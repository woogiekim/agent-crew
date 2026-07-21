#!/usr/bin/env bash
# PostToolUse hook: record per-call Bash tool events into
# {TASK_DIR}/tool-events.jsonl for the active crew task.
#
# Capability: tool_event_fidelity (per-call trace surface).
# Schema v1 is defined by core/scripts/crew-runtime.py:append_tool_event; this
# hook reuses that function so rows stay byte-identical for existing consumers
# (cost-aggregate.py, telemetry-aggregate.py, telemetry-taxonomy-check.py) and
# for the trace-derived quality gate (quality_loop_lib.tool_event_test_runs).
#
# This hook is a no-op when no crew task is active or the tool call is not Bash.

# Read the hook payload before starting Python. The program remains on stdin;
# file descriptor 3 carries the payload without environment-size limits.
HOOK_PAYLOAD=""
IFS= read -r -d '' HOOK_PAYLOAD || true

# Most PostToolUse events are not Bash. Avoid Python startup, project
# resolution, and runtime imports for those events.
if [[ ! "${HOOK_PAYLOAD}" =~ \"tool_name\"[[:space:]]*:[[:space:]]*\"Bash\" ]]; then
    exit 0
fi

python3 3<<<"${HOOK_PAYLOAD}" <<'PYEOF'
import sys, json, os, subprocess, hashlib, re
from datetime import datetime, timezone
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(token|password|passwd|secret|api[_-]?key)=\S+"),
]


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def append_tool_event(
    task_dir: Path,
    *,
    trace_id: str,
    tool_name: str,
    action_summary: str,
    started_at: str,
    ended_at: str,
    status: str,
    exit_code,
    failure_class: str,
) -> None:
    row = {
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
    }
    path = task_dir / "tool-events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def project_root():
    for name in ("AGENT_CREW_PROJECT_ROOT", "PROJECT_ROOT"):
        raw = os.environ.get(name)
        if raw:
            return Path(raw).expanduser().resolve()
    try:
        raw = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if raw:
            return Path(raw).resolve()
    except Exception:
        pass
    return None


def state_dir_for_project():
    env = os.environ.get("AGENT_CREW_STATE_DIR")
    if env:
        return Path(env).expanduser()
    home = Path(os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew"))).expanduser()
    root = project_root()
    if root is None:
        project = os.environ.get("AGENT_CREW_PROJECT", "default")
        return home / "state" / project
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", root.name.strip()).strip(".-").lower() or "project"
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:10]
    keyed = home / "state" / f"{slug}-{digest}"
    legacy = home / "state" / root.name
    return keyed if keyed.exists() else legacy


def resolve_task_id():
    env = os.environ.get("AGENT_CREW_TASK_ID")
    if env:
        return env
    tasks_dir = state_dir_for_project() / "tasks"
    if not tasks_dir.is_dir():
        return None
    markers = sorted(tasks_dir.glob("active.*"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if markers:
        return markers[0].name[len("active."):]
    return None


with os.fdopen(3, encoding="utf-8") as payload_stream:
    raw = payload_stream.read()

try:
    data = json.loads(raw)
except Exception:
    sys.exit(0)

is_envelope = data.get("agent_crew_hook_envelope") == 1

if str(data.get("tool_name") or "") != "Bash":
    sys.exit(0)  # only record Bash tool calls

if is_envelope:
    command = str(data.get("command") or "").strip()
else:
    command = str((data.get("tool_input") or {}).get("command") or "").strip()
if not command:
    sys.exit(0)

task_id = resolve_task_id()
if not task_id:
    sys.exit(0)  # no active crew task — skip silently

task_dir = state_dir_for_project() / "tasks" / task_id
if not task_dir.is_dir():
    sys.exit(0)

# Derive an integer exit_code and status from the tool response.
response = data if is_envelope else data.get("tool_response")
exit_code = None
if isinstance(response, dict):
    raw_code = response.get("exit_code")
    if isinstance(raw_code, bool):
        raw_code = None
    if isinstance(raw_code, int):
        exit_code = raw_code
    elif isinstance(raw_code, str) and raw_code.strip().lstrip("-").isdigit():
        exit_code = int(raw_code.strip())
    if exit_code is None:
        exit_code = 1 if response.get("is_error") else 0
else:
    exit_code = 0

status = "ok" if exit_code == 0 else "error"
failure_class = "" if exit_code == 0 else "bash_command_failed"
now = utc_now_z()
trace_id = (
    os.environ.get("AGENT_CREW_TRACE_ID")
    or os.environ.get("AGENT_CREW_SESSION_ID")
    or task_id
)

try:
    append_tool_event(
        task_dir,
        trace_id=trace_id,
        tool_name="Bash",
        action_summary=command,
        started_at=now,
        ended_at=now,
        status=status,
        exit_code=exit_code,
        failure_class=failure_class,
    )
except Exception:
    sys.exit(0)
PYEOF
