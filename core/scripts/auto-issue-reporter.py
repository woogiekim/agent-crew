#!/usr/bin/env python3
"""Detect agent-crew bug/error signals and store/publish native reports.

Inputs:
  - JSON hook payload on stdin. Recognized shapes include UserPromptSubmit
    {"prompt": "..."} and PostToolUse {"tool_name": "Bash", ...}.
  - Environment controls documented in core/rules/auto-issue-reporting.md.

Outputs:
  - Silent by default for hook use.
  - With --format json, emits a machine-readable status object.

Exit codes:
  - Always 0 for normal operation. This reporter is advisory; it must never
    block the user's prompt/tool flow when GitHub, auth, or parsing fails.

Example:
  printf '{"prompt":"agent-crew error: traceback"}' |
    python3 core/scripts/auto-issue-reporter.py auto --format json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPO = "woogiekim/agent-crew"
DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_TIMEOUT_SECONDS = 8
PUBLISH_FALSE_VALUES = {"", "0", "false", "no", "off", "none", "local"}
PUBLISH_TRUE_VALUES = {"1", "true", "yes", "on", "github"}

AGENT_CREW_RE = re.compile(
    r"agent[-\s]?crew|crew\s*:|crew\s+run|\bcrew\b|\$crew|"
    r"에이전트\s*크루|에이전트크루",
    re.IGNORECASE,
)
BUG_RE = re.compile(
    r"bug|error|exception|traceback|failed|failure|crash|panic|"
    r"오류|에러|버그|실패|크래시|안됨|안\s*됨|문제",
    re.IGNORECASE,
)
SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(token|password|passwd|secret|api[_-]?key)=\S+"),
]


@dataclass(frozen=True)
class Signal:
    source: str
    summary: str
    evidence: str


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def state_dir() -> Path:
    report_override = os.environ.get("AGENT_CREW_REPORT_STATE_DIR")
    if report_override:
        return Path(report_override).expanduser()
    override = os.environ.get("AGENT_CREW_AUTO_ISSUE_STATE_DIR")
    if override:
        return Path(override).expanduser()
    home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    return home / "state" / "reports"


def load_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def flatten_strings(value: Any, limit: int = 12000) -> list[str]:
    out: list[str] = []

    def walk(v: Any) -> None:
        if sum(len(x) for x in out) >= limit:
            return
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, (int, float, bool)):
            out.append(str(v))
        elif isinstance(v, dict):
            for key in sorted(v):
                walk(v[key])
        elif isinstance(v, list):
            for item in v:
                walk(item)

    walk(value)
    return out


def redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def compact_text(text: str, max_len: int = 4000) -> str:
    text = redact(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    if len(text) > max_len:
        return text[: max_len - 40].rstrip() + "\n...[truncated by auto reporter]"
    return text


def has_agent_crew_signal(text: str) -> bool:
    return bool(AGENT_CREW_RE.search(text))


def has_bug_signal(text: str) -> bool:
    return bool(BUG_RE.search(text))


def detect_signal(payload: dict[str, Any]) -> Signal | None:
    prompt = str(payload.get("prompt") or "")
    if prompt and has_agent_crew_signal(prompt) and has_bug_signal(prompt):
        summary = first_line(prompt)
        return Signal(
            source="UserPromptSubmit",
            summary=summary,
            evidence=compact_text(prompt),
        )

    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    command = str(tool_input.get("command") or tool_input.get("cmd") or "")
    response_parts: list[str] = []
    for key in ("tool_response", "tool_result", "response", "result", "stderr", "stdout", "output", "error"):
        if key in payload:
            response_parts.extend(flatten_strings(payload.get(key)))
    response_text = "\n".join(response_parts)
    combined = "\n".join(part for part in (command, response_text) if part)

    command_is_crew = bool(command and has_agent_crew_signal(command))
    output_has_bug = has_bug_signal(response_text)
    if tool_name == "Bash" and command_is_crew and output_has_bug:
        summary_source = command or combined
        return Signal(
            source="PostToolUse:Bash",
            summary=first_line(summary_source),
            evidence=compact_text(combined),
        )

    return None


def first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "agent-crew bug/error signal"


def fingerprint_for(signal: Signal) -> str:
    normalized = re.sub(r"\s+", " ", signal.evidence).strip().lower()
    raw = f"{signal.source}\n{normalized[:2000]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def issue_title(signal: Signal) -> str:
    summary = re.sub(r"\s+", " ", signal.summary).strip()
    summary = redact(summary)
    if len(summary) > 82:
        summary = summary[:79].rstrip() + "..."
    return f"[auto-report] agent-crew error: {summary}"


def issue_body(signal: Signal, fingerprint: str) -> str:
    task_id = os.environ.get("AGENT_CREW_TASK_ID", "")
    host = os.environ.get("AGENT_CREW_HOST", "")
    project = os.environ.get("PROJECT_ROOT", os.getcwd())
    return (
        f"<!-- agent-crew-auto-report-fingerprint:{fingerprint} -->\n\n"
        "### Auto-Reported Agent-Crew Bug/Error\n\n"
        f"- Source: `{signal.source}`\n"
        f"- Fingerprint: `{fingerprint}`\n"
        f"- Project: `{Path(project).name}`\n"
        f"- Task ID: `{task_id or 'N/A'}`\n"
        f"- Host: `{host or 'unknown'}`\n\n"
        "### Detected Signal\n\n"
        "```text\n"
        f"{signal.evidence}\n"
        "```\n\n"
        "### Safeguards\n\n"
        "- Secrets matching common token patterns were redacted before publication.\n"
        "- The hook stores this fingerprint locally to avoid repeated reports.\n"
        "- This issue was created by the agent-crew automatic issue reporter hook.\n"
    )


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def duplicate_record(record_path: Path, ttl_seconds: int) -> dict[str, Any] | None:
    record = read_json(record_path)
    if not record:
        return None
    reported_at = float(record.get("reported_at_epoch") or 0)
    status = str(record.get("status") or "")
    if status in {"recorded", "created", "remote_duplicate", "queued_missing_gh", "dry_run"} and time.time() - reported_at <= ttl_seconds:
        return record
    return None


def publish_backend(explicit: str | None = None) -> str:
    raw = explicit
    if raw is None:
        raw = os.environ.get("AGENT_CREW_REPORT_PUBLISH")
    if raw is None:
        raw = os.environ.get("AGENT_CREW_AUTO_ISSUE_PUBLISH")
    if raw is None:
        return "none"

    value = raw.strip().lower()
    if value in PUBLISH_FALSE_VALUES:
        return "none"
    if value in PUBLISH_TRUE_VALUES:
        return "github"
    return value


def report_document(signal: Signal, fingerprint: str, title: str, body: str, repo: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "fingerprint": fingerprint,
        "repo": repo,
        "source": signal.source,
        "title": title,
        "body": body,
        "summary": redact(signal.summary),
        "evidence": signal.evidence,
        "created_at_epoch": time.time(),
    }


def write_outbox(root: Path, fingerprint: str, document: dict[str, Any]) -> Path:
    path = root / "outbox" / f"{fingerprint}.json"
    write_json(path, document)
    return path


def remove_outbox(root: Path, fingerprint: str) -> None:
    try:
        (root / "outbox" / f"{fingerprint}.json").unlink()
    except FileNotFoundError:
        pass


def gh_json(args: list[str], timeout: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def remote_duplicate(repo: str, fingerprint: str, timeout: int) -> str | None:
    rc, stdout, _stderr = gh_json(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--search",
            f"agent-crew-auto-report-fingerprint:{fingerprint}",
            "--json",
            "number,url",
            "--limit",
            "1",
        ],
        timeout,
    )
    if rc != 0:
        return None
    try:
        rows = json.loads(stdout or "[]")
    except Exception:
        return None
    if isinstance(rows, list) and rows:
        url = rows[0].get("url") if isinstance(rows[0], dict) else None
        return str(url) if url else "remote_duplicate"
    return None


def create_issue(repo: str, title: str, body: str, timeout: int) -> tuple[str, str]:
    rc, stdout, stderr = gh_json(
        ["issue", "create", "--repo", repo, "--title", title, "--body", body],
        timeout,
    )
    if rc == 0:
        return "created", stdout.strip()
    return "failed", stderr or stdout or "gh issue create failed"


def publish_github(root: Path, record_path: Path, base_record: dict[str, Any], title: str, body: str, timeout: int) -> dict[str, Any]:
    repo = str(base_record["repo"])
    fingerprint = str(base_record["fingerprint"])
    if shutil.which("gh") is None:
        queue_path = root / "queued" / f"{fingerprint}.md"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(f"# {title}\n\n{body}", encoding="utf-8")
        record = {**base_record, "status": "queued_missing_gh", "url": "", "queue_path": str(queue_path)}
        write_json(record_path, record)
        return result("queued_missing_gh", fingerprint=fingerprint, queue_path=str(queue_path))

    duplicate_url = remote_duplicate(repo, fingerprint, timeout)
    if duplicate_url:
        record = {**base_record, "status": "remote_duplicate", "url": duplicate_url}
        write_json(record_path, record)
        remove_outbox(root, fingerprint)
        return result("remote_duplicate", fingerprint=fingerprint, url=duplicate_url)

    status, detail = create_issue(repo, title, body, timeout)
    record = {**base_record, "status": status, "url": detail if status == "created" else "", "detail": detail}
    write_json(record_path, record)
    if status == "created":
        remove_outbox(root, fingerprint)
    return result(status, fingerprint=fingerprint, url=record.get("url", ""), detail=detail)


def result(status: str, **extra: Any) -> dict[str, Any]:
    payload = {"status": status}
    payload.update(extra)
    return payload


def emit(payload: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    elif fmt == "text" and payload.get("status") not in {"ignored"}:
        print(payload.get("status", "unknown"))


def handle_auto(raw: str, backend: str | None = None) -> dict[str, Any]:
    if env_flag("AGENT_CREW_AUTO_ISSUE_REPORT_DISABLED") or os.environ.get("AGENT_CREW_AUTO_ISSUE_REPORT") == "0":
        return result("disabled")

    payload = load_payload(raw)
    signal = detect_signal(payload)
    if signal is None:
        return result("ignored")

    repo = os.environ.get("AGENT_CREW_AUTO_ISSUE_REPO", DEFAULT_REPO)
    ttl_seconds = int(os.environ.get("AGENT_CREW_AUTO_ISSUE_TTL_SECONDS", str(DEFAULT_TTL_SECONDS)))
    timeout = int(os.environ.get("AGENT_CREW_AUTO_ISSUE_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    dry_run = env_flag("AGENT_CREW_AUTO_ISSUE_DRY_RUN")
    root = state_dir()
    fingerprint = fingerprint_for(signal)
    record_path = root / "reported" / f"{fingerprint}.json"
    duplicate = duplicate_record(record_path, ttl_seconds)
    if duplicate:
        return result("skipped_duplicate", fingerprint=fingerprint, url=duplicate.get("url", ""))

    title = issue_title(signal)
    body = issue_body(signal, fingerprint)
    document = report_document(signal, fingerprint, title, body, repo)
    base_record = {
        "fingerprint": fingerprint,
        "repo": repo,
        "source": signal.source,
        "title": title,
        "reported_at_epoch": time.time(),
    }

    if dry_run:
        record = {**base_record, "status": "dry_run", "url": ""}
        write_json(record_path, record)
        return result("dry_run", fingerprint=fingerprint, title=title)

    outbox_path = write_outbox(root, fingerprint, document)
    selected_backend = publish_backend(backend)
    if selected_backend == "none":
        record = {**base_record, "status": "recorded", "url": "", "outbox_path": str(outbox_path)}
        write_json(record_path, record)
        return result("recorded", fingerprint=fingerprint, outbox_path=str(outbox_path))

    if selected_backend == "github":
        return publish_github(root, record_path, base_record, title, body, timeout)

    record = {**base_record, "status": "unsupported_backend", "backend": selected_backend, "outbox_path": str(outbox_path)}
    write_json(record_path, record)
    return result("unsupported_backend", fingerprint=fingerprint, backend=selected_backend, outbox_path=str(outbox_path))


def handle_publish(backend: str | None = None) -> dict[str, Any]:
    selected_backend = publish_backend(backend or "github")
    if selected_backend != "github":
        return result("unsupported_backend", backend=selected_backend)

    root = state_dir()
    repo = os.environ.get("AGENT_CREW_AUTO_ISSUE_REPO", DEFAULT_REPO)
    timeout = int(os.environ.get("AGENT_CREW_AUTO_ISSUE_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    outbox_dir = root / "outbox"
    reports = sorted(outbox_dir.glob("*.json")) if outbox_dir.is_dir() else []
    published = 0
    failed = 0
    queued = 0
    details: list[dict[str, Any]] = []

    for path in reports:
        document = read_json(path)
        if not document:
            failed += 1
            details.append({"path": str(path), "status": "invalid"})
            continue
        fingerprint = str(document.get("fingerprint") or path.stem)
        title = str(document.get("title") or f"[auto-report] agent-crew error: {fingerprint}")
        body = str(document.get("body") or "")
        record_path = root / "reported" / f"{fingerprint}.json"
        base_record = {
            "fingerprint": fingerprint,
            "repo": str(document.get("repo") or repo),
            "source": str(document.get("source") or "outbox"),
            "title": title,
            "reported_at_epoch": time.time(),
        }
        publish_result = publish_github(root, record_path, base_record, title, body, timeout)
        status = str(publish_result.get("status") or "")
        if status in {"created", "remote_duplicate"}:
            published += 1
        elif status == "queued_missing_gh":
            queued += 1
        else:
            failed += 1
        details.append({"fingerprint": fingerprint, "status": status, "url": publish_result.get("url", "")})

    status = "published" if failed == 0 and queued == 0 else "partial"
    if not reports:
        status = "empty"
    return result(status, published=published, queued=queued, failed=failed, reports=details)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        argv = ["auto", *argv]

    parser = argparse.ArgumentParser(description="Store and optionally publish agent-crew bug/error reports.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auto = subparsers.add_parser("auto", help="classify a hook payload and store a native report")
    auto.add_argument("--format", choices=("none", "json", "text"), default="none")
    auto.add_argument("--payload", default="-", help="payload source; '-' reads stdin")
    auto.add_argument("--publish", choices=("none", "github"), help="optional publisher backend")

    publish = subparsers.add_parser("publish", help="publish queued native reports")
    publish.add_argument("--format", choices=("none", "json", "text"), default="none")
    publish.add_argument("--backend", choices=("github",), default="github")

    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        if args.command == "auto":
            raw = sys.stdin.read() if args.payload == "-" else Path(args.payload).read_text(encoding="utf-8")
            payload = handle_auto(raw, backend=args.publish)
        elif args.command == "publish":
            payload = handle_publish(args.backend)
        else:
            payload = result("failed", detail=f"unsupported command: {args.command}")
    except Exception as exc:
        payload = result("failed", detail=str(exc))
    emit(payload, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
