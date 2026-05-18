#!/usr/bin/env bash
# Tests for core/scripts/finalize-session.sh
#
# Verifies that finalize-session.sh correctly transitions session.json
# from status=running to status=completed after all inline supervisors
# finish (the Codex / generic HAS_AGENT_BACKGROUND=0 path).

set -u  # do NOT set -e — failed assertions must keep running

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

FINALIZE="${SCRIPTS_DIR}/finalize-session.sh"
set +e

# --------------------------------------------------------------------------- #
# helper: write a minimal session.json
# _write_session SESSION_FILE TOP_STATUS TASKS_JSON_FILE_OR_LITERAL
# TASKS_JSON must be valid JSON. Use a file path for complex values or pass []
# --------------------------------------------------------------------------- #
_write_session() {
  local session_file="$1"
  local top_status="${2:-running}"
  local tasks_json_arg="${3:-[]}"

  python3 - "${session_file}" "${top_status}" "${tasks_json_arg}" <<'PYEOF'
import json, sys

session_file = sys.argv[1]
top_status   = sys.argv[2]
tasks_json   = sys.argv[3]

session = {
    "schema_version": 1,
    "session_id": "test-session",
    "status": top_status,
    "pre_run_head": "abc123",
    "tasks": json.loads(tasks_json),
}
json.dump(session, open(session_file, "w"), indent=2)
print()  # trailing newline
PYEOF
}

_read_session_field() {
  local file="$1" field="$2"
  python3 -c "
import json
s = json.load(open('${file}'))
print(s.get('${field}', ''))
"
}

_read_task_status() {
  local file="$1" task_id="$2"
  python3 -c "
import json
s = json.load(open('${file}'))
for t in s.get('tasks', []):
    if t.get('task_id') == '${task_id}':
        print(t.get('status', ''))
        break
"
}

# --------------------------------------------------------------------------- #
# TEST 1: No args → exit 1
# --------------------------------------------------------------------------- #
it "exits 1 when SESSION_FILE argument is missing"
bash "${FINALIZE}" 2>/dev/null
rc=$?
assert_exit 1 "${rc}" "no args"

# --------------------------------------------------------------------------- #
# TEST 2: Non-existent session file → exit 1
# --------------------------------------------------------------------------- #
it "exits 1 when SESSION_FILE does not exist"
bash "${FINALIZE}" "/tmp/does-not-exist-$(date +%s).json" 2>/dev/null
rc=$?
assert_exit 1 "${rc}" "missing file"

# --------------------------------------------------------------------------- #
# TEST 3: Already-completed session → no-op, exit 0
# --------------------------------------------------------------------------- #
TMP=$(make_tmp)
SESSION_FILE="${TMP}/session.json"
_write_session "${SESSION_FILE}" "completed" "[]"

it "exits 0 when session is already completed"
bash "${FINALIZE}" "${SESSION_FILE}" "${TMP}" 2>/dev/null
rc=$?
assert_exit 0 "${rc}" "already completed"

it "leaves status=completed unchanged"
status=$(_read_session_field "${SESSION_FILE}" status)
assert_eq "completed" "${status}" "top-level status"

# --------------------------------------------------------------------------- #
# TEST 4: All tasks have result.md with STATUS: completed → session=completed
# --------------------------------------------------------------------------- #
TMP=$(make_tmp)
SESSION_FILE="${TMP}/session.json"

# Create two task dirs with result.md
TASK1_DIR="${TMP}/tasks/task-001"
TASK2_DIR="${TMP}/tasks/task-002"
mkdir -p "${TASK1_DIR}" "${TASK2_DIR}"
printf "# Task 1\n\nSTATUS: completed\nBRANCH: feat/task1\nCOMMITS: 2\n" \
  > "${TASK1_DIR}/result.md"
printf "# Task 2\n\nSTATUS: completed\nBRANCH: feat/task2\nCOMMITS: 1\n" \
  > "${TASK2_DIR}/result.md"

