#!/usr/bin/env python3
"""Deterministic local runtime helpers for the crew CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

try:
    from project_state import resolve_project_state
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from project_state import resolve_project_state
from quality_loop_lib import check_quality_loop, looks_mutating_task
from task_capability_lib import required_capabilities_for_task


SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(token|password|passwd|secret|api[_-]?key)=\S+"),
]

HANGUL_PATTERN = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]")
JAPANESE_PATTERN = re.compile(r"[\u3040-\u30ff]")
HAN_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04ff]")
ARABIC_PATTERN = re.compile(r"[\u0600-\u06ff]")
LATIN_EXTENDED_PATTERN = re.compile(r"[\u00c0-\u024f]")
NON_ASCII_PATTERN = re.compile(r"[^\x00-\x7f]")
AMBIGUOUS_TASKS = {
    "go",
    "yes",
    "ok",
    "okay",
    "continue",
    "proceed",
    "resume",
    "do it",
    "fix this",
    "do the thing",
    "do the thing from before",
}
GIT_BRANCH_CACHE: dict[str, str] = {}

AGENT_LAYER_LABELS = {
    "project": "현재 프로젝트 전용",
    "user": "내 개인 기본",
    "system": "agent-crew 기본",
}
AGENT_LAYER_SCOPES = {
    "project": "이 저장소에서만 사용",
    "user": "모든 프로젝트에서 기본 후보로 사용",
    "system": "agent-crew가 제공하는 기본값",
}


def utc_now_z() -> str:
    """Return the progress-buffer timestamp format used by supervisor."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def host_bridge_command_argv(command: str) -> tuple[list[str], str]:
    try:
        command_argv = shlex.split(command) if command.strip() else []
    except ValueError as exc:
        return [], str(exc)

    if command_argv and command_argv[0].startswith("~"):
        command_argv = [str(Path(command_argv[0]).expanduser()), *command_argv[1:]]

    return command_argv, ""


def bridge_hosts_from_command(command: str, command_argv: list[str]) -> list[str]:
    hosts: list[str] = []

    def add_host(host: str) -> None:
        if host and host not in hosts:
            hosts.append(host)

    def host_from_token(token: str) -> str:
        name = Path(token).name
        if name == "codex-host-bridge":
            return "codex"
        if name == "claude-host-bridge":
            return "claude"
        return ""

    for token in command_argv:
        host = host_from_token(token)
        add_host(host)

        try:
            nested_tokens = shlex.split(token)
        except ValueError:
            nested_tokens = []
        for nested in nested_tokens:
            host = host_from_token(nested)
            add_host(host)

    for bridge_match in re.finditer(
        r"(?<![\w.-])(codex-host-bridge|claude-host-bridge)(?![\w.-])",
        command or "",
    ):
        add_host("codex" if bridge_match.group(1) == "codex-host-bridge" else "claude")

    return hosts


def bridge_host_from_command(command: str, command_argv: list[str]) -> str:
    hosts = bridge_hosts_from_command(command, command_argv)
    return hosts[0] if hosts else ""


def host_bridge_failure_reason(bridge_record: dict) -> str:
    if bridge_record.get("timed_out"):
        return "bridge_timeout"
    if bridge_record.get("returncode") == 0:
        return "bridge_reported_blocked"
    if bridge_record.get("failure_class"):
        return str(bridge_record["failure_class"])

    return "host_bridge_command_failed"


def host_bridge_failure_detail(bridge_record: dict, *, limit: int = 240) -> str:
    detail = str(bridge_record.get("stderr") or bridge_record.get("stdout") or "").strip()
    if not detail:
        return ""

    detail = " ".join(redact(detail).split())
    return detail[:limit]


def trace_id_for(register: dict, task_dir: Path, stage: int = 0, attempt: int = 0) -> str:
    session_id = register.get("session_id", task_dir.name)
    return f"{session_id}.{task_dir.name}.{stage}.{attempt}"


def git_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return Path.cwd().resolve()


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return value[:48] or "task"


