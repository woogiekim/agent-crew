#!/usr/bin/env bash
# smoke-test-state.sh — End-to-end smoke test for the F4/F5/G6/J13 stack.
#
# Spins up a synthetic state directory and exercises:
#   - F4: validate-state-schema.py against valid + invalid state files
#   - F5: progress.buffer.jsonl row shape
#   - G6: check-plaintext-approval.py pattern matching
#   - J13: telemetry-aggregate.py per-task + summary metrics
#
# Pure read-only against the repo (uses scripts in core/scripts/).
# Writes only into a temp directory, cleaned up on exit.
#
# Exit codes:
#   0 — every assertion passed
#   1 — one or more assertions failed (last failure printed)
#   2 — prerequisite missing (python3, jq, etc.)
#
# Usage:
#   bash core/scripts/smoke-test-state.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/core/scripts"

# Prerequisite
if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: python3 not found" >&2
  exit 2
fi

PASS=0
FAIL=0
LAST_FAIL=""

assert_eq() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  if [ "${expected}" = "${actual}" ]; then
    PASS=$((PASS + 1))
    printf '  PASS  %s\n' "${label}"
  else
    FAIL=$((FAIL + 1))
    LAST_FAIL="${label}: expected=${expected} actual=${actual}"
    printf '  FAIL  %s — expected=%s actual=%s\n' \
      "${label}" "${expected}" "${actual}"
  fi
}

# Run a command, capture exit code only. Suppress all output. Tolerates
# set -e because we don't propagate the non-zero status — we report it
# as a string back to the caller.
run_capture_rc() {
  set +e
  "$@" >/dev/null 2>&1
  local _rc=$?
  set -e
  printf '%s' "${_rc}"
}

# --------------------------------------------------------------------------- #

TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

export AGENT_CREW_HOME="${REPO_ROOT}"  # so validator finds core/schemas/
STATE_DIR="${TMPDIR}/state"
TASK_ID="20260516-120000-0"
TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
mkdir -p "${TASK_DIR}" "${STATE_DIR}/cost"

# --------------------------------------------------------------------------- #
echo ""
echo "[1/4] F4 — state schema validator"
echo "------------------------------------"
# --------------------------------------------------------------------------- #

# Valid: complete task state.
cat > "${TASK_DIR}/register.json" <<EOF
{
  "schema_version": 1,
  "task_id": "${TASK_ID}",
  "session_id": "20260516-120000",
  "task": "smoke test task",
  "branch": "smoke-test",
  "project_root": "/tmp",
  "task_dir": "${TASK_DIR}",
  "execution_mode": "single",
  "current_phase": "completed",
  "approval_status": "approved",
  "verification_status": "passed"
}
EOF

cat > "${TASK_DIR}/pipeline.json" <<'EOF'
{
  "task": "smoke test task",
  "stages": [["analyst"], ["backend"], ["reviewer"]],
  "completed_stages": 3,
  "needs_creation": []
}
EOF

cat > "${TASK_DIR}/progress.buffer.jsonl" <<'EOF'
{"ts":"2026-05-16T12:00:00Z","trace_id":"20260516-120000.20260516-120000-0.0.0","task_id":"20260516-120000-0","session_id":"20260516-120000","event":"STARTED","stage":0,"agent":"","attempt":0,"status":"started","detail":"smoke test"}
{"ts":"2026-05-16T12:00:30Z","trace_id":"20260516-120000.20260516-120000-0.1.1","task_id":"20260516-120000-0","session_id":"20260516-120000","event":"STAGE","stage":1,"agent":"backend","attempt":1,"status":"in_progress","detail":"1/3 — backend"}
{"ts":"2026-05-16T12:05:00Z","trace_id":"20260516-120000.20260516-120000-0.3.1","task_id":"20260516-120000-0","session_id":"20260516-120000","event":"COMPLETED","stage":3,"agent":"","attempt":1,"status":"completed","detail":"branch=smoke-test commits=1"}
EOF

RC=$(run_capture_rc python3 "${SCRIPTS_DIR}/validate-state-schema.py" \
       --state-dir "${STATE_DIR}" --task-dir "${TASK_DIR}")
# Expected: rc=1 because session.json/capabilities.json absent (soft-warn class).
assert_eq "valid state → soft-warn rc (1)" "1" "${RC}"

# Invalid: malformed register.json — missing required field.
cat > "${TASK_DIR}/register.json" <<EOF
{
  "schema_version": 1,
  "task_id": "${TASK_ID}",
  "session_id": "20260516-120000",
  "current_phase": "phase_2"
}
EOF
RC=$(run_capture_rc python3 "${SCRIPTS_DIR}/validate-state-schema.py" \
       --state-dir "${STATE_DIR}" --task-dir "${TASK_DIR}")
