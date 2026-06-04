#!/usr/bin/env bash
# PostToolUse hook: record per-call token usage into
# ${STATE_DIR}/cost/${TASK_ID}.jsonl for the active task.
#
# Capability: cost_tracking (advertised by adapters/claude/setup.sh).
# Schema documented in core/rules/capabilities/cost-tracking.md.
# Consumer: core/scripts/cost-aggregate.py.
#
# This hook is a no-op when no task is active or no usage data is present.

python3 - <<'PYEOF'
import sys, json, os, subprocess, hashlib, re
from datetime import datetime, timezone
from pathlib import Path


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


raw = sys.stdin.read(1024 * 1024)
sys.stdout.write(raw)  # pass through untouched

try:
    data = json.loads(raw)
except Exception:
    sys.exit(0)

usage = data.get("usage") or data.get("token_usage") or {}
in_tok  = int(usage.get("input_tokens")          or usage.get("prompt_tokens")     or 0)
out_tok = int(usage.get("output_tokens")         or usage.get("completion_tokens") or 0)
cw_tok  = int(usage.get("cache_creation_input_tokens") or 0)
cr_tok  = int(usage.get("cache_read_input_tokens")     or 0)

if in_tok == 0 and out_tok == 0 and cw_tok == 0 and cr_tok == 0:
    sys.exit(0)

task_id = resolve_task_id()
if not task_id:
    sys.exit(0)  # no active task — skip silently

cost_dir = state_dir_for_project() / "cost"
cost_dir.mkdir(parents=True, exist_ok=True)

row = {
    "ts":                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "task_id":               task_id,
    "session_id":            os.environ.get("AGENT_CREW_SESSION_ID") or
                             os.environ.get("CLAUDE_SESSION_ID") or "default",
    "agent":                 os.environ.get("AGENT_CREW_AGENT_NAME") or "unknown",
    "stage":                 int(os.environ["AGENT_CREW_STAGE_INDEX"])
                             if os.environ.get("AGENT_CREW_STAGE_INDEX", "").isdigit() else None,
    "model":                 str(data.get("model") or os.environ.get("CLAUDE_MODEL") or "unknown").lower(),
    "tier":                  os.environ.get("AGENT_CREW_TIER") or "unknown",
    "input_tokens":          in_tok,
    "output_tokens":         out_tok,
    "cache_creation_tokens": cw_tok,
    "cache_read_tokens":     cr_tok,
}

with open(cost_dir / f"{task_id}.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(row) + "\n")
PYEOF