def append_jsonl(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path, fallback: dict | None = None) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback or {})
    return data if isinstance(data, dict) else dict(fallback or {})


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def git_branch(project_root: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(project_root), "branch", "--show-current"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return out
    except Exception:
        pass
    return ""


def git_status_short(project_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(project_root), "status", "--short"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return ""


def text_snippet(path: Path, *, limit: int = 4000) -> str:
    text = load_text(path).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n...[truncated]"


def clipboard_available() -> bool:
    if Path("/usr/bin/pbcopy").is_file():
        return True
    try:
        return subprocess.run(["which", "pbcopy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except Exception:
        return False


def copy_to_clipboard(text: str) -> bool:
    if not clipboard_available():
        return False
    try:
        result = subprocess.run(["pbcopy"], input=text, text=True, check=False)
        return result.returncode == 0
    except Exception:
        return False


def display_host(value: str) -> str:
    host = str(value or "unknown").strip()
    if not host:
        host = "unknown"
    known = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini", "unknown": "Unknown"}
    return known.get(host.lower(), host[:1].upper() + host[1:])


def circled_number(index: int) -> str:
    values = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
    if 1 <= index <= len(values):
        return values[index - 1]
    return f"[{index}]"


def relative_time_label(epoch: float, *, now: float | None = None) -> str:
    now_value = time.time() if now is None else now
    age = max(0, int(now_value - epoch))
    if age < 60:
        return "방금 전"
    minutes = age // 60
    if minutes < 60:
        return f"{minutes}분 전"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}시간 전"
    return f"{hours // 24}일 전"


def first_summary_line(*texts: str, limit: int = 52) -> str:
    for text in texts:
        for line in str(text or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("STATUS:"):
                continue
            if stripped.startswith("SUMMARY:"):
                stripped = stripped.removeprefix("SUMMARY:").strip()
            if len(stripped) > limit:
                return stripped[: limit - 3].rstrip() + "..."
            return stripped
    return "최근 작업 요약 없음"


def file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def latest_path_mtime(paths: list[Path]) -> float:
    values = [file_mtime(path) for path in paths if path.exists()]
    return max(values) if values else 0.0


def parse_iso_epoch(value: str) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def epoch_from_millis(value: object) -> float:
    try:
        number = float(value)
    except Exception:
        return 0.0
    if number > 10_000_000_000:
        return number / 1000
    return number


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude")).expanduser()


def project_name_from_cwd(cwd: object) -> str:
    value = str(cwd or "").strip()
    if not value:
        return "unknown"
    return Path(value).name or "unknown"


def branch_from_session(metadata: dict, cwd: object) -> str:
    branch = str(metadata.get("branch") or "").strip()
    if branch:
        return branch
    value = str(cwd or "").strip()
    if not value:
        return "unknown"
    detected = GIT_BRANCH_CACHE.get(value)
    if detected is None:
        detected = git_branch(Path(value))
        GIT_BRANCH_CACHE[value] = detected
    return detected or "unknown"


def project_name_from_worktree_cwd(cwd: object) -> str:
    value = str(cwd or "").strip()
    if not value:
        return "unknown"
    path = Path(value)
    name = path.name
    parent = path.parent.name
    if parent.endswith("-worktrees") and name:
        return name
    return name or "unknown"


def text_from_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(part for part in parts if part)
    return ""


def extract_message_text(row: dict) -> str:
    for key in ("summary", "prompt", "text", "content"):
        text = text_from_value(row.get(key))
        if text:
            return text
    message = row.get("message")
    if isinstance(message, dict):
        return text_from_value(message.get("content"))
    if isinstance(message, str):
        return message
    return ""


def is_low_signal_summary(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return True
    prefixes = (
        "<permissions instructions>",
        "<apps_instructions>",
        "<skills_instructions>",
        "<environment_context>",
        "# AGENTS.md instructions",
    )
    return any(stripped.startswith(prefix) for prefix in prefixes)


def tail_jsonl_summary(path: Path, *, byte_limit: int = 256_000, line_limit: int = 240) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - byte_limit))
            raw = handle.read().decode("utf-8", errors="replace")
    except Exception:
        return ""

    for line in reversed(raw.splitlines()[-line_limit:]):
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        text = ""
        if row.get("type") == "event_msg":
            text = extract_message_text(payload)
        elif row.get("type") == "response_item":
            role = payload.get("role")
            if role in {"assistant", "user"}:
                text = extract_message_text(payload)
        summary = first_summary_line(text)
        if summary and summary != "최근 작업 요약 없음" and not is_low_signal_summary(summary):
            return summary
    return ""


def latest_jsonl_summary(path: Path, *, limit: int = 52) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
    except Exception:
        return ""
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        text = extract_message_text(row)
        if text:
            return first_summary_line(text, limit=limit)
    return ""


def claude_project_dir_name(cwd: object) -> str:
    return str(cwd or "").replace("/", "-")


def claude_summary_for_session(home: Path, session_id: str, cwd: object) -> str:
    candidates: list[Path] = []
    if cwd:
        candidates.append(home / "projects" / claude_project_dir_name(cwd) / f"{session_id}.jsonl")
    candidates.extend((home / "projects").glob(f"*/{session_id}.jsonl"))
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        summary = latest_jsonl_summary(path)
        if summary:
            return summary
    return ""


def codex_session_candidates(home: Path) -> list[dict]:
    candidates_by_ref: dict[str, dict] = {}
    index_path = home / "session_index.jsonl"
    if index_path.is_file():
        for line in load_text(index_path).splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            session_id = str(row.get("id") or "").strip()
            if not session_id:
                continue
            cwd = row.get("cwd") or row.get("project_root")
            project = row.get("project") or row.get("project_name") or project_name_from_worktree_cwd(cwd)
            updated_at = parse_iso_epoch(str(row.get("updated_at") or row.get("created_at") or ""))
            candidate = {
                "source": "codex",
                "session_ref": f"codex:{session_id}",
                "ai_type": "Codex",
                "project": str(project or "unknown"),
                "branch": branch_from_session(row, cwd),
                "summary": first_summary_line(str(row.get("thread_name") or row.get("summary") or "")),
                "updated_at": updated_at or file_mtime(index_path),
                "status": str(row.get("status") or "최근 세션"),
                "cwd": str(cwd or ""),
            }
            candidates_by_ref[candidate["session_ref"]] = candidate

    for candidate in codex_rollout_session_candidates(home):
        current = candidates_by_ref.get(candidate["session_ref"])
        if current is None or candidate.get("updated_at", 0) >= current.get("updated_at", 0):
            candidates_by_ref[candidate["session_ref"]] = candidate

    return list(candidates_by_ref.values())


def codex_rollout_session_candidates(home: Path, *, recent_days: int = 3) -> list[dict]:
    sessions_dir = home / "sessions"
    if not sessions_dir.is_dir():
        return []

    cutoff = time.time() - recent_days * 24 * 60 * 60
    candidates: list[dict] = []
    for path in sessions_dir.rglob("*.jsonl"):
        if file_mtime(path) < cutoff:
            continue
        candidate = codex_rollout_session_candidate(path)
        if candidate:
            candidates.append(candidate)
    return candidates


def codex_rollout_session_candidate(path: Path, *, scan_line_limit: int = 80) -> dict | None:
    meta: dict = {}
    context: dict = {}
    summary = ""
    latest_timestamp = ""
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line_number > scan_line_limit and meta and context:
                    break
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                latest_timestamp = str(row.get("timestamp") or latest_timestamp)
                row_type = row.get("type")
                payload = row.get("payload")
                if row_type == "session_meta" and isinstance(payload, dict):
                    meta = payload
                elif row_type == "turn_context" and isinstance(payload, dict):
                    context = payload
                elif not summary:
                    summary = extract_message_text(payload if isinstance(payload, dict) else {})
    except Exception:
        return None

    session_id = str(meta.get("id") or meta.get("session_id") or "").strip()
    if not session_id:
        return None
    cwd = meta.get("cwd") or context.get("cwd")
    if not cwd:
        workspace_roots = context.get("workspace_roots")
        if isinstance(workspace_roots, list) and workspace_roots:
            cwd = workspace_roots[0]
    summary = tail_jsonl_summary(path) or summary
    updated_at = parse_iso_epoch(latest_timestamp) or file_mtime(path)
    return {
        "source": "codex-rollout",
        "session_ref": f"codex:{session_id}",
        "ai_type": "Codex",
        "project": project_name_from_worktree_cwd(cwd),
        "branch": branch_from_session(meta, cwd),
        "summary": first_summary_line(summary, str(meta.get("thread_name") or "")),
        "updated_at": updated_at,
        "status": str(meta.get("thread_source") or "최근 세션"),
        "cwd": str(cwd or ""),
    }


def claude_session_candidates(home: Path) -> list[dict]:
    sessions_dir = home / "sessions"
    if not sessions_dir.is_dir():
        return []

    candidates: list[dict] = []
    for path in sorted(sessions_dir.glob("*.json")):
        row = load_json(path, {})
        session_id = str(row.get("sessionId") or row.get("session_id") or "").strip()
        if not session_id:
            continue
        cwd = row.get("cwd") or row.get("project_root")
        summary = claude_summary_for_session(home, session_id, cwd)
        candidates.append(
            {
                "source": "claude",
                "session_ref": f"claude:{session_id}",
                "ai_type": "Claude",
                "project": project_name_from_cwd(cwd),
                "branch": branch_from_session(row, cwd),
                "summary": first_summary_line(summary, str(row.get("name") or "")),
                "updated_at": epoch_from_millis(row.get("updatedAt")) or file_mtime(path),
                "status": str(row.get("status") or row.get("kind") or "최근 세션"),
            }
        )
    return candidates


def parse_aoe_session_line(line: str) -> dict | None:
    match = re.match(r"^(?P<title>.+?)\s{2,}(?P<group>.+?)\s+(?P<cwd>/\S+)\s+(?P<session_id>\S+)\s*$", line.strip())
    if not match:
        return None
    title = match.group("title").strip()
    if title.upper() == "TITLE":
        return None
    return {
        "title": title,
        "cwd": match.group("cwd").strip(),
        "session_id": match.group("session_id").strip(),
    }


def aoe_session_candidates() -> list[dict]:
    if not interact_aoe_enabled():
        return []
    try:
        completed = subprocess.run(
            ["aoe", "list"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    if completed.returncode != 0:
        return []

    candidates: list[dict] = []
    for line in (completed.stdout or "").splitlines():
        parsed = parse_aoe_session_line(line)
        if not parsed:
            continue
        title = parsed["title"]
        cwd = parsed["cwd"]
        session_id = parsed["session_id"]
        title_lower = title.lower()
        if "claude" in title_lower:
            ai_type = "Claude"
        elif "codex" in title_lower:
            ai_type = "Codex"
        elif "opencode" in title_lower:
            ai_type = "OpenCode"
        else:
            ai_type = "AoE"

        candidates.append(
            {
                "source": "aoe",
                "session_ref": f"aoe:{session_id}",
                "ai_type": ai_type,
                "project": project_name_from_cwd(cwd),
                "branch": branch_from_session({}, cwd),
                "summary": "AoE registered session",
                "updated_at": time.time(),
                "status": "aoe",
                "cwd": cwd,
                "aoe_title": title,
                "aoe_id": session_id,
            }
        )
    return candidates


def interact_aoe_enabled() -> bool:
    return os.environ.get("AGENT_CREW_INTERACT_AOE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def interact_cache_path(agent_crew_home: Path) -> Path:
    return agent_crew_home / "cache" / "interact-sessions.json"


def directory_signature(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "mtime": 0.0}
    return {
        "exists": True,
        "mtime": file_mtime(path),
    }


def interact_cache_source_signature() -> dict:
    codex = codex_home()
    claude = claude_home()
    return {
        "codex_index": directory_signature(codex / "session_index.jsonl"),
        "codex_sessions": directory_signature(codex / "sessions"),
        "claude_sessions": directory_signature(claude / "sessions"),
        "claude_projects": directory_signature(claude / "projects"),
    }


def read_interact_session_cache(agent_crew_home: Path) -> list[dict] | None:
    payload = load_json(interact_cache_path(agent_crew_home), {})
    if payload.get("schema_version") != 1:
        return None
    if payload.get("sources") != interact_cache_source_signature():
        return None
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return None
    return [
        dict(candidate)
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("source") != "aoe"
    ]


def write_interact_session_cache(agent_crew_home: Path, candidates: list[dict]) -> None:
    cache_candidates: list[dict] = []
    for candidate in candidates:
        if candidate.get("source") == "aoe":
            continue
        row = dict(candidate)
        row.pop("index", None)
        cache_candidates.append(row)
    write_json(
        interact_cache_path(agent_crew_home),
        {
            "schema_version": 1,
            "generated_at": utc_now_z(),
            "sources": interact_cache_source_signature(),
            "candidates": cache_candidates,
        },
    )


def task_session_enrichment(state_dir: Path, task_dir: Path) -> dict:
    register = load_json(task_dir / "register.json", {})
    result = load_text(task_dir / "result.md")
    handoff = load_text(task_dir / "handoff.md")
    latest_progress = latest_progress_event(task_dir)
    project_name = register.get("project_name") or load_json(state_dir / "project.json", {}).get("project_name") or state_dir.name
    branch = register.get("branch") or "unknown"
    summary = first_summary_line(
        result,
        latest_progress.get("detail", ""),
        handoff,
        register.get("task", ""),
    )
    updated_at = latest_path_mtime(
        [
            task_dir / "result.md",
            task_dir / "progress.buffer.jsonl",
            task_dir / "handoff.md",
            task_dir / "register.json",
        ]
    )
    return {
        "project": str(project_name),
        "branch": str(branch),
        "summary": summary,
        "updated_at": updated_at,
    }


def collect_task_enrichments(agent_crew_home: Path) -> list[dict]:
    enrichments: list[dict] = []
    states_dir = agent_crew_home / "state"
    for state_dir in sorted(states_dir.glob("*")):
        tasks_dir = state_dir / "tasks"
        if not tasks_dir.is_dir():
            continue
        for task_dir in sorted(tasks_dir.iterdir()):
            if not task_dir.is_dir() or task_dir.name.startswith("active."):
                continue
            if not (task_dir / "register.json").is_file():
                continue
            enrichments.append(task_session_enrichment(state_dir, task_dir))
    enrichments.sort(key=lambda row: row.get("updated_at", 0), reverse=True)
    return enrichments


def enrich_session_candidates(candidates: list[dict], enrichments: list[dict]) -> None:
    for candidate in candidates:
        if candidate.get("summary") and candidate["summary"] != "최근 작업 요약 없음":
            continue
        for enrichment in enrichments:
            if enrichment.get("project") != candidate.get("project"):
                continue
            branch = str(enrichment.get("branch") or "")
            if branch != "unknown" and branch != candidate.get("branch"):
                continue
            candidate["summary"] = enrichment.get("summary") or candidate["summary"]
            break


def collect_session_candidates(agent_crew_home: Path, *, limit: int = 20) -> list[dict]:
    fresh_aoe = aoe_session_candidates() if interact_aoe_enabled() else []
    cached = read_interact_session_cache(agent_crew_home)
    if cached is not None:
        candidates = [
            *fresh_aoe,
            *cached,
        ]
        candidates.sort(key=lambda row: row.get("updated_at", 0), reverse=True)
        for index, row in enumerate(candidates[:limit], start=1):
            row["index"] = index
        return candidates[:limit]

    candidates = [
        *fresh_aoe,
        *codex_session_candidates(codex_home()),
        *claude_session_candidates(claude_home()),
    ]
    if any(not row.get("summary") or row.get("summary") == "최근 작업 요약 없음" for row in candidates):
        enrich_session_candidates(candidates, collect_task_enrichments(agent_crew_home))

    candidates.sort(key=lambda row: row.get("updated_at", 0), reverse=True)
    write_interact_session_cache(agent_crew_home, candidates)
    for index, row in enumerate(candidates[:limit], start=1):
        row["index"] = index
    return candidates[:limit]


def collect_targeted_session_candidates(agent_crew_home: Path, selector: str, *, limit: int = 20) -> list[dict]:
    target = str(selector or "").strip().lower()
    if not target:
        return []

    targeted: list[dict] = []
    for candidate in aoe_session_candidates():
        if session_matches_selector(candidate, target):
            targeted.append(candidate)
    if targeted:
        targeted.sort(key=lambda row: row.get("updated_at", 0), reverse=True)
        for index, row in enumerate(targeted[:limit], start=1):
            row["index"] = index
        return targeted[:limit]

    cached = read_interact_session_cache(agent_crew_home)
    if cached is not None:
        targeted = [
            row
            for row in cached
            if session_matches_selector(row, target)
        ]
        targeted.sort(key=lambda row: row.get("updated_at", 0), reverse=True)
        for index, row in enumerate(targeted[:limit], start=1):
            row["index"] = index
        return targeted[:limit]

    return []


def render_session_candidates(candidates: list[dict], *, grouped_threshold: int = 4) -> str:
    if not candidates:
        return "최근 AI 세션을 찾지 못했습니다.\n"

    lines = ["전송할 AI 세션 후보를 찾았습니다.", ""]
    first = candidates[0]
    lines.extend(
        [
            "추천:",
            f"{circled_number(1)} {first['ai_type']} · {first['project']} · {first['branch']}",
            f"   {first['summary']} · {relative_time_label(first['updated_at'])}",
        ]
    )

    others = candidates[1:]
    if others:
        lines.append("")
        if len(candidates) >= grouped_threshold:
            current_project = ""
            for row in others:
                if row["project"] != current_project:
                    current_project = row["project"]
                    lines.extend(["", current_project])
                lines.extend(
                    [
                        f"{circled_number(row['index'])} {row['ai_type']} · {row['branch']}",
                        f"   {row['summary']} · {relative_time_label(row['updated_at'])}",
                    ]
                )
        else:
            lines.append("다른 후보:")
            for row in others:
                lines.extend(
                    [
                        f"{circled_number(row['index'])} {row['ai_type']} · {row['project']} · {row['branch']}",
                        f"   {row['summary']} · {relative_time_label(row['updated_at'])}",
                    ]
                )

    lines.extend(["", "번호나 설명으로 선택하세요.", "예: 1, Claude agent-crew, main 브랜치"])
    return "\n".join(lines) + "\n"


def session_match_text(candidate: dict) -> str:
    return " ".join(
        [
            str(candidate.get("ai_type", "")),
            str(candidate.get("project", "")),
            str(candidate.get("branch", "")),
            str(candidate.get("summary", "")),
            str(candidate.get("cwd", "")),
            str(candidate.get("source", "")),
            str(candidate.get("aoe_title", "")),
            str(candidate.get("aoe_id", "")),
        ]
    ).lower()


def session_selector_tokens(selector: str) -> list[str]:
    return [token for token in re.split(r"\s+", str(selector or "").lower()) if token]


def session_matches_selector(candidate: dict, selector: str) -> bool:
    tokens = session_selector_tokens(selector)
    if not tokens:
        return True
    match_text = session_match_text(candidate)
    return all(token in match_text for token in tokens)


def select_session_candidate(candidates: list[dict], selector: str) -> dict | None:
    value = str(selector or "").strip()
    if not value or not candidates:
        return None
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(candidates):
            return candidates[index - 1]
        return None

    tokens = session_selector_tokens(value)
    best: tuple[int, dict | None] = (0, None)
    for candidate in candidates:
        match_text = session_match_text(candidate)
        score = sum(1 for token in tokens if token in match_text)
        if score > best[0]:
            best = (score, candidate)
    return best[1] if best[0] else None


def render_selected_session(candidate: dict) -> str:
    index = int(candidate.get("index") or 1)
    lines = [
        "선택한 세션:",
        f"{circled_number(index)} {candidate['ai_type']} · {candidate['project']} · {candidate['branch']}",
        f"   {candidate['summary']} · {relative_time_label(candidate['updated_at'])}",
        "",
        "STATUS: selected",
    ]
    return "\n".join(lines) + "\n"


def append_progress(task_dir: Path, row: dict) -> None:
    append_jsonl(task_dir / "progress.buffer.jsonl", row)


def append_progress_log(task_dir: Path, event: str, detail: str) -> None:
    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_now_z()} | {event} | {detail}\n")


def agent_uuid_for_display() -> str:
    for name in (
        "AGENT_CREW_AGENT_UUID",
        "AGENT_CREW_HOST_AGENT_UUID",
        "CODEX_THREAD_ID",
        "CODEX_SESSION_ID",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return "unavailable"


def render_start_banner(register: dict, task_dir: Path) -> str:
    task = str(register.get("task") or "").strip()
    if len(task) > 96:
        task = task[:93].rstrip() + "..."
    agent_uuid = agent_uuid_for_display()
    task_id = register.get("task_id", task_dir.name)
    lines = [
        "[crew] START",
        f"  mapping:    {agent_uuid} -> {task_id}",
        f"  agent_uuid: {agent_uuid}",
        f"  task_id:    {task_id}",
        f"  title:      {task or '(untitled)'}",
        f"  branch:     {register.get('branch', '')}",
        f"  state:      {task_dir}",
        "  monitor:    crew:status (CLI: crew status)",
    ]
    return "\n".join(lines)


def latest_progress_event(task_dir: Path) -> dict:
    buffer = task_dir / "progress.buffer.jsonl"
    if buffer.is_file():
        for line in reversed(buffer.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                row = json.loads(line)
            except Exception:
                continue
            return {
                "ts": row.get("ts", ""),
                "event": row.get("event", ""),
                "stage": row.get("stage", 0),
                "agent": row.get("agent", ""),
                "detail": row.get("detail", ""),
            }

    log = task_dir / "progress.log"
    if log.is_file():
        for line in reversed(log.read_text(encoding="utf-8", errors="replace").splitlines()):
            parts = [p.strip() for p in line.split("|", 2)]
            if len(parts) == 3:
                return {"ts": parts[0], "event": parts[1], "stage": 0, "agent": "", "detail": parts[2]}
            if line.strip():
                return {"ts": "", "event": "LOG", "stage": 0, "agent": "", "detail": line.strip()}

    return {"ts": "", "event": "", "stage": 0, "agent": "", "detail": "no progress events yet"}


def progress_age_seconds(event: dict) -> int | None:
    ts = str(event.get("ts") or "").strip().rstrip("Z")
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
        except ValueError:
            continue
    return None


def render_wait_progress(register: dict, task_dir: Path) -> str:
    latest = latest_progress_event(task_dir)
    age = progress_age_seconds(latest)
    stage_value = latest.get("agent") or latest.get("stage")
    stage = f"stage={stage_value}" if stage_value not in ("", None) else "stage=0"
    age_text = "unknown" if age is None else f"{age}s"
    detail = str(latest.get("detail") or "").strip()
    if len(detail) > 120:
        detail = detail[:117].rstrip() + "..."
    return (
        f"[crew] WAIT | task_id={register.get('task_id', task_dir.name)} "
        f"phase={latest.get('event') or 'unknown'} {stage} "
        f"last_update_age={age_text} detail={detail}"
    )


def append_delegation(
    task_dir: Path,
    *,
    trace_id: str,
    span_id: str,
    parent_span_id: str,
    agent_role: str,
    unit_id: str,
    delegated_by: str,
    status: str,
) -> None:
    append_jsonl(
        task_dir / "delegation.jsonl",
        {
            "ts": utc_now_z(),
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "agent_role": agent_role,
            "unit_id": unit_id,
            "delegated_by": delegated_by,
            "status": status,
        },
    )


def append_tool_event(
    task_dir: Path,
    *,
    trace_id: str,
    tool_name: str,
    action_summary: str,
    started_at: str,
    ended_at: str,
    status: str,
    exit_code: int | None,
    failure_class: str,
) -> None:
    append_jsonl(
        task_dir / "tool-events.jsonl",
        {
            "schema_version": 1,
            "trace_id": trace_id,
            "tool_name": tool_name,
            "action_summary": redact(action_summary)[:500],
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "exit_code": exit_code,
            "token_usage_ref": f"cost/{task_dir.name}.jsonl",
            "failure_class": failure_class,
        },
    )


def _text_from_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def tail_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return "...[truncated]\n" + text[-limit:]


def tail_text_single_line(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return "...[truncated] " + text[-limit:]


def bridge_output_excerpt(bridge_record: dict, *, limit: int = 2000) -> str:
    sections = []
    for stream_name in ("stdout", "stderr"):
        output = redact(_text_from_output(bridge_record.get(stream_name))).strip()
        if not output:
            continue
        sections.extend([
            f"### {stream_name}",
            "",
            "```text",
            tail_text(output, limit).replace("```", "` ` `"),
            "```",
        ])
    return "\n".join(sections).strip()


def render_bridge_output_section(bridge_record: dict) -> str:
    excerpt = bridge_output_excerpt(bridge_record)
    if not excerpt:
        excerpt = "No bridge stdout or stderr was captured."
    return "\n## Host Bridge Output\n\n" + excerpt.rstrip() + "\n"


def host_bridge_child_output_preview(stdout: object, stderr: object, *, limit: int = 180) -> str:
    parts = []
    for stream_name, output_value in (("stdout", stdout), ("stderr", stderr)):
        output = redact(_text_from_output(output_value)).strip()
        if not output:
            continue
        single_line = re.sub(r"\s+", " ", output)
        parts.append(f"{stream_name}: {tail_text_single_line(single_line, limit)}")
    return " | ".join(parts)


def write_host_bridge_output_tail(
    task_dir: Path,
    stdout: object,
    stderr: object,
    *,
    limit: int = 4000,
) -> str:
    sections = []
    for stream_name, output_value in (("stdout", stdout), ("stderr", stderr)):
        output = redact(_text_from_output(output_value)).strip()
        if output:
            sections.append(f"## {stream_name}\n\n{tail_text(output, limit)}")
    if not sections:
        return ""

    path = task_dir / "context" / "host-bridge-output-tail.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(sections).rstrip() + "\n", encoding="utf-8")
    return "context/host-bridge-output-tail.txt"


def render_completed_result(
    task: str,
    task_id: str,
    completion_path: str,
    note: str,
    bridge_record: dict | None = None,
) -> str:
    lines = [
        f"# {task}",
        "",
        "STATUS: completed",
        f"TASK_ID: {task_id}",
        "MEASUREMENTS: host bridge completion recorded 1 automatic completion event",
        f"EVIDENCE: {completion_path}",
        "UNCERTAINTY: Host bridge command success indicates handoff delivery completed; downstream host prompt quality still depends on the active runtime.",
    ]
    if note:
        lines.append(f"NOTE: {note}")
    result = "\n".join(lines).rstrip() + "\n"
    if bridge_record is not None:
        result += render_bridge_output_section(bridge_record)
    return result


def render_quality_loop_blocked_result(
    task: str,
    task_id: str,
    failures: list[str],
    evidence_path: str,
) -> str:
    return (
        f"# {task}\n\n"
        "STATUS: blocked\n"
        f"TASK_ID: {task_id}\n"
        "MEASUREMENTS: runtime quality-loop validation ran 1 check, 0 retries\n"
        "BLOCKER: missing_quality_loop_pipeline\n"
        f"EVIDENCE: {evidence_path}\n"
        "EVIDENCE: context/quality-loop-runtime-check.json\n"
        "DETAIL: Host bridge or fake-host completion cannot mark a mutating "
        "implementation task completed until the pipeline trace proves TDD, "
        "review, remediation/refactor after rejection, and reviewer approval.\n"
        "FAILURES: " + ", ".join(failures) + "\n"
        "UNCERTAINTY: Host bridge execution may have run outside this process, "
        "but it did not leave the required provider-neutral quality-loop state.\n"
    )


def host_bridge_next_line(task_dir: Path, task_id: str, bridge_command_present: bool) -> str:
    handoff_path = str(task_dir / "handoff.md")
    lines = [
        f"NEXT: Continue with {handoff_path}, then run "
        f"`crew repair {task_id} --status completed --note \"<summary>\"`.",
    ]
    if not bridge_command_present:
        lines.append(
            "DETAIL: no external bridge command is required for this state; "
            "agent-crew recorded a resumable internal handoff."
        )
    else:
        lines.append("DETAIL: the configured host bridge did not complete this handoff.")
    return "\n".join(lines) + "\n"


def host_bridge_current_session_next_line(task_dir: Path, task_id: str) -> str:
    handoff_path = str(task_dir / "handoff.md")
    lines = [
        f"NEXT: Continue this existing crew:run handoff in the current Codex session from {handoff_path}.",
        "DETAIL: Codex refused nested bridge execution because this command is already running inside Codex; no background bridge is still running.",
        f"REPAIR: After completing the handoff, run `crew repair {task_id} --status completed --note \"<summary>\"`.",
    ]
    return "\n".join(lines) + "\n"


def mark_quality_loop_blocked(
    task_dir: Path,
    register: dict,
    pipeline: dict,
    quality_result: dict,
    evidence_path: str,
) -> None:
    now = utc_now_z()
    failures = list(quality_result.get("failures", []))
    check_path = task_dir / "context" / "quality-loop-runtime-check.json"
    write_json(check_path, quality_result)

    register.update({
        "current_phase": "blocked",
        "blocked_by": ["missing_quality_loop_pipeline"],
        "host_bridge_status": "quality_blocked",
        "host_bridge_completion_path": str(task_dir / evidence_path),
        "host_bridge_completed_at": now,
    })
    pipeline.setdefault("completed_stages", 0)

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    (task_dir / "result.md").write_text(
        render_quality_loop_blocked_result(
            register.get("task", task_dir.name),
            register.get("task_id", task_dir.name),
            failures,
            evidence_path,
        ),
        encoding="utf-8",
    )

    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now} | QUALITY_BLOCKED | missing_quality_loop_pipeline\n")
        handle.write(f"{now} | STATUS | blocked\n")

    append_progress(
        task_dir,
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', task_dir.name)}.{task_dir.name}.0.0",
            "task_id": task_dir.name,
            "session_id": register.get("session_id", ""),
            "event": "QUALITY_BLOCKED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "failed",
            "detail": "missing_quality_loop_pipeline",
            "files": [evidence_path, "context/quality-loop-runtime-check.json", "result.md"],
        },
    )


def mark_auto_completed(task_dir: Path, register: dict, pipeline: dict,
                        bridge_record: dict, note: str,
                        preserve_quality_state: bool = False) -> None:
    now = utc_now_z()
    completion_path = task_dir / "context" / "host-bridge-completion.json"
    write_json(completion_path, bridge_record)

    register.update({
        "current_phase": "completed",
        "blocked_by": [],
        "host_bridge_status": "auto_completed",
        "host_bridge_completion_path": str(completion_path),
        "host_bridge_completed_at": now,
    })

    stages = pipeline.get("stages") or ["supervisor"]
    pipeline["completed_stages"] = len(stages)
    if preserve_quality_state:
        pipeline.setdefault("stage_agent_status", {})
    else:
        pipeline["stage_agent_status"] = {
            "1": {"supervisor": "completed"}
        }

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    existing_result = load_text(task_dir / "result.md")
    if preserve_quality_state and re.search(r"^STATUS\s*:\s*completed\b", existing_result, re.I | re.M):
        marker = "HOST_BRIDGE: auto_completed"
        addition = ""
        if marker not in existing_result:
            addition += (
                "\n" + marker + "\n"
                "EVIDENCE: context/host-bridge-completion.json\n"
            )
        if "## Host Bridge Output" not in existing_result:
            addition += render_bridge_output_section(bridge_record)
        if addition:
            (task_dir / "result.md").write_text(existing_result.rstrip() + addition, encoding="utf-8")
    else:
        (task_dir / "result.md").write_text(
            render_completed_result(
                register.get("task", task_dir.name),
                register.get("task_id", task_dir.name),
                "context/host-bridge-completion.json",
                note,
                bridge_record,
            ),
            encoding="utf-8",
        )

    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now} | HOST_BRIDGE | auto completed\n")
        handle.write(f"{now} | STATUS | completed\n")

    append_progress(
        task_dir,
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', task_dir.name)}.{task_dir.name}.0.0",
            "task_id": task_dir.name,
            "session_id": register.get("session_id", ""),
            "event": "HOST_BRIDGE",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "completed",
            "detail": "auto host bridge completed",
            "files": ["context/host-bridge-completion.json", "result.md"],
        },
    )
    append_progress(
        task_dir,
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', task_dir.name)}.{task_dir.name}.0.0",
            "task_id": task_dir.name,
            "session_id": register.get("session_id", ""),
            "event": "COMPLETED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "completed",
            "detail": "completed",
            "files": [],
        },
    )


def json_candidate_texts(text: str) -> list[str]:
    stripped = text.strip()
    candidates: list[str] = []
    if stripped:
        candidates.append(stripped)

    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.I | re.S):
        fenced = match.group(1).strip()
        if fenced:
            candidates.append(fenced)

    for line in text.splitlines():
        line = line.strip()
        if line and line not in candidates:
            candidates.append(line)

    return candidates


def has_non_english_script(text: str) -> bool:
    if any(
        pattern.search(text)
        for pattern in (
            HANGUL_PATTERN,
            JAPANESE_PATTERN,
            HAN_PATTERN,
            CYRILLIC_PATTERN,
            ARABIC_PATTERN,
            LATIN_EXTENDED_PATTERN,
        )
    ):
        return True

    return any(
        not char.isascii() and unicodedata.category(char).startswith("L")
        for char in text
    )


def active_codex_session() -> bool:
    return any(
        os.environ.get(name, "").strip()
        for name in ("CODEX", "CODEX_CI", "CODEX_THREAD_ID", "CODEX_MANAGED_BY_NPM")
    )


def active_claude_session() -> bool:
    return any(
        os.environ.get(name, "").strip()
        for name in ("CLAUDECODE", "CLAUDE_SESSION_ID", "CLAUDE_MODEL")
    )


def active_host_from_env() -> str:
    if active_codex_session():
        return "codex"
    if active_claude_session():
        return "claude"
    return ""


def infer_host_bridge_resolution(command: str) -> dict:
    command_argv, command_parse_error = host_bridge_command_argv(command)
    command_display = command_argv[0] if command_argv else ""
    host = bridge_host_from_command(command, command_argv)

    return {
        "command": command,
        "source": "direct_invoke",
        "host": host,
        "capabilities_path": "",
        "command_parse_error": command_parse_error,
    }


def should_block_cross_host_bridge(command_argv: list[str], bridge_resolution: dict) -> bool:
    if not active_codex_session():
        return False
    if env_flag("AGENT_CREW_ALLOW_CROSS_HOST_BRIDGE") or env_flag("AGENT_CREW_ALLOW_CLAUDE_BRIDGE_IN_CODEX"):
        return False

    command_name = Path(command_argv[0]).name if command_argv else ""
    selected_host = str(bridge_resolution.get("host") or "").strip().lower()
    detected_hosts = bridge_hosts_from_command(str(bridge_resolution.get("command") or ""), command_argv)
    if not selected_host:
        selected_host = detected_hosts[0] if detected_hosts else ""
    return "claude" in detected_hosts or selected_host == "claude" or command_name == "claude-host-bridge"


def invoke_host_bridge(
    command: str,
    *,
    task_dir: Path,
    register: dict,
    project_root: Path,
    extra_env: dict | None = None,
    bridge_resolution: dict | None = None,
) -> dict:
    env = os.environ.copy()
    env.update({
        "AGENT_CREW_TASK_ID": register["task_id"],
        "AGENT_CREW_TASK_DIR": str(task_dir),
        "AGENT_CREW_HANDOFF_PATH": str(task_dir / "handoff.md"),
        "AGENT_CREW_RESULT_PATH": str(task_dir / "result.md"),
        "AGENT_CREW_PROJECT_ROOT": str(project_root),
        "AGENT_CREW_BRIDGE_OUTPUT_TAIL_PATH": str(task_dir / "context" / "host-bridge-output-tail.txt"),
    })
    if extra_env:
        env.update(extra_env)
    started = datetime.now(timezone.utc)
    interval_raw = os.environ.get("AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS", "10")
    try:
        interval = max(0.0, float(interval_raw))
    except ValueError:
        interval = 10.0

    direct_agent = bool((extra_env or {}).get("AGENT_CREW_AGENT_REQUEST_ID"))
    timeout_name = "AGENT_CREW_DIRECT_AGENT_BRIDGE_TIMEOUT_SECONDS" if direct_agent else "AGENT_CREW_BRIDGE_TIMEOUT_SECONDS"
    timeout_default = "60" if direct_agent else "1800"
    timeout_raw = os.environ.get(timeout_name) or os.environ.get("AGENT_CREW_BRIDGE_TIMEOUT_SECONDS") or timeout_default
    try:
        timeout_seconds = max(0.0, float(timeout_raw))
    except ValueError:
        timeout_seconds = float(timeout_default)

    bridge_resolution = bridge_resolution or infer_host_bridge_resolution(command)
    command_argv, command_parse_error = host_bridge_command_argv(command)
    command_display = command_argv[0] if command_argv else ""
    invocation_path = task_dir / "context" / "host-bridge-invocation.json"
    running_record = {
        "schema_version": 1,
        "task_id": register["task_id"],
        "command": command,
        "command_argv": command_argv,
        "command_display": command_display,
        "bridge_selection_source": str(bridge_resolution.get("source") or ""),
        "bridge_selection_host": str(bridge_resolution.get("host") or ""),
        "bridge_selection_capabilities_path": str(bridge_resolution.get("capabilities_path") or ""),
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": "",
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "timed_out": False,
        "timeout_seconds": timeout_seconds,
        "failure_class": "",
        "status": "running",
        "direct_agent": direct_agent,
        "output_observed": False,
        "output_tail_path": "context/host-bridge-output-tail.txt",
        "stall_class": "",
    }
    write_json(invocation_path, running_record)
    append_progress_log(
        task_dir,
        "HOST_BRIDGE_START",
        f"{command_display or 'host_bridge_command'} timeout={timeout_seconds:g}s",
    )
    append_progress(
        task_dir,
        {
            "ts": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "trace_id": trace_id_for(register, task_dir),
            "task_id": register["task_id"],
            "session_id": register.get("session_id", ""),
            "event": "HOST_BRIDGE_START",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "running",
            "detail": (
                f"host bridge started: {command_display or 'host_bridge_command'}; "
                f"timeout={timeout_seconds:g}s"
            ),
            "files": ["context/host-bridge-invocation.json"],
        },
    )

    def record_host_bridge_start_failed(stderr: str) -> dict:
        finished = datetime.now(timezone.utc)
        bridge_record = {
            **running_record,
            "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "returncode": 127,
            "stderr": stderr[-4000:],
            "failure_class": "host_bridge_start_failed",
            "status": "failed",
        }
        write_host_bridge_output_tail(task_dir, "", stderr)
        write_json(invocation_path, bridge_record)
        append_progress_log(task_dir, "HOST_BRIDGE_FINISHED", "host_bridge_start_failed")
        append_progress(
            task_dir,
            {
                "ts": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "trace_id": trace_id_for(register, task_dir),
                "task_id": register["task_id"],
                "session_id": register.get("session_id", ""),
                "event": "HOST_BRIDGE_FINISHED",
                "stage": 0,
                "agent": "",
                "attempt": 0,
                "status": "failed",
                "detail": "host_bridge_start_failed",
                "files": ["context/host-bridge-invocation.json"],
            },
        )
        append_tool_event(
            task_dir,
            trace_id=trace_id_for(register, task_dir),
            tool_name="host_bridge_command",
            action_summary=command,
            started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ended_at=finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
            status="failed",
            exit_code=127,
            failure_class="host_bridge_start_failed",
        )
        return bridge_record

    if command_parse_error:
        return record_host_bridge_start_failed(command_parse_error)
    if not command_argv:
        return record_host_bridge_start_failed("host bridge command is empty")
    if should_block_cross_host_bridge(command_argv, bridge_resolution):
        stderr = (
            "AGENT_CREW_BRIDGE_STATUS: current_session_required\n"
            "crew-runtime: refusing claude-host-bridge from an active Codex session; "
            "continue the handoff in the current Codex session or set "
            "AGENT_CREW_ALLOW_CROSS_HOST_BRIDGE=1 to override\n"
        )
        finished = datetime.now(timezone.utc)
        bridge_record = {
            **running_record,
            "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "returncode": 2,
            "stderr": stderr,
            "failure_class": "current_session_required",
            "status": "current_session_required",
            "output_observed": True,
        }
        write_host_bridge_output_tail(task_dir, "", stderr)
        write_json(invocation_path, bridge_record)
        append_progress_log(task_dir, "HOST_BRIDGE_FINISHED", "current_session_required")
        append_progress(
            task_dir,
            {
                "ts": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "trace_id": trace_id_for(register, task_dir),
                "task_id": register["task_id"],
                "session_id": register.get("session_id", ""),
                "event": "HOST_BRIDGE_FINISHED",
                "stage": 0,
                "agent": "",
                "attempt": 0,
                "status": "handoff_ready",
                "detail": "current_session_required",
                "files": ["context/host-bridge-invocation.json"],
            },
        )
        append_tool_event(
            task_dir,
            trace_id=trace_id_for(register, task_dir),
            tool_name="host_bridge_command",
            action_summary=command,
            started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ended_at=finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
            status="completed",
            exit_code=2,
            failure_class="current_session_required",
        )
        return bridge_record

    timed_out = False
    try:
        proc = subprocess.Popen(
            command_argv,
            shell=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
    except Exception as exc:
        return record_host_bridge_start_failed(str(exc))

    deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None
    last_child_output_preview = ""
    while True:
        wait_for = interval if interval > 0 else None
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                stdout, stderr = terminate_host_bridge(proc)
                returncode = 124
                break
            wait_for = min(wait_for, remaining) if wait_for is not None else remaining
        try:
            stdout, stderr = proc.communicate(timeout=wait_for)
            returncode = proc.returncode
            break
        except subprocess.TimeoutExpired as exc:
            child_output_preview = host_bridge_child_output_preview(
                getattr(exc, "output", ""),
                getattr(exc, "stderr", ""),
            )
            if child_output_preview and child_output_preview != last_child_output_preview:
                last_child_output_preview = child_output_preview
                append_progress_log(task_dir, "HOST_BRIDGE_OUTPUT", child_output_preview)
                append_progress(
                    task_dir,
                    {
                        "ts": utc_now_z(),
                        "trace_id": trace_id_for(register, task_dir),
                        "task_id": register["task_id"],
                        "session_id": register.get("session_id", ""),
                        "event": "HOST_BRIDGE_OUTPUT",
                        "stage": 0,
                        "agent": "",
                        "attempt": 0,
                        "status": "running",
                        "detail": child_output_preview,
                        "files": ["context/host-bridge-invocation.json"],
                    },
                )

            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                stdout, stderr = terminate_host_bridge(proc)
                returncode = 124
                break
            if interval > 0:
                print(render_wait_progress(register, task_dir), file=sys.stderr)

    finished = datetime.now(timezone.utc)
    stdout = stdout or ""
    stderr = stderr or ""
    output_observed = bool(stdout.strip() or stderr.strip())
    output_tail_path = write_host_bridge_output_tail(task_dir, stdout, stderr)
    stall_class = "no_output_startup_stall" if timed_out and not output_observed else ""
    current_session_required = host_bridge_current_session_required_output(
        stdout,
        stderr,
    )
    failure_class = "host_bridge_timeout" if timed_out else ("" if returncode == 0 else "host_bridge_command_failed")
    if current_session_required:
        failure_class = "current_session_required"
    bridge_record = {
        **running_record,
        "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "returncode": returncode,
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "timed_out": timed_out,
        "failure_class": failure_class,
        "status": (
            "current_session_required"
            if current_session_required
            else ("completed" if returncode == 0 else "failed")
        ),
        "output_observed": output_observed,
        "output_tail_path": output_tail_path or running_record["output_tail_path"],
        "stall_class": stall_class,
    }
    write_json(invocation_path, bridge_record)

    if timed_out:
        timeout_detail = f"host bridge exceeded {timeout_seconds:g}s timeout"
        if stall_class:
            timeout_detail += f"; stall_class={stall_class}"
        append_progress(
            task_dir,
            {
                "ts": utc_now_z(),
                "trace_id": trace_id_for(register, task_dir),
                "task_id": register["task_id"],
                "session_id": register.get("session_id", ""),
                "event": "HOST_BRIDGE_TIMEOUT",
                "stage": 0,
                "agent": "",
                "attempt": 0,
                "status": "blocked",
                "detail": timeout_detail,
                "files": ["context/host-bridge-invocation.json"],
            },
        )
    append_progress_log(task_dir, "HOST_BRIDGE_FINISHED", failure_class or "completed")
    append_progress(
        task_dir,
        {
            "ts": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "trace_id": trace_id_for(register, task_dir),
            "task_id": register["task_id"],
            "session_id": register.get("session_id", ""),
            "event": "HOST_BRIDGE_FINISHED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": (
                "handoff_ready"
                if current_session_required
                else ("completed" if returncode == 0 else "failed")
            ),
            "detail": stall_class or failure_class or "completed",
            "files": ["context/host-bridge-invocation.json"],
        },
    )
    append_tool_event(
        task_dir,
        trace_id=trace_id_for(register, task_dir),
        tool_name="host_bridge_command",
        action_summary=command,
        started_at=started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        ended_at=finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        status="completed" if returncode == 0 or current_session_required else "failed",
        exit_code=returncode,
        failure_class=failure_class,
    )
    return bridge_record


def terminate_host_bridge(proc: subprocess.Popen) -> tuple[str, str]:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        proc.terminate()
    try:
        stdout, stderr = proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        stdout, stderr = proc.communicate()
    return stdout or "", stderr or ""


def host_bridge_reported_blocked(bridge_record: dict) -> bool:
    output = "\n".join(
        str(bridge_record.get(key, "") or "")
        for key in ("stdout", "stderr")
    )
    return bool(re.search(r"(?im)^\s*(STATUS\s*:\s*blocked\b|BLOCKER\s*:)", output))


def host_bridge_current_session_required_output(stdout: str, stderr: str) -> bool:
    output = "\n".join([stdout or "", stderr or ""])
    return bool(
        re.search(
            r"(?im)^\s*AGENT_CREW_BRIDGE_STATUS:\s*current_session_required\s*$",
            output,
        )
        or "refusing nested Codex exec from an active Codex session" in output
    )


def host_bridge_current_session_required(bridge_record: dict) -> bool:
    if bridge_record.get("failure_class") == "current_session_required":
        return True
    return host_bridge_current_session_required_output(
        str(bridge_record.get("stdout", "") or ""),
        str(bridge_record.get("stderr", "") or ""),
    )


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def default_host_bridge_resolution(agent_crew_home: Path, project_root: Path) -> dict:
    if env_flag("AGENT_CREW_HOST_BRIDGE_ACTIVE"):
        return {
            "command": "",
            "source": "disabled.AGENT_CREW_HOST_BRIDGE_ACTIVE",
            "host": "",
            "capabilities_path": "",
        }
    if env_flag("AGENT_CREW_HOST_BRIDGE_DISABLE_DEFAULT") or env_flag("AGENT_CREW_DISABLE_DEFAULT_HOST_BRIDGE"):
        return {
            "command": "",
            "source": "disabled.AGENT_CREW_HOST_BRIDGE_DISABLE_DEFAULT",
            "host": "",
            "capabilities_path": "",
        }

    state_info = resolve_project_state(
        home=agent_crew_home,
        project_root=project_root,
        prefer_existing_legacy=True,
    )
    capabilities_path = Path(state_info["state_dir"]) / "capabilities.json"
    capabilities = load_json(capabilities_path, {})
    env_host = os.environ.get("AGENT_CREW_HOST", "").strip().lower()
    active_host = active_host_from_env()
    capabilities_host = str(capabilities.get("host") or "").strip().lower()
    capabilities_adapter = str(capabilities.get("adapter") or "").strip().lower()
    if env_host:
        host = env_host
        source = "env.AGENT_CREW_HOST"
    elif active_host:
        host = active_host
        source = "active_host_env"
    elif capabilities_host:
        host = capabilities_host
        source = "capabilities.host"
    elif capabilities_adapter:
        host = capabilities_adapter
        source = "capabilities.adapter"
    else:
        host = ""
        source = "none"

    bridge_name_by_host = {
        "codex": "codex-host-bridge",
        "claude": "claude-host-bridge",
    }
    bridge_name = bridge_name_by_host.get(host)
    if not bridge_name:
        return {
            "command": "",
            "source": source,
            "host": host,
            "capabilities_path": str(capabilities_path),
        }

    candidate = agent_crew_home / "adapters" / host / "bin" / bridge_name
    if candidate.is_file() and os.access(candidate, os.X_OK):
        command = str(candidate)
    else:
        command = ""

    return {
        "command": command,
        "source": source,
        "host": host,
        "capabilities_path": str(capabilities_path),
    }


def default_host_bridge_command(agent_crew_home: Path, project_root: Path) -> str:
    return str(default_host_bridge_resolution(agent_crew_home, project_root).get("command") or "")


def resolve_host_bridge(explicit_command: str | None, agent_crew_home: Path, project_root: Path) -> dict:
    if explicit_command:
        resolution = infer_host_bridge_resolution(explicit_command)
        resolution["source"] = "explicit_argument"
        return resolution
    env_command = os.environ.get("AGENT_CREW_HOST_BRIDGE_COMMAND", "").strip()
    if env_command:
        resolution = infer_host_bridge_resolution(env_command)
        resolution["source"] = "env.AGENT_CREW_HOST_BRIDGE_COMMAND"
        return resolution
    return default_host_bridge_resolution(agent_crew_home, project_root)


def resolve_host_bridge_command(explicit_command: str | None, agent_crew_home: Path, project_root: Path) -> str:
    return str(resolve_host_bridge(explicit_command, agent_crew_home, project_root).get("command") or "")


def asset_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def read_agent_registry(root: Path) -> dict[str, dict]:
    registry_path = root / "rules" / "agent-routing.md"
    agents: dict[str, dict] = {}
    if not registry_path.exists():
        return agents

    in_registry = False
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "## Agent Registry":
            in_registry = True
            continue
        if in_registry and line.startswith("## ") and line.strip() != "## Agent Registry":
            break
        if not in_registry or not line.startswith("|"):
            continue
        if "---" in line or line.startswith("| Agent "):
            continue

        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        name, scope, keywords, safe, reason = cells[:5]
        agents[name] = {
            "scope": scope,
            "keywords": keywords,
            "safe": safe.lower() == "yes",
            "reason": "" if reason == "—" else reason,
        }
    return agents


def _markdown_table_rows(text: str, section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    in_section = False
    section_level = 0
    for line in text.splitlines():
        heading_match = re.match(r"^(#{2,})\s+", line)
        if heading_match and re.search(re.escape(section), line, re.IGNORECASE):
            in_section = True
            section_level = len(heading_match.group(1))
            continue
        if in_section and heading_match and len(heading_match.group(1)) <= section_level:
            break
        if not in_section or not line.startswith("|"):
            continue
        if "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells:
            rows.append(cells)
    return rows


def _route_tokens(pattern: str) -> list[str]:
    if not pattern or pattern.strip().lower() == "(no match)":
        return []

    tokens: list[str] = []
    for raw in re.split(r"\s+OR\s+", pattern, flags=re.IGNORECASE):
        token = raw.strip().strip('"').strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def read_agent_routing_rules(root: Path) -> list[dict[str, str | list[str]]]:
    routing_path = root / "rules" / "agent-routing.md"
    if not routing_path.exists():
        return []

    rules: list[dict[str, str | list[str]]] = []
    for cells in _markdown_table_rows(routing_path.read_text(encoding="utf-8"), "Auto-Routing Rules"):
        if cells[:5] == ["Priority", "Pattern (case-insensitive, any word matches)", "Agent", "Confidence", "Reason shown to user"]:
            continue
        if len(cells) < 5:
            continue
        priority, pattern, agent, confidence, reason = cells[:5]
        tokens = _route_tokens(pattern)
        if not tokens or agent in {"— NONE —", "-", ""}:
            continue
        rules.append({
            "priority": priority,
            "agent": agent,
            "tokens": tokens,
            "confidence": confidence,
            "reason": reason,
        })

    def sort_key(rule: dict[str, str | list[str]]) -> float:
        try:
            return float(str(rule.get("priority") or "999"))
        except ValueError:
            return 999.0

    return sorted(rules, key=sort_key)


def looks_mutating(task: str) -> bool:
    return looks_mutating_task(task)


def contains_hangul(text: str) -> bool:
    return bool(HANGUL_PATTERN.search(text or ""))


def detect_issue_references(text: str) -> list[str]:
    refs: list[str] = []
    for pattern in (r"(?<![\w/])#(\d+)\b", r"/issues/(\d+)\b"):
        for match in re.finditer(pattern, text or ""):
            value = match.group(1)
            if value not in refs:
                refs.append(value)
    return refs


def detect_source_language(text: str) -> str:
    value = text or ""
    if HANGUL_PATTERN.search(value):
        return "ko"
    if JAPANESE_PATTERN.search(value):
        return "ja"
    if HAN_PATTERN.search(value):
        return "zh"
    if CYRILLIC_PATTERN.search(value):
        return "cyrillic"
    if ARABIC_PATTERN.search(value):
        return "arabic"
    if LATIN_EXTENDED_PATTERN.search(value):
        return "latin-extended"
    if NON_ASCII_PATTERN.search(value):
        return "unknown"
    return "en"


def ambiguous_input_reason(text: str) -> str:
    value = " ".join((text or "").strip().lower().split())
    if value in AMBIGUOUS_TASKS:
        return "short conversational shorthand requires prior-context binding"
    if len(value.split()) <= 3 and re.search(r"\b(this|that|it|before|again)\b", value):
        return "short ambiguous reference requires missing-context annotation"
    return ""


def input_normalization_metadata(raw_task: str, *, next_target: str) -> dict:
    source_language = detect_source_language(raw_task)
    ambiguity = ambiguous_input_reason(raw_task)
    translation_required = False
    normalization_required = False
    confidence = 0.9 if not ambiguity else 0.55
    reason = ["raw input is preserved verbatim; forced English normalization is disabled"]
    if ambiguity:
        reason.append(ambiguity)
    return {
        "schema_version": 1,
        "normalization_required": normalization_required,
        "source_language": source_language,
        "translation_required": translation_required,
        "ambiguity_flags": [ambiguity] if ambiguity else [],
        "confidence": confidence,
        "required_capabilities": required_capabilities_for_task(raw_task),
        "raw_input_ref": "handoff.md#RAW_INPUT",
        "downstream_route_hint": next_target,
        "normalization_sources": [],
        "reason": "; ".join(reason),
    }


def extract_comment_requirements(comments: list[dict]) -> list[str]:
    requirements: list[str] = []
    for comment in comments:
        body = str(comment.get("body", ""))
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("-", "*")):
                continue
            text = stripped.lstrip("-* ").strip()
            lowered = text.lower()
            if any(token in lowered for token in ("must", "should", "acceptance", "required", "supports", "records", "handles")):
                requirements.append(text)
    return requirements[:50]


def build_issue_ingestion_evidence(issue: dict, issue_number: str) -> dict:
    import hashlib

    all_comments = issue.get("comments") if isinstance(issue.get("comments"), list) else []
    comments = [
        comment
        for comment in all_comments
        if not comment.get("isMinimized") and not comment.get("minimizedReason")
    ]
    latest_comment_at = ""
    for comment in comments:
        created_at = str(comment.get("createdAt", ""))
        if created_at > latest_comment_at:
            latest_comment_at = created_at

    return {
        "schema_version": 1,
        "issue_number": issue.get("number", issue_number),
        "issue_url": issue.get("url", ""),
        "issue_title": issue.get("title", ""),
        "comments_ingested": True,
        "comment_count": len(comments),
        "latest_comment_at": latest_comment_at,
        "labels": [label.get("name", "") for label in issue.get("labels", []) if isinstance(label, dict)],
        "body_sha256": hashlib.sha256(str(issue.get("body", "")).encode("utf-8")).hexdigest(),
        "comment_urls": [comment.get("url", "") for comment in comments if comment.get("url")],
        "comment_derived_requirements": extract_comment_requirements(comments),
        "contradiction_review_required": len(comments) > 0,
        "planning_gate": "issue body and all non-minimized comments ingested before planning",
    }


def load_issue_payload(issue_number: str, repo: str = "") -> tuple[dict | None, str]:
    cmd = [
        "gh",
        "issue",
        "view",
        str(issue_number),
        "--comments",
        "--json",
        "number,title,body,comments,labels,url",
    ]
    if repo:
        cmd.extend(["--repo", repo])
    try:
        raw = subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE)
        data = json.loads(raw)
    except FileNotFoundError:
        return None, "gh executable not found"
    except subprocess.CalledProcessError as exc:
        return None, exc.stderr.strip() or "gh issue view failed"
    except Exception as exc:
        return None, f"failed to parse issue payload: {exc}"
    return data if isinstance(data, dict) else {}, ""


def record_issue_ingestion_evidence(task_dir: Path, raw_task: str) -> list[dict]:
    records: list[dict] = []
    for issue_number in detect_issue_references(raw_task):
        issue, error = load_issue_payload(issue_number)
        if issue is None:
            evidence = {
                "schema_version": 1,
                "issue_number": issue_number,
                "comments_ingested": False,
                "error": error,
                "planning_gate": "issue comment ingestion attempted before planning",
            }
        else:
            evidence = build_issue_ingestion_evidence(issue, issue_number)
        evidence_path = task_dir / "context" / f"issue-{issue_number}-ingestion.json"
        write_json(evidence_path, evidence)
        records.append({
            "issue_number": str(issue_number),
            "path": str(evidence_path),
            "comments_ingested": bool(evidence.get("comments_ingested")),
            "comment_count": int(evidence.get("comment_count") or 0),
        })
    return records


def auto_route_agent(task: str, agents: dict[str, dict]) -> tuple[str | None, str]:
    lowered = task.lower()

    for rule in read_agent_routing_rules(asset_root()):
        name = str(rule.get("agent") or "")
        tokens = rule.get("tokens") or []
        if name not in agents:
            continue
        if any(str(token).lower() in lowered or str(token) in task for token in tokens):
            reason = str(rule.get("reason") or f"matched {name} keywords")
            return name, f"{reason} ({name})"
    return None, "no direct-agent routing rule matched"


def agent_resolution_manifest_path(project_root: Path) -> Path:
    return project_root / ".agent-crew" / "agent-resolution.json"


def agent_layer_paths(project_root: Path, agent_crew_home: Path) -> list[tuple[str, Path]]:
    return [
        ("project", project_root / ".agent-crew" / "project" / "agents"),
        ("user", agent_crew_home / "user" / "agents"),
        ("system", agent_crew_home / "system" / "agents"),
    ]


def _parse_agent_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        item = re.match(r"^(\w[\w_-]*):\s*(.*)", line)
        if item:
            data[item.group(1)] = item.group(2).strip().strip("\"'")
    return data, match.group(2)


def _agent_description(frontmatter: dict[str, str], body: str) -> str:
    description = frontmatter.get("description", "").strip()
    if description:
        return re.sub(r"\s+", " ", description.lstrip("> ").strip())
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        if stripped:
            return re.sub(r"\s+", " ", stripped)[:180]
    return "No description available"


def _agent_file_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def discover_agent_candidates(agent_name: str, project_root: Path, agent_crew_home: Path) -> list[dict]:
    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for layer, base in agent_layer_paths(project_root, agent_crew_home):
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            frontmatter, body = _parse_agent_frontmatter(text)
            declared_name = (frontmatter.get("name") or path.stem).strip()
            if agent_name not in {path.stem, declared_name}:
                continue
            key = (layer, str(path.resolve()))
            if key in seen:
                continue
            seen.add(key)
            stat = path.stat()
            candidates.append(
                {
                    "agent_name": agent_name,
                    "declared_name": declared_name,
                    "layer": layer,
                    "friendly_label": f"{AGENT_LAYER_LABELS[layer]} {agent_name}",
                    "scope": AGENT_LAYER_SCOPES[layer],
                    "path": str(path.resolve()),
                    "description": _agent_description(frontmatter, body),
                    "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "fingerprint": _agent_file_fingerprint(path),
                }
            )
    return candidates


def load_agent_resolution_manifest(project_root: Path) -> dict:
    path = agent_resolution_manifest_path(project_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_agent_resolution_manifest(project_root: Path, candidate: dict) -> None:
    path = agent_resolution_manifest_path(project_root)
    payload = load_agent_resolution_manifest(project_root)
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
    decisions = [item for item in decisions if isinstance(item, dict)]
    decisions = [
        item for item in decisions
        if item.get("agent_name") != candidate["agent_name"]
    ]
    decisions.append(
        {
            "agent_name": candidate["agent_name"],
            "layer": candidate["layer"],
            "path": candidate["path"],
            "fingerprint": candidate["fingerprint"],
            "decided_at": utc_now_z(),
        }
    )
    write_json(
        path,
        {
            "schema_version": "agent-crew.agent-resolution.v1",
            "decisions": sorted(decisions, key=lambda item: str(item.get("agent_name", ""))),
        },
    )


def _candidate_by_layer(candidates: list[dict], layer: str | None) -> dict | None:
    if not layer:
        return None
    matches = [candidate for candidate in candidates if candidate["layer"] == layer]
    return matches[0] if len(matches) == 1 else None


def _candidate_from_manifest(agent_name: str, candidates: list[dict], project_root: Path) -> tuple[dict | None, str]:
    payload = load_agent_resolution_manifest(project_root)
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
    for item in decisions:
        if not isinstance(item, dict) or item.get("agent_name") != agent_name:
            continue
        for candidate in candidates:
            if candidate["path"] == item.get("path") and candidate["fingerprint"] == item.get("fingerprint"):
                return candidate, "saved"
        return None, "stale"
    return None, ""


def render_agent_candidate_selection(agent_name: str, candidates: list[dict], reason: str = "") -> str:
    status = "AGENT_DECISION_STALE" if reason == "stale" else "selection_required"
    lines = [
        f"STATUS: {status}",
        f"AGENT: {agent_name}",
        "AGENT_CONFLICT: same-name agent definitions require an explicit choice.",
        "Choose one candidate for this run with --agent-layer <project|user|system>, "
        "or save a project decision with --save-agent-layer <project|user|system>.",
        "",
        "Candidates:",
    ]
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"{index}. {candidate['friendly_label']}",
                f"   layer: {candidate['layer']}",
                f"   path: {candidate['path']}",
                f"   scope: {candidate['scope']}",
                f"   description: {candidate['description']}",
                f"   mtime: {candidate['mtime']}",
                f"   fingerprint: {candidate['fingerprint']}",
            ]
        )
    return "\n".join(lines) + "\n"


def resolve_agent_definition_choice(
    agent_name: str,
    project_root: Path,
    agent_crew_home: Path,
    *,
    agent_layer: str | None = None,
    save_agent_layer: str | None = None,
) -> tuple[str, dict | None, str]:
    candidates = discover_agent_candidates(agent_name, project_root, agent_crew_home)
    selected_layer = save_agent_layer or agent_layer
    if selected_layer:
        candidate = _candidate_by_layer(candidates, selected_layer)
        if not candidate:
            return "selection_required", None, render_agent_candidate_selection(agent_name, candidates)
        if save_agent_layer:
            save_agent_resolution_manifest(project_root, candidate)
            return "saved", candidate, ""
        return "one_shot", candidate, ""
    if len(candidates) <= 1:
        return "single" if candidates else "registry_only", candidates[0] if candidates else None, ""
    candidate, manifest_status = _candidate_from_manifest(agent_name, candidates, project_root)
    if candidate:
        return manifest_status, candidate, ""
    return (
        "stale" if manifest_status == "stale" else "selection_required",
        None,
        render_agent_candidate_selection(agent_name, candidates, reason=manifest_status),
    )


def command_run(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    state_info = resolve_project_state(
        home=agent_crew_home,
        project_root=project_root,
        ensure=True,
        migrate_legacy=True,
    )
    project_name = state_info["project_name"]
    state_dir = Path(state_info["state_dir"])
    tasks_dir = state_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    now_z = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    session_id = now.strftime("%Y%m%d-%H%M%S")
    task_id = f"{session_id}-0"
    index = 0
    while (tasks_dir / task_id).exists():
        index += 1
        task_id = f"{session_id}-{index}"

    task_dir = tasks_dir / task_id
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    raw_task = args.task
    normalization_metadata = input_normalization_metadata(raw_task, next_target="crew run supervisor")
    task = raw_task

    fake_completed_requested = args.fake_host_result == "completed"
    fake_quality_blocked = fake_completed_requested and looks_mutating_task(task)
    bridge_resolution = resolve_host_bridge(args.host_bridge_command, agent_crew_home, project_root)
    bridge_command = str(bridge_resolution.get("command") or "")
    if fake_completed_requested and not fake_quality_blocked:
        result_status = "completed"
    elif bridge_command or fake_quality_blocked:
        result_status = "blocked"
    else:
        result_status = "handoff_ready"
    current_phase = result_status
    blocked_by = []
    if fake_quality_blocked:
        blocked_by = ["missing_quality_loop_pipeline"]
    elif result_status == "blocked":
        blocked_by = ["host_bridge_not_invoked"]
    quality_next = (
        "NEXT: A mutating implementation task can only be auto-completed after "
        "the host runtime leaves pipeline-level quality-loop evidence in "
        "pipeline.json and progress.buffer.jsonl.\n"
    )

    if fake_quality_blocked:
        host_bridge_status = "quality_blocked"
    elif result_status == "completed":
        host_bridge_status = "fake_completed"
    elif result_status == "handoff_ready":
        host_bridge_status = "internal_handoff_ready"
    else:
        host_bridge_status = "pending" if bridge_command else "not_invoked"
    blocked_next = host_bridge_next_line(task_dir, task_id, bool(bridge_command))

    register = {
        "schema_version": 1,
        "task_id": task_id,
        "session_id": session_id,
        "task": task,
        "branch": f"crew/{slug(task)}",
        "project_root": str(project_root),
        "project_name": project_name,
        "project_state_key": state_info["project_state_key"],
        "state_dir": str(state_dir),
        "task_dir": str(task_dir),
        "execution_mode": "single",
        "current_phase": current_phase,
        "approval_status": "not_required",
        "verification_status": "failed" if fake_quality_blocked else "skipped",
        "pipeline_path": str(task_dir / "pipeline.json"),
        "handoff_path": str(task_dir / "handoff.md"),
        "progress_log_path": str(task_dir / "progress.log"),
        "progress_buffer_path": str(task_dir / "progress.buffer.jsonl"),
        "result_path": str(task_dir / "result.md"),
        "blocked_by": blocked_by,
        "host_bridge_status": host_bridge_status,
        "repair_command": f"crew repair {task_id} --status completed --note \"<summary>\"",
    }

    pipeline = {
        "schema_version": 1,
        "task": task,
        "stages": ["supervisor"],
        "completed_stages": 1 if result_status == "completed" else 0,
        "stage_agent_status": {
            "1": {
                "supervisor": "completed" if result_status == "completed" else "blocked"
            }
        },
    }

    handoff = (
        f"# Supervisor Handoff\n\n"
        f"TASK_ID: {task_id}\n"
        f"TASK: {task}\n"
        f"PROJECT_ROOT: {project_root}\n"
        f"MODE: fake-host\n" if args.fake_host_result else
        f"# Supervisor Handoff\n\n"
        f"TASK_ID: {task_id}\n"
        f"TASK: {task}\n"
        f"PROJECT_ROOT: {project_root}\n"
        f"MODE: native-cli\n"
        f"STATUS: {result_status}\n"
        f"REPAIR: crew repair {task_id} --status completed --note \"<summary>\"\n"
    )
    if result_status == "blocked":
        handoff += "BLOCKER: host AI bridge has not completed this handoff\n"

    result = (
        f"# {task}\n\n"
        f"STATUS: {result_status}\n"
        f"TASK_ID: {task_id}\n"
        f"BRANCH: {register['branch']}\n"
    )
    if result_status == "handoff_ready":
        result += "HOST_BRIDGE: internal_handoff_ready\n"
        result += blocked_next
    elif result_status == "blocked":
        if fake_quality_blocked:
            result += "BLOCKER: missing_quality_loop_pipeline\n"
            result += (
                "DETAIL: fake-host completion for mutating implementation "
                "tasks is blocked unless the quality loop is actually recorded.\n"
            )
            result += quality_next
        else:
            result += "BLOCKER: host AI bridge has not completed this handoff\n"
        result += blocked_next

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    issue_ingestions = record_issue_ingestion_evidence(task_dir, raw_task)
    if issue_ingestions:
        register["issue_comment_ingestion"] = issue_ingestions
        write_json(task_dir / "register.json", register)
    (task_dir / "handoff.md").write_text(handoff, encoding="utf-8")
    (task_dir / "result.md").write_text(result, encoding="utf-8")
    progress_status = "completed" if result_status == "completed" else "in_progress"
    if result_status == "blocked":
        progress_status = "failed"
    (task_dir / "progress.log").write_text(
        f"{now_z} | STARTED | {task}\n"
        f"{now_z} | STATUS | {result_status}\n",
        encoding="utf-8",
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": now_z,
            "trace_id": f"{session_id}.{task_id}.0.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STARTED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "started",
            "detail": task,
            "files": [],
        },
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": utc_now_z(),
            "trace_id": f"{session_id}.{task_id}.0.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STATUS",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": progress_status,
            "detail": result_status,
            "files": [],
        },
    )
    append_delegation(
        task_dir,
        trace_id=f"{session_id}.{task_id}.0.0",
        span_id=f"{task_id}:supervisor",
        parent_span_id="",
        agent_role="supervisor",
        unit_id=task_id,
        delegated_by="crew-runtime",
        status=result_status,
    )

    print(render_start_banner(register, task_dir), flush=True)

    if fake_quality_blocked:
        quality_result = check_quality_loop(task_dir, target_status="completed")
        mark_quality_loop_blocked(
            task_dir,
            register,
            pipeline,
            quality_result,
            "pipeline.json",
        )

    if result_status == "blocked" and bridge_command:
        bridge_record = invoke_host_bridge(
            bridge_command,
            task_dir=task_dir,
            register=register,
            project_root=project_root,
            bridge_resolution=bridge_resolution,
        )
        write_json(task_dir / "context" / "host-bridge-invocation.json", bridge_record)
        if host_bridge_current_session_required(bridge_record):
            now = utc_now_z()
            current_next = host_bridge_current_session_next_line(task_dir, task_id)
            register.update(
                {
                    "current_phase": "handoff_ready",
                    "blocked_by": [],
                    "host_bridge_status": "current_session_required",
                    "host_bridge_failure_reason": "nested_codex_current_session_required",
                    "host_bridge_completion_path": str(task_dir / "context" / "host-bridge-invocation.json"),
                    "host_bridge_completed_at": now,
                }
            )
            write_json(task_dir / "register.json", register)

            handoff = (
                f"# Supervisor Handoff\n\n"
                f"TASK_ID: {task_id}\n"
                f"TASK: {task}\n"
                f"PROJECT_ROOT: {project_root}\n"
                f"MODE: native-cli\n"
                f"STATUS: handoff_ready\n"
                f"HOST_BRIDGE: current_session_required\n"
                f"REPAIR: crew repair {task_id} --status completed --note \"<summary>\"\n"
            )

            result = (
                f"# {task}\n\n"
                "STATUS: handoff_ready\n"
                f"TASK_ID: {task_id}\n"
                f"BRANCH: {register['branch']}\n"
            )
            result += "HOST_BRIDGE: current_session_required\n"
            result += current_next

            (task_dir / "handoff.md").write_text(handoff, encoding="utf-8")
            (task_dir / "result.md").write_text(result, encoding="utf-8")
            append_progress_log(
                task_dir,
                "HOST_BRIDGE_CURRENT_SESSION",
                "current Codex session must complete crew:run handoff",
            )
            append_progress_log(task_dir, "STATUS", "handoff_ready")
            append_progress(
                task_dir,
                {
                    "ts": now,
                    "trace_id": trace_id_for(register, task_dir),
                    "task_id": task_id,
                    "session_id": session_id,
                    "event": "HOST_BRIDGE_CURRENT_SESSION",
                    "stage": 0,
                    "agent": "",
                    "attempt": 0,
                    "status": "handoff_ready",
                    "detail": "current Codex session must complete crew:run handoff",
                    "files": ["handoff.md", "register.json", "result.md"],
                },
            )
            print(f"TASK_ID: {task_id}")
            print(f"TASK_DIR: {task_dir}")
            print("STATUS: handoff_ready")
            print("HOST_BRIDGE: current_session_required")
            print(current_next.rstrip())
            return 0

        if bridge_record["returncode"] == 0 and not host_bridge_reported_blocked(bridge_record):
            latest_register = load_json(task_dir / "register.json", register)
            latest_pipeline = load_json(task_dir / "pipeline.json", pipeline)
            if looks_mutating_task(str(latest_register.get("task", args.task))):
                quality_result = check_quality_loop(task_dir, target_status="completed")
                if not quality_result["passed"]:
                    mark_quality_loop_blocked(
                        task_dir,
                        latest_register,
                        latest_pipeline,
                        quality_result,
                        "context/host-bridge-invocation.json",
                    )
                    print(f"TASK_ID: {task_id}")
                    print(f"TASK_DIR: {task_dir}")
                    print("STATUS: blocked")
                    print("BLOCKER: missing_quality_loop_pipeline")
                    print("HOST_BRIDGE: quality_blocked")
                    return 3

                write_json(task_dir / "context" / "quality-loop-runtime-check.json", quality_result)
                latest_register = load_json(task_dir / "register.json", latest_register)
                latest_pipeline = load_json(task_dir / "pipeline.json", latest_pipeline)
                mark_auto_completed(
                    task_dir,
                    latest_register,
                    latest_pipeline,
                    bridge_record,
                    "Automatic host bridge command completed successfully after quality-loop validation.",
                    preserve_quality_state=True,
                )
                print(f"TASK_ID: {task_id}")
                print(f"TASK_DIR: {task_dir}")
                print("STATUS: completed")
                print("HOST_BRIDGE: auto_completed")
                return 0

            mark_auto_completed(
                task_dir,
                register,
                pipeline,
                bridge_record,
                "Automatic host bridge command completed successfully.",
            )
            print(f"TASK_ID: {task_id}")
            print(f"TASK_DIR: {task_dir}")
            print("STATUS: completed")
            print("HOST_BRIDGE: auto_completed")
            return 0

        register["host_bridge_status"] = "failed"
        register["host_bridge_failure_reason"] = host_bridge_failure_reason(bridge_record)
        failure_detail = host_bridge_failure_detail(bridge_record)
        if failure_detail:
            register["host_bridge_failure_detail"] = failure_detail
        if bridge_record.get("timed_out") and bridge_record.get("stall_class"):
            register["host_bridge_stall_class"] = bridge_record["stall_class"]
        register["host_bridge_completion_path"] = str(task_dir / "context" / "host-bridge-invocation.json")
        write_json(task_dir / "register.json", register)

    print(f"TASK_ID: {task_id}")
    print(f"TASK_DIR: {task_dir}")
    print(f"STATUS: {result_status}")
    if result_status == "handoff_ready":
        print("HOST_BRIDGE: internal_handoff_ready")
        print(blocked_next.rstrip())
        return 0
    if result_status == "blocked":
        if fake_quality_blocked:
            print("BLOCKER: missing_quality_loop_pipeline")
            print(quality_next.rstrip())
        elif register.get("host_bridge_failure_reason") == "bridge_timeout":
            print("BLOCKER: host AI bridge timed out before completing this handoff")
            print("NEXT: Inspect context/host-bridge-invocation.json and resume or repair the handoff.")
        elif register.get("host_bridge_failure_reason") == "host_bridge_start_failed":
            print("BLOCKER: host bridge failed to start (host_bridge_start_failed)")
            if register.get("host_bridge_failure_detail"):
                print(f"DETAIL: {register['host_bridge_failure_detail']}")
            print("NEXT: Inspect context/host-bridge-invocation.json and fix the bridge command.")
        else:
            print("BLOCKER: host AI bridge has not completed this handoff")
            print(blocked_next.rstrip())
        return 3
    return 0


