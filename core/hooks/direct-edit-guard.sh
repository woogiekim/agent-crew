#!/bin/bash
# direct-edit-guard.sh
# PreToolUse hook for Edit and Write tools.
# Blocks direct file edits to project source files when no active crew task
# is in progress. Enforces the rule: all implementation work must go through
# crew:run -> supervisor pipeline.
#
# Escape hatch: set AGENT_CREW_ALLOW_DIRECT_EDIT=1 in the environment, or
# include the literal string "agent-crew: direct-edit" anywhere in the
# session context to authorize a direct edit explicitly.
# See core/rules/direct-edit-guard.md for the full enforcement contract.
#
# Exit codes (Claude Code PreToolUse contract):
#   0  — allow (no block decision)
#   2  — block (Claude sees the reason and the tool call is cancelled)
#
# Bug history:
#   2026-05-17: hook was exiting 0 even on the block path, which meant
#   Claude never enforced the block decision. Fixed by using sys.exit(2)
#   on the block path. See GitHub issue #17.

INPUT=$(cat)

python3 - "$INPUT" <<'PYEOF'
import json
import os
import subprocess
import sys

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""

def block_with_reason(reason):
    print(json.dumps({"decision": "block", "reason": reason}), file=sys.stderr, flush=True)
    sys.exit(2)

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

# Escape hatch 1: AGENT_CREW_ALLOW_DIRECT_EDIT env var
if os.environ.get("AGENT_CREW_ALLOW_DIRECT_EDIT", "").strip() == "1":
    sys.exit(0)

# Resolve project root
try:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, cwd=os.path.dirname(file_path) if os.path.dirname(file_path) else None
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
#
# Stale-marker guard: per-task markers are validated against a live task.
# The legacy singleton is inherently less reliable (no task-id binding) but
# is still accepted for backward compatibility. Callers must clean up markers
# in Phase 3 (supervisor-retry.md "Clear active task marker").
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

# No active crew task found — block with exit code 2.
#
# FIX (issue #17): Previously this path called sys.exit(0) after printing the
# block JSON, which caused Claude Code to ignore the block decision entirely
# (exit 0 = "allow" in the PreToolUse hook contract). Changed to sys.exit(2)
# so the host surfaces the reason to the model and cancels the tool call.
block_message = (
    "[agent-crew] Direct edit blocked — no active crew task.\n\n"
    "All implementation work must go through the crew pipeline:\n"
    "  crew:run \"your request\"\n\n"
    "The active task marker is created automatically by the supervisor "
    "agent (Phase 1c). Never create it manually — use crew:run to "
    "delegate all implementation work to a supervisor.\n\n"
    "To authorize a one-off direct edit, set AGENT_CREW_ALLOW_DIRECT_EDIT=1 "
    "in the environment or see core/rules/direct-edit-guard.md for the "
    "full escape hatch documentation."
)
block_with_reason(block_message)
PYEOF