assert_eq "missing required field → hard error (2)" "2" "${RC}"

# Invalid: bad enum value.
cat > "${TASK_DIR}/register.json" <<EOF
{
  "schema_version": 1,
  "task_id": "${TASK_ID}",
  "session_id": "20260516-120000",
  "task": "x",
  "branch": "x",
  "project_root": "/tmp",
  "task_dir": "${TASK_DIR}",
  "execution_mode": "single",
  "current_phase": "bogus_phase",
  "approval_status": "approved",
  "verification_status": "passed"
}
EOF
RC=$(run_capture_rc python3 "${SCRIPTS_DIR}/validate-state-schema.py" \
       --state-dir "${STATE_DIR}" --task-dir "${TASK_DIR}")
assert_eq "bad enum value → hard error (2)" "2" "${RC}"

# Restore valid register for the rest of the suite.
cat > "${TASK_DIR}/register.json" <<EOF
{
  "schema_version": 1,
  "task_id": "${TASK_ID}",
  "session_id": "20260516-120000",
  "task": "smoke test task",
  "branch": "smoke-test",
  "project_root": "/tmp",
  "task_dir": "${TASK_DIR}",
  "execution_mode": "single",
  "current_phase": "completed",
  "approval_status": "approved",
  "verification_status": "passed"
}
EOF

# --------------------------------------------------------------------------- #
echo ""
echo "[2/4] F5 — progress.buffer.jsonl row schema"
echo "------------------------------------"
# --------------------------------------------------------------------------- #

# Add a row with all required fields → should pass schema row-by-row.
cat >> "${TASK_DIR}/progress.buffer.jsonl" <<'EOF'
{"ts":"2026-05-16T12:05:01Z","trace_id":"20260516-120000.20260516-120000-0.3.1","task_id":"20260516-120000-0","session_id":"20260516-120000","event":"STAGE_DONE","stage":3,"agent":"reviewer","attempt":1,"status":"completed","detail":"reviewer — APPROVED"}
EOF
RC=$(run_capture_rc python3 "${SCRIPTS_DIR}/validate-state-schema.py" \
       --state-dir "${STATE_DIR}" --task-dir "${TASK_DIR}")
assert_eq "F5 buffer well-formed → soft-warn (1)" "1" "${RC}"

# Inject a malformed line — missing required ts.
cat >> "${TASK_DIR}/progress.buffer.jsonl" <<'EOF'
{"trace_id":"x","task_id":"20260516-120000-0","event":"BOGUS","stage":0}
EOF
RC=$(run_capture_rc python3 "${SCRIPTS_DIR}/validate-state-schema.py" \
       --state-dir "${STATE_DIR}" --task-dir "${TASK_DIR}")
assert_eq "F5 row missing required field → hard error (2)" "2" "${RC}"

# Remove the bad line for the rest of the suite.
head -n -1 "${TASK_DIR}/progress.buffer.jsonl" > "${TASK_DIR}/progress.buffer.jsonl.tmp"
mv "${TASK_DIR}/progress.buffer.jsonl.tmp" "${TASK_DIR}/progress.buffer.jsonl"

# --------------------------------------------------------------------------- #
echo ""
echo "[3/4] G6 — forbid-plaintext-approval validator"
echo "------------------------------------"
# --------------------------------------------------------------------------- #

# Forbidden English phrase.
RC=$(run_capture_rc python3 "${SCRIPTS_DIR}/check-plaintext-approval.py" \
       --text "Implementation is complete. Shall I merge and push?")
assert_eq "English 'Shall I' → violation (2)" "2" "${RC}"

# Forbidden Korean phrase.
RC=$(run_capture_rc python3 "${SCRIPTS_DIR}/check-plaintext-approval.py" \
       --text "구현 완료했습니다. 푸시 진행할까요?")
assert_eq "Korean '진행할까요?' → violation (2)" "2" "${RC}"

# Clean output.
RC=$(run_capture_rc python3 "${SCRIPTS_DIR}/check-plaintext-approval.py" \
       --text "STATUS: completed. Branch: feat/api. Commits: 2.")
assert_eq "Clean output → ok (0)" "0" "${RC}"

# False-positive guard.
RC=$(run_capture_rc python3 "${SCRIPTS_DIR}/check-plaintext-approval.py" \
       --text "Can I help with anything else?")
assert_eq "'Can I help' → no violation (0)" "0" "${RC}"