def command_agent(args: argparse.Namespace) -> int:
    root = asset_root(args.asset_root)
    agents = read_agent_registry(root)
    raw_args = list(args.agent_args or [])

    if not raw_args and not args.list and not args.routing:
        print("usage: crew-runtime.py agent [--list|--routing|agent-name task|task]")
        return 0

    if args.list:
        print(f"Available direct agents (source: {root / 'rules' / 'agent-routing.md'})")
        for name in sorted(agents):
            if agents[name]["safe"]:
                print(f"  {name}: {agents[name]['scope']}")
        return 0

    if args.routing:
        registry_path = root / "rules" / "agent-routing.md"
        text = registry_path.read_text(encoding="utf-8")
        start = text.find("## Auto-Routing Rules")
        end = text.find("### Matching semantics", start)
        print(text[start:end].rstrip() if start >= 0 and end > start else text)
        return 0

    if raw_args[0] in agents:
        agent_name = raw_args[0]
        task = " ".join(raw_args[1:]).strip()
        route_reason = "explicit direct-agent request"
    else:
        task = " ".join(raw_args).strip()
        agent_name, route_reason = auto_route_agent(task, agents)

    if not task:
        print("crew agent: task description is required", file=sys.stderr)
        return 2

    intended_agent_name = agent_name
    normalization_metadata = input_normalization_metadata(
        task,
        next_target=intended_agent_name or "direct-agent auto-routing",
    )

    if agent_name is None:
        print("crew agent: cannot auto-route this task; specify an agent name", file=sys.stderr)
        return 2

    info = agents.get(agent_name)
    if not info:
        print(f"crew agent: unknown agent '{agent_name}'", file=sys.stderr)
        return 2
    if not info["safe"]:
        reason = info["reason"] or "agent requires supervisor context"
        print(f"crew agent: '{agent_name}' cannot be invoked directly. Reason: {reason}", file=sys.stderr)
        return 2

    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    resolution_status, selected_agent, selection_message = resolve_agent_definition_choice(
        agent_name,
        project_root,
        agent_crew_home,
        agent_layer=getattr(args, "agent_layer", None),
        save_agent_layer=getattr(args, "save_agent_layer", None),
    )
    if selected_agent is None and resolution_status in {"selection_required", "stale"}:
        print(selection_message, end="")
        return 2

    state_info = resolve_project_state(
        home=agent_crew_home,
        project_root=project_root,
        ensure=True,
        migrate_legacy=True,
    )
    project_name = state_info["project_name"]
    state_dir = Path(state_info["state_dir"])
    requests_dir = state_dir / "agent-requests"
    requests_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    request_id = f"agent-{now.strftime('%Y%m%d-%H%M%S')}-0"
    index = 0
    while (requests_dir / request_id).exists():
        index += 1
        request_id = f"agent-{now.strftime('%Y%m%d-%H%M%S')}-{index}"

    request_dir = requests_dir / request_id
    bridge_resolution = resolve_host_bridge(args.host_bridge_command, agent_crew_home, project_root)
    bridge_command = str(bridge_resolution.get("command") or "")
    request = {
        "schema_version": 1,
        "request_id": request_id,
        "agent": agent_name,
        "task": task,
        "route_reason": route_reason,
        "project_root": str(project_root),
        "project_name": project_name,
        "project_state_key": state_info["project_state_key"],
        "state_dir": str(state_dir),
        "request_dir": str(request_dir),
        "agent_resolution": {
            "status": resolution_status,
            "selected_agent": selected_agent,
        },
        "status": "handoff_ready",
        "host_bridge_status": "pending" if bridge_command else "not_invoked",
        "created_at": now.isoformat(),
        "progress_log_path": str(request_dir / "progress.log"),
        "progress_buffer_path": str(request_dir / "progress.buffer.jsonl"),
    }
    handoff = (
        f"# Direct Agent Handoff\n\n"
        f"REQUEST_ID: {request_id}\n"
        f"AGENT: {agent_name}\n"
        f"AGENT_RESOLUTION: {resolution_status}\n"
        f"TASK: {task}\n"
        f"PROJECT_ROOT: {project_root}\n"
        f"MODE: host-prompt-bridge\n"
        f"STATUS: handoff_ready\n"
        f"NEXT: Invoke crew:agent {agent_name!r} with this task inside the host prompt runtime.\n"
    )
    if selected_agent:
        handoff += (
            "\n## Selected Agent Definition\n\n"
            f"- layer: {selected_agent['layer']}\n"
            f"- label: {selected_agent['friendly_label']}\n"
            f"- path: {selected_agent['path']}\n"
            f"- scope: {selected_agent['scope']}\n"
            f"- description: {selected_agent['description']}\n"
            f"- fingerprint: {selected_agent['fingerprint']}\n"
        )

    write_json(request_dir / "request.json", request)
    (request_dir / "handoff.md").write_text(handoff, encoding="utf-8")
    append_progress_log(request_dir, "DIRECT_AGENT_REQUEST", f"{agent_name}: handoff_ready")
    append_progress(
        request_dir,
        {
            "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "trace_id": trace_id_for({"task_id": request_id}, request_dir),
            "task_id": request_id,
            "session_id": "",
            "event": "DIRECT_AGENT_REQUEST",
            "stage": 0,
            "agent": agent_name,
            "attempt": 0,
            "status": "handoff_ready",
            "detail": route_reason,
            "files": ["request.json", "handoff.md"],
        },
    )

    print(f"AGENT_REQUEST_ID: {request_id}")
    print(f"AGENT: {agent_name}")
    print(f"AGENT_RESOLUTION: {resolution_status}")
    if selected_agent:
        print(f"AGENT_LAYER: {selected_agent['layer']}")
        print(f"AGENT_PATH: {selected_agent['path']}")
    print(f"REQUEST_DIR: {request_dir}")

    bridge_invocation_path = request_dir / "context" / "host-bridge-invocation.json"
    bridge_completion_path = request_dir / "context" / "host-bridge-completion.json"
    if bridge_command:
        bridge_record = invoke_host_bridge(
            bridge_command,
            task_dir=request_dir,
            register={"task_id": request_id},
            project_root=project_root,
            bridge_resolution=bridge_resolution,
            extra_env={
                "AGENT_CREW_AGENT_NAME": agent_name,
                "AGENT_CREW_AGENT_REQUEST_ID": request_id,
                "AGENT_CREW_REQUEST_DIR": str(request_dir),
                "AGENT_CREW_SELECTED_AGENT_PATH": str(selected_agent.get("path", "")) if selected_agent else "",
                "AGENT_CREW_SELECTED_AGENT_LAYER": str(selected_agent.get("layer", "")) if selected_agent else "",
            },
        )
        write_json(bridge_invocation_path, bridge_record)
        if bridge_record["returncode"] == 0 and not host_bridge_reported_blocked(bridge_record):
            now = utc_now_z()
            write_json(bridge_completion_path, bridge_record)
            result_path = request_dir / "result.md"
            if not result_path.exists():
                result_path.write_text(
                    "# Direct Agent Result\n\n"
                    f"REQUEST_ID: {request_id}\n"
                    f"AGENT: {agent_name}\n"
                    "STATUS: completed\n"
                    f"COMPLETED_AT: {now}\n"
                    "FILES: none\n\n"
                    + render_bridge_output_section(bridge_record).lstrip(),
                    encoding="utf-8",
                )
            request.update(
                {
                    "status": "auto_completed",
                    "host_bridge_status": "auto_completed",
                    "host_bridge_completion_path": str(bridge_completion_path),
                    "host_bridge_completed_at": now,
                }
            )
            write_json(request_dir / "request.json", request)
            print("STATUS: completed")
            print("HOST_BRIDGE: auto_completed")
            return 0

        if host_bridge_current_session_required(bridge_record):
            now = utc_now_z()
            request.update(
                {
                    "status": "handoff_ready",
                    "host_bridge_status": "current_session_required",
                    "host_bridge_failure_reason": "nested_codex_current_session_required",
                    "host_bridge_completion_path": str(bridge_invocation_path),
                    "host_bridge_completed_at": now,
                }
            )
            write_json(request_dir / "request.json", request)
            append_progress_log(
                request_dir,
                "HOST_BRIDGE_CURRENT_SESSION",
                "current Codex session must complete direct-agent handoff",
            )
            append_progress(
                request_dir,
                {
                    "ts": now,
                    "trace_id": trace_id_for({"task_id": request_id}, request_dir),
                    "task_id": request_id,
                    "session_id": "",
                    "event": "HOST_BRIDGE_CURRENT_SESSION",
                    "stage": 0,
                    "agent": agent_name,
                    "attempt": 0,
                    "status": "handoff_ready",
                    "detail": "current Codex session must complete direct-agent handoff",
                    "files": ["handoff.md", "request.json"],
                },
            )
            print("STATUS: handoff_ready")
            print("HOST_BRIDGE: current_session_required")
            print(
                "NEXT: Continue this read-only direct-agent handoff in the current "
                f"Codex session from {request_dir / 'handoff.md'}."
            )
            return 0

        request.update(
            {
                "host_bridge_status": "failed",
                "host_bridge_completion_path": str(bridge_invocation_path),
                "host_bridge_completed_at": utc_now_z(),
            }
        )
        request["host_bridge_failure_reason"] = host_bridge_failure_reason(bridge_record)
        failure_detail = host_bridge_failure_detail(bridge_record)
        if failure_detail:
            request["host_bridge_failure_detail"] = failure_detail
        if bridge_record.get("timed_out") and bridge_record.get("stall_class"):
            request["host_bridge_stall_class"] = bridge_record["stall_class"]
        write_json(request_dir / "request.json", request)
        print("STATUS: blocked")
        if bridge_record.get("timed_out"):
            print("BLOCKER: host AI bridge timed out before completing this agent request")
        elif request.get("host_bridge_failure_reason") == "host_bridge_start_failed":
            print("BLOCKER: host bridge failed to start (host_bridge_start_failed)")
            if request.get("host_bridge_failure_detail"):
                print(f"DETAIL: {request['host_bridge_failure_detail']}")
        else:
            print("BLOCKER: host AI bridge has not completed this agent request")
        print(
            "NEXT: Continue with "
            f"{request_dir / 'handoff.md'} using your host bridge or run --host-bridge-command for one-off execution."
        )
        return 3

    print("STATUS: handoff_ready")
    return 0


