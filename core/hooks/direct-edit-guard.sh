#!/bin/bash
# direct-edit-guard.sh
# PreToolUse hook for Edit and Write tools.
# Blocks direct file edits to project source files when no active crew task
# is in progress. Enforces the rule: all implementation work must go through
# crew:run -> task-runner pipeline.

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

if tool_name not in ("Edit", "Write"):
    sys.exit(0)

file_path = tool_input.get("file_path", "")
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

# Check for active crew task marker
project_name = os.path.basename(project_root)
active_marker = os.path.join(
    agent_crew_home, "state", project_name, "tasks", "active"
)

if os.path.exists(active_marker):
    sys.exit(0)  # Inside a crew task — allow

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
