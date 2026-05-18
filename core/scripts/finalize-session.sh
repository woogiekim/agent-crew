#!/usr/bin/env bash
# finalize-session.sh — Finalize session.json after inline fan-out completes
#
# Usage:
#   finalize-session.sh <SESSION_FILE> [STATE_DIR]
#
# Purpose:
#   On the Codex / generic inline fan-out path (HAS_AGENT_BACKGROUND=0, N>1),
#   the orchestrator's turn stays alive while supervisors run synchronously.
#   After all inline Agent calls return, this script:
#     1. Reads every task's result.md and updates the per-task status in
#        session.json (running → completed / blocked).
#     2. Sets the top-level session.json status to 'completed' once all
#        tasks are in a terminal state.
#
# This is the authoritative session finalization step for the inline path.
# Calling it is MANDATORY immediately after all inline supervisors return
# and before proceeding to Step 7 (result collection / merge).
#
# The P4 background path (HAS_AGENT_BACKGROUND=1) does NOT call this script —
# its session finalization is handled by crew:status --collect (Step 4S).
#
# Exit codes:
#   0  — session.json written with status=completed (or already completed)
#   1  — SESSION_FILE path not provided or file does not exist
#   2  — at least one task is still in terminal-unknown state (partial success)
#       The script still writes what it can; callers should warn but not abort.
#
# Idempotent: safe to call multiple times; a session already marked
# 'completed' or 'blocked' is left unchanged.

set -euo pipefail

SESSION_FILE="${1:-}"
STATE_DIR="${2:-}"

if [ -z "${SESSION_FILE}" ]; then
  echo "finalize-session: ERROR: SESSION_FILE argument required" >&2
  exit 1
fi

if [ ! -f "${SESSION_FILE}" ]; then
  echo "finalize-session: ERROR: session file not found: ${SESSION_FILE}" >&2
  exit 1
fi

# Derive STATE_DIR from the session file's parent directory when not supplied.
if [ -z "${STATE_DIR}" ]; then
  STATE_DIR="$(dirname "${SESSION_FILE}")"
fi

python3 - "${SESSION_FILE}" "${STATE_DIR}" <<'PYEOF'
import json
import os
import re
import sys
import tempfile

SESSION_FILE = sys.argv[1]
STATE_DIR    = sys.argv[2]

# --- load session.json ---------------------------------------------------
try:
    with open(SESSION_FILE, "r", encoding="utf-8") as f:
        session = json.load(f)
except Exception as e:
    print(f"finalize-session: ERROR: cannot read {SESSION_FILE}: {e}", file=sys.stderr)
    sys.exit(1)

top_status = session.get("status", "running")

# Already finalized — nothing to do.
if top_status in ("completed", "blocked"):
    print(f"finalize-session: session already {top_status}, skipping.", file=sys.stderr)
    sys.exit(0)

tasks = session.get("tasks", [])
any_unknown = False

STATUS_RE = re.compile(r"^\s*STATUS:\s*(completed|blocked)\s*$", re.MULTILINE | re.IGNORECASE)

for task in tasks:
    task_status = task.get("status", "running")
    if task_status in ("completed", "blocked"):
        # Already terminal — skip.
        continue

    # Try reading result.md to determine the terminal status.
    task_dir = task.get("task_dir", "")
    if not task_dir:
        # Derive from STATE_DIR + task_id as a fallback.
        task_id = task.get("task_id", "")
        if task_id:
            task_dir = os.path.join(STATE_DIR, "tasks", task_id)

    result_path = os.path.join(task_dir, "result.md") if task_dir else ""

    if result_path and os.path.isfile(result_path):
        try:
            result_text = open(result_path, "r", encoding="utf-8").read()
        except Exception:
            result_text = ""

        m = STATUS_RE.search(result_text)
        if m:
            detected = m.group(1).lower()
            task["status"] = detected
        else:
            # result.md exists but STATUS line is absent/unparseable.
            # Mark as blocked (something went wrong) rather than leaving it 'running'.
            task["status"] = "blocked"
    else:
        # No result.md — task may have crashed before writing one.
        # Leave as-is and flag partial success so caller can warn.
        any_unknown = True

# Determine new top-level status.
remaining = [
    t for t in tasks
    if t.get("status", "running") not in ("completed", "blocked")
]

if not remaining:
    session["status"] = "completed"
    new_top_status = "completed"
else:
    # At least one task still in unknown state — leave top-level 'running'
    # so the stale-session timeout can clean it up; do not prematurely mark
    # completed. Caller receives exit code 2 to indicate partial success.
    new_top_status = "running"

# Atomic write: tempfile → rename so a concurrent reader never sees a half-written file.
tmp_fd, tmp_path = tempfile.mkstemp(
    dir=os.path.dirname(SESSION_FILE),
    prefix=".session-finalize.",
    suffix=".tmp",
)
try:
    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.rename(tmp_path, SESSION_FILE)
except Exception as e:
    try:
        os.unlink(tmp_path)
    except Exception:
        pass
    print(f"finalize-session: ERROR: cannot write {SESSION_FILE}: {e}", file=sys.stderr)
    sys.exit(1)

print(f"finalize-session: session status → {new_top_status} "
      f"({len(tasks) - len(remaining)}/{len(tasks)} tasks terminal)",
      file=sys.stderr)

if any_unknown or remaining:
    sys.exit(2)

sys.exit(0)
PYEOF
