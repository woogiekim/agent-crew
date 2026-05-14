#!/bin/bash
# direct-edit-guard.sh
# PreToolUse hook for Edit and Write tools.
# Blocks direct file edits to project source files when no active crew task
# is in progress. Enforces the rule: all implementation work must go through
# crew:run -> task-runner pipeline.

python3 - <<'PYEOF'
import json
import os
import subprocess
import sys

try:
    data = json.loads(sys.stdin.read())
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name", "")
if tool_name not in ("Edit", "Write"):
    sys.exit(0)

file_path = data.get("tool_input", {}).get("file_path", "")
if not file_path:
    sys.exit(0)

# Resolve project root
try:
    project_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    ).stdout.strip()
except Exception:
    sys.exit(0)

if not project_root or not file_path.startswith(project_root):
    sys.exit(0)

# Allow edits to crew state, agent definitions, and harness config itself
agent_crew_home = os.environ.get("AGENT_CREW_HOME", os.path.expanduser("~/.agent-crew"))
if file_path.startswith(agent_crew_home) or file_path.startswith(os.path.expanduser("~/.claude")):
    sys.exit(0)

# Check for an active crew task marker.
#
# Two marker layouts are supported (backward compatibility for codex / generic
# adapters that have not adopted the per-task marker):
#
#   1. Legacy singleton:   tasks/active
#      Used by single task-runner workflows and by hosts that have not opted
#      into background fan-out. Existing installations rely on this path; it
#      must continue to work without any change.
#
#   2. Per-task markers:   tasks/active.<TASK_ID>
#      Required by P4 background fan-out — when multiple task-runners run in
#      independent host sessions, each owns its own marker so concurrent
#      teardown by one runner does not strand edits made by another.
#
# Either layout grants permission. Exit on first match — no need to scan all.
tasks_dir = os.path.join(agent_crew_home, "state", os.path.basename(project_root), "tasks")

if os.path.exists(os.path.join(tasks_dir, "active")):
    sys.exit(0)  # Inside a crew task (legacy singleton marker) — allow

# Per-task markers: exit on the first active.<TASK_ID> file found.
try:
    if os.path.isdir(tasks_dir):
        with os.scandir(tasks_dir) as it:
            for entry in it:
                if entry.name.startswith("active.") and entry.is_file():
                    sys.exit(0)  # Inside a crew task (per-task marker) — allow
except Exception:
    pass  # Fall through to block decision below

# No active crew task found — block
print(json.dumps({
    "decision": "block",
    "reason": (
        "[agent-crew] Direct edit blocked — no active crew task.\n\n"
        "All implementation work must go through the crew pipeline:\n"
        "  crew:run \"your request\"\n\n"
        "If this is genuinely not implementation work (e.g. a one-line "
        "typo fix with no design implications), start a crew task first "
        "to create the active task marker, then proceed."
    )
}))
sys.exit(0)
PYEOF