def command_issue_ingest(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    state_info = resolve_project_state(
        home=agent_crew_home,
        project_root=project_root,
        prefer_existing_legacy=True,
    )
    project_name = state_info["project_name"]
    state_dir = Path(state_info["state_dir"])

    issue, error = load_issue_payload(str(args.issue_number), repo=args.repo)
    if issue is None:
        print(f"crew issue-ingest: {error}", file=sys.stderr)
        return 1

    evidence = build_issue_ingestion_evidence(issue, str(args.issue_number))

    output_path = None
    if args.task_id:
        output_path = state_dir / "tasks" / args.task_id / "context" / f"issue-{args.issue_number}-ingestion.json"
        write_json(output_path, evidence)
    elif args.output:
        output_path = Path(args.output)
        write_json(output_path, evidence)

    if args.format == "json":
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    else:
        print(f"ISSUE: {evidence['issue_number']}")
        print(f"COMMENTS_INGESTED: {str(evidence['comments_ingested']).lower()}")
        print(f"COMMENT_COUNT: {evidence['comment_count']}")
        print(f"LATEST_COMMENT_AT: {evidence['latest_comment_at']}")
        if output_path:
            print(f"EVIDENCE: {output_path}")
    return 0


def build_relay_prompt(manifest: dict, context: dict, prompt_text: str) -> str:
    from_task = context.get("from_task") if isinstance(context.get("from_task"), dict) else {}
    task_text = prompt_text or str(from_task.get("task") or "").strip()
    if not task_text:
        task_text = "Continue from the packaged context."

    sections = [
        "# agent-crew Relay Prompt",
        "",
        "## ROLE",
        f"You are the target AI session for a local agent-crew relay package in `{manifest['mode']}` mode.",
        "",
        "## ROUTING",
        f"SOURCE_HOST: {manifest['source_host']}",
        f"TARGET_HOST: {manifest['target_host']}",
        f"PROJECT_ROOT: {context['project_root']}",
        f"BRANCH: {context.get('branch') or 'unknown'}",
        "",
        "## TASK",
        task_text,
        "",
        "## CONTEXT",
        f"Relay ID: {manifest['relay_id']}",
        f"From task: {manifest.get('from_task') or 'none'}",
        "Paths:",
    ]
    paths = context.get("paths") or []
    sections.extend([f"- {path}" for path in paths] if paths else ["- none"])
    sections.extend(
        [
            "",
            "Git status:",
            "```text",
            context.get("git_status") or "clean or unavailable",
            "```",
        ]
    )

    if from_task:
        sections.extend(
            [
                "",
                "Existing task context:",
                "```text",
                from_task.get("summary") or "",
                "```",
            ]
        )

    sections.extend(
        [
            "",
            "## INSTRUCTIONS",
            "- Treat this as a local handoff package, not permission to operate on external state.",
            "- Do not execute remote, push, deploy, merge, or destructive actions unless the user explicitly approves them in your session.",
            "- Preserve the project architecture and constraints already described in this package.",
            "",
            "## EXPECTED_OUTPUT",
            "- Start with the concrete answer, plan, or code review result requested by TASK.",
            "- Mention any missing context explicitly instead of guessing.",
            "",
        ]
    )
    return "\n".join(sections)


def load_relay_task_context(state_dir: Path, task_id: str) -> tuple[dict, str]:
    if not task_id:
        return {}, ""

    task_dir = state_dir / "tasks" / task_id
    if not task_dir.is_dir():
        return {}, f"crew relay: task not found: {task_id}"

    register = load_json(task_dir / "register.json", {})
    snippets = []
    for name in ("handoff.md", "result.md"):
        snippet = text_snippet(task_dir / name)
        if snippet:
            snippets.append(f"--- {name} ---\n{snippet}")

    return {
        "task_id": task_id,
        "task": str(register.get("task") or "").strip(),
        "task_dir": str(task_dir),
        "summary": "\n\n".join(snippets),
    }, ""


def create_relay_package(
    *,
    project_root: Path,
    agent_crew_home: Path,
    target_host: str,
    mode: str,
    prompt_text: str,
    paths: list[str] | None = None,
    from_task_id: str = "",
    copy_requested: bool = False,
) -> tuple[dict, str]:
    state_info = resolve_project_state(
        home=agent_crew_home,
        project_root=project_root,
        ensure=True,
        migrate_legacy=True,
    )
    state_dir = Path(state_info["state_dir"])
    relays_dir = state_dir / "relays"
    relays_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    session_id = now.strftime("%Y%m%d-%H%M%S")
    relay_id = f"relay-{session_id}-0"
    index = 0
    while (relays_dir / relay_id).exists():
        index += 1
        relay_id = f"relay-{session_id}-{index}"

    from_task, error = load_relay_task_context(state_dir, from_task_id)
    if error:
        return {}, error

    relay_dir = relays_dir / relay_id
    relay_dir.mkdir(parents=True)
    relay_paths = [str(path) for path in (paths or [])]
    source_host = os.environ.get("AGENT_CREW_HOST", "").strip() or active_host_from_env() or "unknown"
    manifest = {
        "schema_version": 1,
        "relay_id": relay_id,
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_host": source_host,
        "target_host": target_host,
        "mode": mode,
        "project_root": str(project_root),
        "project_state_key": state_info["project_state_key"],
        "state_dir": str(state_dir),
        "relay_dir": str(relay_dir),
        "manifest_file": str(relay_dir / "manifest.json"),
        "context_file": str(relay_dir / "context.json"),
        "prompt_file": str(relay_dir / "prompt.md"),
        "copy_file": str(relay_dir / "copy.txt"),
        "from_task": from_task_id,
        "paths": relay_paths,
        "copy_requested": bool(copy_requested),
        "auto_execute": False,
    }
    context = {
        "schema_version": 1,
        "project_root": str(project_root),
        "project_name": state_info["project_name"],
        "branch": git_branch(project_root),
        "git_status": git_status_short(project_root),
        "paths": relay_paths,
        "from_task": from_task,
    }
    prompt = build_relay_prompt(manifest, context, prompt_text)

    write_json(relay_dir / "manifest.json", manifest)
    write_json(relay_dir / "context.json", context)
    (relay_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    (relay_dir / "copy.txt").write_text(prompt, encoding="utf-8")

    copied = copy_to_clipboard(prompt) if copy_requested else False
    return {
        "manifest": manifest,
        "context": context,
        "prompt": prompt,
        "relay_dir": relay_dir,
        "copied": copied,
    }, ""


def interact_delivery_command_template(host: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(host or "").upper()).strip("_")
    if normalized:
        value = os.environ.get(f"AGENT_CREW_INTERACT_DELIVERY_COMMAND_{normalized}", "").strip()
        if value:
            return value
    return os.environ.get("AGENT_CREW_INTERACT_DELIVERY_COMMAND", "").strip()


def render_interact_delivery_command(template: str, candidate: dict, package: dict) -> tuple[list[str], str]:
    argv, error = host_bridge_command_argv(template)
    if error:
        return [], error
    manifest = package.get("manifest") if isinstance(package.get("manifest"), dict) else {}
    context = package.get("context") if isinstance(package.get("context"), dict) else {}
    relay_dir = Path(str(manifest.get("relay_dir") or package.get("relay_dir") or ""))
    output_file = relay_dir / "delivery-output.txt"
    cwd = str(candidate.get("cwd") or context.get("project_root") or manifest.get("project_root") or "")
    replacements = {
        "prompt_file": str(manifest.get("prompt_file") or ""),
        "copy_file": str(manifest.get("copy_file") or ""),
        "context_file": str(manifest.get("context_file") or ""),
        "manifest_file": str(manifest.get("manifest_file") or ""),
        "relay_dir": str(relay_dir),
        "output_file": str(output_file),
        "project_root": str(context.get("project_root") or manifest.get("project_root") or ""),
        "cwd": cwd,
        "target_host": str(manifest.get("target_host") or candidate.get("ai_type") or "").lower(),
    }

    rendered: list[str] = []
    try:
        for token in argv:
            rendered.append(token.format(**replacements))
    except KeyError as exc:
        return [], f"unknown delivery command placeholder: {exc}"
    return rendered, ""


def write_delivery_result(package: dict, result: dict) -> Path:
    manifest = package.get("manifest") if isinstance(package.get("manifest"), dict) else {}
    relay_dir = Path(str(manifest.get("relay_dir") or package.get("relay_dir") or ""))
    delivery_path = relay_dir / "delivery.json"
    serializable = dict(result)
    serializable["delivery_file"] = str(delivery_path)
    write_json(delivery_path, serializable)
    return delivery_path


def deliver_relay_to_aoe_session(candidate: dict, package: dict) -> dict:
    title = str(candidate.get("aoe_title") or "").strip()
    if not title:
        delivery_file = write_delivery_result(
            package,
            {
                "status": "failed",
                "reason": "aoe_session_title_missing",
                "command": ["aoe", "send"],
            },
        )
        return {"status": "failed", "delivery_file": str(delivery_file), "reason": "aoe_session_title_missing"}

    context = package.get("context") if isinstance(package.get("context"), dict) else {}
    cwd = Path(str(candidate.get("cwd") or context.get("project_root") or ".")).expanduser()
    if not cwd.is_dir():
        cwd = Path(str(context.get("project_root") or ".")).expanduser()
    prompt = str(package.get("prompt") or "")
    argv = ["aoe", "send", title, prompt]
    timeout = int(os.environ.get("AGENT_CREW_INTERACT_DELIVERY_TIMEOUT_SECONDS", "120") or "120")
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        result = {
            "status": "sent" if completed.returncode == 0 else "failed",
            "reason": "aoe_send_completed" if completed.returncode == 0 else "aoe_send_failed",
            "command": ["aoe", "send", title, "<prompt>"],
            "cwd": str(cwd),
            "returncode": completed.returncode,
            "stdout": redact(completed.stdout or ""),
            "stderr": redact(completed.stderr or ""),
            "output_file": "",
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "status": "failed",
            "reason": "aoe_send_timeout",
            "command": ["aoe", "send", title, "<prompt>"],
            "cwd": str(cwd),
            "returncode": None,
            "stdout": redact(exc.stdout or ""),
            "stderr": redact(exc.stderr or ""),
            "output_file": "",
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "reason": "aoe_send_exception",
            "command": ["aoe", "send", title, "<prompt>"],
            "cwd": str(cwd),
            "returncode": None,
            "stdout": "",
            "stderr": redact(str(exc)),
            "output_file": "",
        }

    delivery_file = write_delivery_result(package, result)
    return {
        "status": result["status"],
        "delivery_file": str(delivery_file),
        "reason": result["reason"],
    }


def deliver_relay_to_session(candidate: dict, package: dict) -> dict:
    if str(candidate.get("source") or "").lower() == "aoe":
        return deliver_relay_to_aoe_session(candidate, package)

    manifest = package.get("manifest") if isinstance(package.get("manifest"), dict) else {}
    context = package.get("context") if isinstance(package.get("context"), dict) else {}
    target_host = str(manifest.get("target_host") or candidate.get("ai_type") or "").strip().lower()
    template = interact_delivery_command_template(target_host)
    if not template:
        return {
            "status": "packaged",
            "reason": "host_session_injection_unsupported",
        }

    argv, error = render_interact_delivery_command(template, candidate, package)
    if error:
        delivery_file = write_delivery_result(
            package,
            {
                "status": "failed",
                "reason": "delivery_command_invalid",
                "error": error,
                "command": template,
            },
        )
        return {"status": "failed", "delivery_file": str(delivery_file), "reason": "delivery_command_invalid"}

    cwd = Path(str(candidate.get("cwd") or context.get("project_root") or ".")).expanduser()
    if not cwd.is_dir():
        cwd = Path(str(context.get("project_root") or ".")).expanduser()
    timeout = int(os.environ.get("AGENT_CREW_INTERACT_DELIVERY_TIMEOUT_SECONDS", "120") or "120")
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        result = {
            "status": "sent" if completed.returncode == 0 else "failed",
            "reason": "delivery_command_completed" if completed.returncode == 0 else "delivery_command_failed",
            "command": argv,
            "cwd": str(cwd),
            "returncode": completed.returncode,
            "stdout": redact(completed.stdout or ""),
            "stderr": redact(completed.stderr or ""),
            "output_file": str(Path(str(manifest.get("relay_dir") or package.get("relay_dir"))) / "delivery-output.txt"),
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "status": "failed",
            "reason": "delivery_command_timeout",
            "command": argv,
            "cwd": str(cwd),
            "returncode": None,
            "stdout": redact(exc.stdout or ""),
            "stderr": redact(exc.stderr or ""),
            "output_file": str(Path(str(manifest.get("relay_dir") or package.get("relay_dir"))) / "delivery-output.txt"),
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "reason": "delivery_command_exception",
            "command": argv,
            "cwd": str(cwd),
            "returncode": None,
            "stdout": "",
            "stderr": redact(str(exc)),
            "output_file": str(Path(str(manifest.get("relay_dir") or package.get("relay_dir"))) / "delivery-output.txt"),
        }

    delivery_file = write_delivery_result(package, result)
    return {
        "status": result["status"],
        "delivery_file": str(delivery_file),
        "reason": result["reason"],
    }



def render_selected_session_target(candidate: dict) -> str:
    index = int(candidate.get("index") or 1)
    lines = [
        "선택한 세션:",
        f"{circled_number(index)} {candidate['ai_type']} · {candidate['project']} · {candidate['branch']}",
        f"   {candidate['summary']} · {relative_time_label(candidate['updated_at'])}",
        "",
    ]
    return "\n".join(lines)


def command_relay(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    package, error = create_relay_package(
        project_root=project_root,
        agent_crew_home=agent_crew_home,
        target_host=args.to,
        mode=args.mode,
        prompt_text=" ".join(args.prompt or []).strip(),
        paths=args.paths or [],
        from_task_id=args.from_task,
        copy_requested=bool(args.copy),
    )
    if error:
        print(error, file=sys.stderr)
        return 1

    manifest = package["manifest"]
    copied = bool(package["copied"])
    print("STATUS: completed")
    print(f"RELAY_ID: {manifest['relay_id']}")
    print(f"TARGET: {args.to}")
    print(f"PROMPT: {manifest['prompt_file']}")
    print(f"COPY: {'copied' if copied else 'not_requested' if not args.copy else 'unavailable'}")
    return 0


def command_sessions(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    resolve_project_state(
        home=agent_crew_home,
        project_root=project_root,
        ensure=True,
        migrate_legacy=True,
    )
    candidates = collect_session_candidates(agent_crew_home, limit=args.limit)

    print(render_session_candidates(candidates), end="")
    return 0


def command_interact(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    resolve_project_state(
        home=agent_crew_home,
        project_root=project_root,
        ensure=True,
        migrate_legacy=True,
    )
    request = " ".join(args.prompt or []).strip()
    selector = getattr(args, "select", "")
    candidates: list[dict] = []
    if args.to and selector and getattr(args, "send", False):
        candidates = collect_targeted_session_candidates(agent_crew_home, args.to, limit=args.limit)
    if not candidates:
        candidates = collect_session_candidates(agent_crew_home, limit=args.limit)
    if args.to:
        target = args.to.lower()
        candidates = [
            row
            for row in candidates
            if session_matches_selector(row, target)
        ]
        for index, row in enumerate(candidates, start=1):
            row["index"] = index

    if request:
        print(f"요청: {request}")
        print("")
    if selector:
        selected = select_session_candidate(candidates, selector)
        if selected is None:
            print("선택한 조건에 맞는 AI 세션을 찾지 못했습니다.")
            print("")
            print(render_session_candidates(candidates), end="")
            return 1
        if not getattr(args, "send", False):
            print(render_selected_session(selected), end="")
            return 0

        package, error = create_relay_package(
            project_root=project_root,
            agent_crew_home=agent_crew_home,
            target_host=str(selected.get("ai_type") or "").lower() or "unknown",
            mode="ask",
            prompt_text=request,
            paths=[],
            copy_requested=bool(getattr(args, "copy", False)),
        )
        if error:
            print(error, file=sys.stderr)
            return 1
        delivery = deliver_relay_to_session(selected, package)
        status = str(delivery.get("status") or "packaged").strip().lower()
        if status == "sent":
            final_status = "sent"
        elif getattr(args, "copy", False) and package.get("copied"):
            final_status = "copy_fallback"
        elif status in {"failed", "packaged"}:
            final_status = status
        else:
            final_status = "packaged"

        print(render_selected_session_target(selected))
        print(f"STATUS: {final_status}")
        delivery_file = str(delivery.get("delivery_file") or "").strip()
        if delivery_file:
            print(f"DELIVERY: {delivery_file}")
        if final_status != "sent":
            print(f"PROMPT: {package['manifest']['prompt_file']}")
        if getattr(args, "copy", False):
            print(f"COPY: {'copied' if package.get('copied') else 'unavailable'}")
        if final_status == "failed":
            return 1
        return 0

    print(render_session_candidates(candidates), end="")
    if candidates:
        print("")
        print("그대로 보낼까요? 아니면 번호를 선택하세요.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="agent-crew deterministic runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="create deterministic crew run state")
    run.add_argument("task")
    run.add_argument("--project-root")
    run.add_argument("--fake-host-result", choices=["completed"], default=None)
    run.add_argument("--host-bridge-command", default=None)
    run.set_defaults(func=command_run)

    agent = sub.add_parser("agent", help="create deterministic direct-agent handoff")
    agent.add_argument("--project-root")
    agent.add_argument("--asset-root")
    agent.add_argument("--host-bridge-command", default=None)
    agent.add_argument("--agent-layer", choices=["project", "user", "system"], default=None)
    agent.add_argument("--save-agent-layer", choices=["project", "user", "system"], default=None)
    agent.add_argument("--list", action="store_true")
    agent.add_argument("--routing", action="store_true")
    agent.add_argument("agent_args", nargs=argparse.REMAINDER)
    agent.set_defaults(func=command_agent)

    issue_ingest = sub.add_parser("issue-ingest", help="record issue body/comment ingestion evidence")
    issue_ingest.add_argument("issue_number")
    issue_ingest.add_argument("--project-root")
    issue_ingest.add_argument("--task-id", default="")
    issue_ingest.add_argument("--repo", default="")
    issue_ingest.add_argument("--output", default="")
    issue_ingest.add_argument("--format", choices=["text", "json"], default="text")
    issue_ingest.set_defaults(func=command_issue_ingest)

    relay = sub.add_parser("relay", help="package a prompt for another AI session")
    relay.add_argument("--project-root")
    relay.add_argument("--to", required=True, help="target AI host name, such as claude, codex, or gemini")
    relay.add_argument("--mode", choices=["ask", "run", "review", "debug"], default="ask")
    relay.add_argument("--from-task", default="")
    relay.add_argument("--paths", action="append", default=[])
    relay.add_argument("--copy", action="store_true")
    relay.add_argument("prompt", nargs=argparse.REMAINDER)
    relay.set_defaults(func=command_relay)

    sessions = sub.add_parser("sessions", help="list recent AI session candidates")
    sessions.add_argument("--project-root")
    sessions.add_argument("--limit", type=int, default=20)
    sessions.set_defaults(func=command_sessions)

    interact = sub.add_parser("interact", help="start a natural-language interaction with another AI session")
    interact.add_argument("--project-root")
    interact.add_argument("--to", default="")
    interact.add_argument("--select", default="")
    interact.add_argument("--limit", type=int, default=20)
    interact_send = interact.add_mutually_exclusive_group()
    interact_send.add_argument("--send", dest="send", action="store_true", help="attempt delivery after selecting a session")
    interact_send.add_argument("--no-send", dest="send", action="store_false", help="select only without delivery")
    interact.set_defaults(send=True)
    interact.add_argument("--copy", action="store_true", help="copy packaged fallback prompt only when explicitly requested")
    interact.add_argument("prompt", nargs=argparse.REMAINDER)
    interact.set_defaults(func=command_interact)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