TASKS_JSON="[
    {\"task_id\": \"task-001\", \"task_dir\": \"${TASK1_DIR}\", \"branch\": \"feat/task1\", \"task\": \"task 1\", \"status\": \"running\", \"injected\": false},
    {\"task_id\": \"task-002\", \"task_dir\": \"${TASK2_DIR}\", \"branch\": \"feat/task2\", \"task\": \"task 2\", \"status\": \"running\", \"injected\": false}
]"
_write_session "${SESSION_FILE}" "running" "${TASKS_JSON}"

it "exits 0 when all tasks have result.md with STATUS: completed"
bash "${FINALIZE}" "${SESSION_FILE}" "${TMP}" 2>/dev/null
rc=$?
assert_exit 0 "${rc}" "all complete"

it "sets top-level status to completed"
status=$(_read_session_field "${SESSION_FILE}" status)
assert_eq "completed" "${status}" "top-level status"

it "sets task-001 status to completed"
ts=$(_read_task_status "${SESSION_FILE}" "task-001")
assert_eq "completed" "${ts}" "task-001"

it "sets task-002 status to completed"
ts=$(_read_task_status "${SESSION_FILE}" "task-002")
assert_eq "completed" "${ts}" "task-002"

# --------------------------------------------------------------------------- #
# TEST 5: One task blocked, one completed → session=completed (all terminal)
# --------------------------------------------------------------------------- #
TMP=$(make_tmp)
SESSION_FILE="${TMP}/session.json"

TASK1_DIR="${TMP}/tasks/task-A"
TASK2_DIR="${TMP}/tasks/task-B"
mkdir -p "${TASK1_DIR}" "${TASK2_DIR}"
printf "STATUS: completed\n" > "${TASK1_DIR}/result.md"
printf "STATUS: blocked\nBLOCKER: test failure\n" > "${TASK2_DIR}/result.md"

TASKS_JSON="[
    {\"task_id\": \"task-A\", \"task_dir\": \"${TASK1_DIR}\", \"branch\": \"feat/a\", \"task\": \"A\", \"status\": \"running\", \"injected\": false},
    {\"task_id\": \"task-B\", \"task_dir\": \"${TASK2_DIR}\", \"branch\": \"feat/b\", \"task\": \"B\", \"status\": \"running\", \"injected\": false}
]"
_write_session "${SESSION_FILE}" "running" "${TASKS_JSON}"

it "exits 0 when all tasks are terminal (mixed completed/blocked)"
bash "${FINALIZE}" "${SESSION_FILE}" "${TMP}" 2>/dev/null
rc=$?
assert_exit 0 "${rc}" "mixed terminal"

it "sets top-level status to completed when all tasks terminal"
status=$(_read_session_field "${SESSION_FILE}" status)
assert_eq "completed" "${status}" "top-level status"

it "sets blocked task status to blocked"
ts=$(_read_task_status "${SESSION_FILE}" "task-B")
assert_eq "blocked" "${ts}" "task-B"

# --------------------------------------------------------------------------- #
# TEST 6: One task has no result.md (crashed) → exit 2, partial update
# --------------------------------------------------------------------------- #
TMP=$(make_tmp)
SESSION_FILE="${TMP}/session.json"

TASK1_DIR="${TMP}/tasks/task-X"
TASK2_DIR="${TMP}/tasks/task-Y"
mkdir -p "${TASK1_DIR}" "${TASK2_DIR}"
printf "STATUS: completed\n" > "${TASK1_DIR}/result.md"
# task-Y has no result.md — simulates a crashed supervisor

TASKS_JSON="[
    {\"task_id\": \"task-X\", \"task_dir\": \"${TASK1_DIR}\", \"branch\": \"feat/x\", \"task\": \"X\", \"status\": \"running\", \"injected\": false},
    {\"task_id\": \"task-Y\", \"task_dir\": \"${TASK2_DIR}\", \"branch\": \"feat/y\", \"task\": \"Y\", \"status\": \"running\", \"injected\": false}
]"
_write_session "${SESSION_FILE}" "running" "${TASKS_JSON}"

it "exits 2 when a task has no result.md"
bash "${FINALIZE}" "${SESSION_FILE}" "${TMP}" 2>/dev/null
rc=$?
assert_exit 2 "${rc}" "missing result.md"

it "does NOT set top-level status to completed when a task is missing result.md"
status=$(_read_session_field "${SESSION_FILE}" status)
assert_eq "running" "${status}" "top-level status stays running"

it "still updates task-X to completed"
ts=$(_read_task_status "${SESSION_FILE}" "task-X")
assert_eq "completed" "${ts}" "task-X updated"

# --------------------------------------------------------------------------- #
# TEST 7: Idempotency — calling twice produces same result
# --------------------------------------------------------------------------- #
TMP=$(make_tmp)
SESSION_FILE="${TMP}/session.json"

TASK1_DIR="${TMP}/tasks/task-idem"
mkdir -p "${TASK1_DIR}"
printf "STATUS: completed\n" > "${TASK1_DIR}/result.md"

TASKS_JSON="[
    {\"task_id\": \"task-idem\", \"task_dir\": \"${TASK1_DIR}\", \"branch\": \"feat/idem\", \"task\": \"idem\", \"status\": \"running\", \"injected\": false}
]"
_write_session "${SESSION_FILE}" "running" "${TASKS_JSON}"

bash "${FINALIZE}" "${SESSION_FILE}" "${TMP}" 2>/dev/null
bash "${FINALIZE}" "${SESSION_FILE}" "${TMP}" 2>/dev/null
rc=$?

it "second call exits 0 (already completed — idempotent)"
assert_exit 0 "${rc}" "second call"

it "second call leaves status=completed"
status=$(_read_session_field "${SESSION_FILE}" status)
assert_eq "completed" "${status}" "top-level status"

# --------------------------------------------------------------------------- #
# TEST 8: task_dir derived from STATE_DIR/tasks/<task_id> when task_dir absent
# --------------------------------------------------------------------------- #
TMP=$(make_tmp)
SESSION_FILE="${TMP}/session.json"

TASK_ID="task-derived"
TASK1_DIR="${TMP}/tasks/${TASK_ID}"
mkdir -p "${TASK1_DIR}"
printf "STATUS: completed\n" > "${TASK1_DIR}/result.md"

# task_dir field intentionally omitted from the task entry
TASKS_JSON="[
    {\"task_id\": \"${TASK_ID}\", \"branch\": \"feat/derived\", \"task\": \"derived\", \"status\": \"running\", \"injected\": false}
]"
_write_session "${SESSION_FILE}" "running" "${TASKS_JSON}"

it "derives task_dir from STATE_DIR/tasks/<task_id> when field is absent"
bash "${FINALIZE}" "${SESSION_FILE}" "${TMP}" 2>/dev/null
rc=$?
assert_exit 0 "${rc}" "derived task_dir"

it "sets top-level status to completed via derived path"
status=$(_read_session_field "${SESSION_FILE}" status)
assert_eq "completed" "${status}" "top-level status"

# --------------------------------------------------------------------------- #
end_report
