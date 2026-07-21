#!/usr/bin/env python3
"""Low-latency PostToolUse foreground dispatcher.

The shell hook reads the host payload once. This script persists the exact
payload, returns a compact envelope for optional child hooks, and performs the
latency-critical checks inline so Bash PostToolUse does not spawn multiple
foreground hook processes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


MAX_FOREGROUND_READ_BYTES = 1_000_000
SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(token|password|passwd|secret|api[_-]?key)=\S+"),
]
FORBIDDEN_PROGRESS_RE = re.compile(
    r"\|\s*(STAGE|STAGE_DONE|STAGE_TDD_PARALLEL_STARTED|"
    r"STAGE_TDD_PARALLEL_DONE|STAGE_FANOUT_STARTED|"
    r"STAGE_FANOUT_UNIT_DONE|STAGE_FANOUT_DONE|"
    r"STAGE_STREAMING_REVIEW_STARTED|STAGE_STREAMING_REVIEW_DONE|"
    r"COMPLETED)\s*\|"
)
TERMINAL_STATUS_RE = re.compile(
    r"^\s*STATUS:\s*(completed|blocked|cancelled)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def regex_string(raw: bytes, name: bytes) -> str:
    match = re.search(rb'"' + re.escape(name) + rb'"\s*:\s*"((?:\\.|[^"\\])*)"', raw)
    if not match:
        return ""
    try:
        return json.loads(b'"' + match.group(1) + b'"')
    except Exception:
        return match.group(1).decode("utf-8", errors="replace")


def regex_int(raw: bytes, name: bytes) -> int | None:
    match = re.search(rb'"' + re.escape(name) + rb'"\s*:\s*(-?\d+)', raw)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def regex_bool(raw: bytes, name: bytes) -> bool:
    return bool(re.search(rb'"' + re.escape(name) + rb'"\s*:\s*true\b', raw))


def redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def load_small_document(raw: bytes) -> dict[str, Any]:
    if len(raw) > 1_000_000:
        return {}
    try:
        document = json.loads(raw)
    except Exception:
        return {}
    return document if isinstance(document, dict) else {}


def nested_string(document: dict[str, Any], tool_input: dict[str, Any], raw: bytes, name: str) -> str:
    value = document.get(name)
    if isinstance(value, str):
        return value
    value = tool_input.get(name)
    if isinstance(value, str):
        return value
    return regex_string(raw, name.encode())


def payload_fields(raw: bytes) -> dict[str, Any]:
    document = load_small_document(raw)
    tool_input = document.get("tool_input") if isinstance(document.get("tool_input"), dict) else {}
    tool_response = document.get("tool_response") if isinstance(document.get("tool_response"), dict) else {}

    exit_code = tool_response.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        exit_code = tool_response.get("returncode")
    if isinstance(exit_code, str) and exit_code.strip().lstrip("-").isdigit():
        exit_code = int(exit_code.strip())
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        exit_code = regex_int(raw, b"exit_code")
    if exit_code is None:
        exit_code = regex_int(raw, b"returncode")

    is_error = bool(tool_response.get("is_error") or document.get("is_error") or regex_bool(raw, b"is_error"))
    if exit_code is None and is_error:
        exit_code = 1

    return {
        "tool_name": str(document.get("tool_name") or regex_string(raw, b"tool_name") or ""),
        "cwd": nested_string(document, tool_input, raw, "cwd") or os.getcwd(),
        "file_path": nested_string(document, tool_input, raw, "file_path"),
        "path": nested_string(document, tool_input, raw, "path"),
        "new_path": nested_string(document, tool_input, raw, "new_path"),
        "command": str(tool_input.get("command") or document.get("command") or regex_string(raw, b"command") or ""),
        "exit_code": exit_code,
        "is_error": is_error,
    }


def git_root_from_hint(hint: str) -> Path | None:
    raw_hint = Path(hint or os.getcwd()).expanduser()
    cursor = raw_hint if raw_hint.is_dir() else raw_hint.parent
    try:
        cursor = cursor.resolve()
    except OSError:
        return None
    for candidate in (cursor, *cursor.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def state_dir_for_project(agent_crew_home: Path, project_root: Path | None) -> Path | None:
    override = os.environ.get("AGENT_CREW_STATE_DIR")
    if override:
        return Path(override).expanduser()
    if project_root is None:
        project = os.environ.get("AGENT_CREW_PROJECT")
        return agent_crew_home / "state" / project if project else None
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", project_root.name.strip()).strip(".-").lower() or "project"
    digest = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:10]
    keyed = agent_crew_home / "state" / f"{slug}-{digest}"
    legacy = agent_crew_home / "state" / slug
    return keyed if keyed.exists() or not legacy.exists() else legacy


def active_task_dirs(state_dir: Path | None) -> list[Path]:
    if state_dir is None:
        return []
    tasks_dir = state_dir / "tasks"
    if not tasks_dir.is_dir():
        return []
    env_task = os.environ.get("AGENT_CREW_TASK_ID")
    if env_task:
        task_dir = tasks_dir / env_task
        return [task_dir] if task_dir.is_dir() else []
    markers = sorted(tasks_dir.glob("active.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for marker in markers[:1]:
        task_id = marker.name.removeprefix("active.")
        task_dir = tasks_dir / task_id
        if task_id and task_dir.is_dir():
            return [task_dir]
    return []


def has_terminal_result(task_dir: Path) -> bool:
    try:
        result = (task_dir / "result.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(TERMINAL_STATUS_RE.search(result))


def latest_forbidden_line(task_dir: Path) -> str:
    try:
        lines = (task_dir / "progress.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines[-50:]):
        if "supervisor_pipeline_bypass_prevented" in line:
            continue
        if FORBIDDEN_PROGRESS_RE.search(line):
            return line
    return ""


def record_bash_tool_event(task_dir: Path, fields: dict[str, Any], now: dt.datetime) -> None:
    command = str(fields.get("command") or "").strip()
    if fields.get("tool_name") != "Bash" or not command:
        return
    exit_code = fields.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        exit_code = 0
    status = "ok" if exit_code == 0 else "error"
    row = {
        "schema_version": 1,
        "trace_id": os.environ.get("AGENT_CREW_TRACE_ID") or os.environ.get("AGENT_CREW_SESSION_ID") or task_dir.name,
        "tool_name": "Bash",
        "action_summary": redact(command)[:500],
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ended_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "exit_code": exit_code,
        "token_usage_ref": f"cost/{task_dir.name}.jsonl",
        "failure_class": "" if status == "ok" else "bash_command_failed",
    }
    with (task_dir / "tool-events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def check_supervisor_progress(task_dir: Path) -> bool:
    if has_terminal_result(task_dir) or (task_dir / "pipeline.json").is_file():
        return False
    line = latest_forbidden_line(task_dir)
    if not line:
        return False
    (task_dir / "result.violation.md").write_text(
        "\n".join(
            [
                "STATUS: blocked",
                "BLOCKER: supervisor_pipeline_bypass_prevented",
                "DETAIL: PostToolUse supervisor-progress-guard detected stage/completion progress before pipeline.json existed.",
                f"EVIDENCE: {line}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": "[agent-crew] supervisor_pipeline_bypass_prevented: "
                f"{task_dir} recorded progress before pipeline.json: {line}",
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
        flush=True,
    )
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        return 0
    tmp_payload = Path(argv[1])
    payload_root = Path(argv[2]).expanduser()
    agent_crew_home = Path(argv[3]).expanduser()
    payload_size = tmp_payload.stat().st_size
    with tmp_payload.open("rb") as handle:
        raw = handle.read(MAX_FOREGROUND_READ_BYTES)
    digest = hashlib.sha256(raw).hexdigest() if payload_size <= MAX_FOREGROUND_READ_BYTES else ""
    now = dt.datetime.now(dt.timezone.utc)
    payload_dir = payload_root / now.strftime("%Y%m%d")
    payload_dir.mkdir(parents=True, exist_ok=True)
    if digest:
        payload_path = payload_dir / f"posttooluse-{digest[:16]}.json"
    else:
        payload_path = payload_dir / f"posttooluse-large-{now.strftime('%H%M%S%f')}-{os.getpid()}.json"

    if payload_path.exists():
        tmp_payload.unlink(missing_ok=True)
    else:
        shutil.move(str(tmp_payload), str(payload_path))

    fields = payload_fields(raw)
    command_bytes = str(fields["command"]).encode("utf-8", errors="replace")
    auto_issue_re = re.compile(
        rb"(^|[^./A-Za-z0-9_-])agent[-_\s]?crew([^/A-Za-z0-9_-]|$)"
        rb"|(^|[^A-Za-z0-9_])crew\s+(run|agent|status|repair|report|update|setup|sync|cost|smm)([^A-Za-z0-9_]|$)"
        rb"|crew:[A-Za-z-]+|[$]crew|supervisor_blocked|blocked_by|STATUS:\s*blocked|BLOCKER:",
        re.IGNORECASE,
    )
    korean_auto_issue_re = re.compile("에이전트\\s*크루|에이전트크루".encode("utf-8"))
    auto_issue_signal = (
        True
        if payload_size > MAX_FOREGROUND_READ_BYTES
        else bool(auto_issue_re.search(command_bytes) or auto_issue_re.search(raw) or korean_auto_issue_re.search(raw))
    )
    route_directive_signal = b"[agent-crew] STOP" in raw or b"[agent-crew] ROUTE" in raw
    envelope = {
        "agent_crew_hook_envelope": 1,
        "hook_event_name": regex_string(raw, b"hook_event_name") or "PostToolUse",
        "payload_path": str(payload_path),
        "payload_sha256": digest,
        "payload_bytes": payload_size,
        "tool_name": fields["tool_name"],
        "cwd": fields["cwd"],
        "file_path": fields["file_path"],
        "path": fields["path"],
        "new_path": fields["new_path"],
        "command": fields["command"],
        "exit_code": fields["exit_code"],
        "is_error": fields["is_error"],
        "contains_mnemos_capture_notification": (
            ("✻".encode("utf-8") in raw and "🧠".encode("utf-8") in raw)
            or (b"\\u273b" in raw and (b"\\ud83e\\udde0" in raw or b"\\U0001f9e0" in raw))
        ),
        "contains_auto_issue_signal": auto_issue_signal,
        "contains_route_directive_signal": route_directive_signal,
    }
    print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))

    state_dir = state_dir_for_project(
        agent_crew_home,
        git_root_from_hint(fields["cwd"] or fields["file_path"] or fields["path"] or fields["new_path"]),
    )
    for task_dir in active_task_dirs(state_dir):
        try:
            record_bash_tool_event(task_dir, fields, now)
        except Exception:
            pass
        try:
            if check_supervisor_progress(task_dir):
                return 2
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
