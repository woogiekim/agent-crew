#!/bin/bash
# direct-edit-guard.sh
# PreToolUse hook for Edit and Write tools.
# Blocks direct file edits to project source files when no active crew task
# is in progress. Enforces the rule: all implementation work must go through
# crew:run -> supervisor pipeline.

INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import json
import os
import subprocess
import sys

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

try:
    data = json.loads(raw_input)
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {})

if tool_name not in ("Edit", "Write", "MultiEdit", "apply_patch"):
    sys.exit(0)

file_path = ""
if isinstance(tool_input, dict):
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
if not file_path:
    sys.exit(0)

# Resolve project root
try:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    )
    project_root = result.stdout.strip()
except Exception:
    sys.exit(0)

if not project_root or not file_path.startswith(project_root):
    sys.exit(0)

# Allow edits to crew state, agent definitions, and harness config itself
agent_crew_home = os.environ.get("AGENT_CREW_HOME", os.path.expanduser("~/.agent-crew"))
allowed_prefixes = [
    agent_crew_home,
    os.path.expanduser("~/.claude"),
]
if any(file_path.startswith(p) for p in allowed_prefixes):
    sys.exit(0)

# Check for an active crew task marker.
#
# Two marker layouts are supported (backward compatibility for codex / generic
# adapters that have not adopted the per-task marker):
#
#   1. Legacy singleton:   tasks/active
#      Used by single supervisor workflows and by hosts that have not opted
#      into background fan-out. Existing installations rely on this path; it
#      must continue to work without any change.
#
#   2. Per-task markers:   tasks/active.<TASK_ID>
#      Required by background fan-out. When multiple supervisors run in
#      independent host sessions, each owns its own marker so concurrent
#      teardown by one runner does not strand edits made by another.
#
# Either layout grants permission. Exit on first match.
tasks_dir = os.path.join(agent_crew_home, "state", os.path.basename(project_root), "tasks")

if os.path.exists(os.path.join(tasks_dir, "active")):
    sys.exit(0)  # Inside a crew task (legacy singleton marker) — allow

try:
    if os.path.isdir(tasks_dir):
        with os.scandir(tasks_dir) as it:
            for entry in it:
                if entry.name.startswith("active.") and entry.is_file():
                    sys.exit(0)  # Inside a crew task (per-task marker) — allow
except Exception:
    pass

# No active crew task found — block
block_output = {
    "decision": "block",
    "reason": (
        "[agent-crew] Direct edit blocked — no active crew task.\n\n"
        "All implementation work must go through the crew pipeline:\n"
        "  crew:run \"your request\"\n\n"
        "If this is genuinely not implementation work (e.g. a one-line "
        "typo fix with no design implications), start a crew task first "
        "to create the active task marker, then proceed."
    )
}
print(json.dumps(block_output))
sys.exit(0)
PYEOF