# Non-Agent tool input → silently skip.
RC=$(run_capture_rc bash -c "echo '{\"tool_name\":\"Bash\",\"tool_response\":{\"content\":\"Shall I commit?\"}}' \
       | python3 \"${SCRIPTS_DIR}/check-plaintext-approval.py\"")
assert_eq "non-Agent tool filtered → ok (0)" "0" "${RC}"

# --------------------------------------------------------------------------- #
echo ""
echo "[4/4] J13 — telemetry aggregator"
echo "------------------------------------"
# --------------------------------------------------------------------------- #

# Add a cost JSONL so token totals are populated.
cat > "${STATE_DIR}/cost/${TASK_ID}.jsonl" <<EOF
{"ts":"2026-05-16T12:00:30Z","task_id":"${TASK_ID}","session_id":"20260516-120000","agent":"backend","stage":1,"model":"claude-sonnet-4-6","tier":"balanced","input_tokens":10000,"output_tokens":2000,"cache_creation_tokens":0,"cache_read_tokens":8000}
EOF

# Add a blocked second task so the summary's blocker histogram is exercised.
TASK_ID2="20260516-130000-0"
TASK_DIR2="${STATE_DIR}/tasks/${TASK_ID2}"
mkdir -p "${TASK_DIR2}"
cat > "${TASK_DIR2}/register.json" <<EOF
{
  "schema_version": 1,
  "task_id": "${TASK_ID2}",
  "session_id": "20260516-130000",
  "task": "smoke blocked",
  "branch": "smoke-blocked",
  "project_root": "/tmp",
  "task_dir": "${TASK_DIR2}",
  "execution_mode": "single",
  "current_phase": "blocked",
  "approval_status": "approved",
  "verification_status": "failed",
  "blocked_by": ["validation_budget_exceeded"]
}
EOF
cat > "${TASK_DIR2}/progress.buffer.jsonl" <<EOF
{"ts":"2026-05-16T13:00:00Z","trace_id":"x","task_id":"${TASK_ID2}","session_id":"20260516-130000","event":"STARTED","stage":0,"agent":"","attempt":0,"status":"started","detail":"smoke blocked"}
{"ts":"2026-05-16T13:05:00Z","trace_id":"x","task_id":"${TASK_ID2}","session_id":"20260516-130000","event":"BLOCKED","stage":1,"agent":"reviewer","attempt":3,"status":"failed","detail":"validation_budget_exceeded"}
EOF

# JSON output — verify aggregate fields.
JSON=$(python3 "${SCRIPTS_DIR}/telemetry-aggregate.py" \
        --state-dir "${STATE_DIR}" --recent 10 --format json)
TASKS_TOTAL=$(printf '%s' "${JSON}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['summary']['tasks_total'])")
COMPLETED=$(printf '%s' "${JSON}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['summary']['tasks_completed'])")
BLOCKED=$(printf '%s' "${JSON}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['summary']['tasks_blocked'])")
TOTAL_TOKENS=$(printf '%s' "${JSON}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['summary']['total_tokens'])")
BLOCKER_COUNT=$(printf '%s' "${JSON}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['summary']['by_blocker'].get('validation_budget_exceeded',0))")

assert_eq "telemetry tasks_total"     "2"     "${TASKS_TOTAL}"
assert_eq "telemetry tasks_completed" "1"     "${COMPLETED}"
assert_eq "telemetry tasks_blocked"   "1"     "${BLOCKED}"
assert_eq "telemetry total_tokens"    "12000" "${TOTAL_TOKENS}"
assert_eq "telemetry by_blocker"      "1"     "${BLOCKER_COUNT}"

# Text format prints something nontrivial.
TEXT_OUT=$(python3 "${SCRIPTS_DIR}/telemetry-aggregate.py" \
            --state-dir "${STATE_DIR}" --recent 10 2>&1)
if printf '%s' "${TEXT_OUT}" | grep -q "Tasks: 2 total"; then
  PASS=$((PASS + 1))
  printf '  PASS  %s\n' "text format summary line present"
else
  FAIL=$((FAIL + 1))
  LAST_FAIL="text format missing 'Tasks: 2 total'"
  printf '  FAIL  %s\n' "text format summary line missing"
fi

# --------------------------------------------------------------------------- #
echo ""
echo "------------------------------------"
echo "Result: ${PASS} passed, ${FAIL} failed"
# --------------------------------------------------------------------------- #
if [ "${FAIL}" -gt 0 ]; then
  echo "Last failure: ${LAST_FAIL}"
  exit 1
fi
exit 0
