#!/usr/bin/env bash
# Regression tests for hook-driven automatic agent-crew issue reporting.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

TMP=$(make_tmp)
STATE_DIR="${TMP}/reports"
BIN_DIR="${TMP}/bin"
GH_LOG="${TMP}/gh.log"
mkdir -p "${STATE_DIR}" "${BIN_DIR}"

cat > "${BIN_DIR}/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${GH_LOG}"
if [ "$1 $2" = "issue list" ]; then
  printf '[]\n'
  exit 0
fi
if [ "$1 $2" = "issue create" ]; then
  printf 'https://github.com/woogiekim/agent-crew/issues/999\n'
  exit 0
fi
exit 1
EOF
chmod +x "${BIN_DIR}/gh"

PROMPT_PAYLOAD='{"hook_event_name":"UserPromptSubmit","prompt":"에이전트크루에서 crew run 실행 중 오류가 납니다: traceback boom"}'

it "auto issue reporter creates a GitHub issue for agent-crew error prompts"
out=$(printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${GH_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${STATE_DIR}" \
  python3 "${SCRIPTS_DIR}/auto-issue-reporter.py" --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "auto issue reporter reports created status"
assert_contains "${out}" '"status": "created"'

it "auto issue reporter targets the agent-crew remote repo"
assert_contains "$(cat "${GH_LOG}")" "issue create"
assert_contains "$(cat "${GH_LOG}")" "--repo woogiekim/agent-crew"

it "auto issue reporter stores a local dedup record"
reported_count=$(find "${STATE_DIR}/reported" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
assert_eq "1" "${reported_count}"

it "auto issue reporter skips duplicate prompt reports locally"
out=$(printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${GH_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${STATE_DIR}" \
  python3 "${SCRIPTS_DIR}/auto-issue-reporter.py" --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "auto issue reporter duplicate status is skipped"
assert_contains "${out}" '"status": "skipped_duplicate"'

it "auto issue reporter duplicate did not create another issue"
create_count=$(grep -c 'issue create' "${GH_LOG}" 2>/dev/null || true)
assert_eq "1" "${create_count}"

it "auto issue reporter ignores unrelated errors"
out=$(printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"my local app has an error"}' | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${GH_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/ignore-reports" \
  python3 "${SCRIPTS_DIR}/auto-issue-reporter.py" --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "auto issue reporter ignored status is explicit"
assert_contains "${out}" '"status": "ignored"'

it "auto issue reporter dry-run avoids gh calls"
DRY_LOG="${TMP}/dry-gh.log"
out=$(printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${DRY_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/dry-reports" \
  AGENT_CREW_AUTO_ISSUE_DRY_RUN=1 \
  python3 "${SCRIPTS_DIR}/auto-issue-reporter.py" --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "auto issue reporter dry-run status is explicit"
assert_contains "${out}" '"status": "dry_run"'

it "auto issue reporter dry-run does not call gh"
assert_file_absent "${DRY_LOG}"

TOOL_PAYLOAD='{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"crew status"},"tool_response":{"stderr":"crew: traceback error while reading state","returncode":1}}'

it "auto issue reporter handles Bash tool failures involving crew"
out=$(printf '%s' "${TOOL_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/tool-gh.log" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/tool-reports" \
  python3 "${SCRIPTS_DIR}/auto-issue-reporter.py" --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "created"'

HOST_BRIDGE_PAYLOAD='{"hook_event_name":"PostToolUse","status":"failed","tool_name":"Bash","tool_input":{"command":"crew run \"demo\""},"tool_response":{"stderr":"STATUS: blocked\nBLOCKER: host AI bridge has not completed this handoff","returncode":3}}'

it "auto issue reporter ignores normal host bridge blocked handoffs"
out=$(printf '%s' "${HOST_BRIDGE_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/host-bridge-gh.log" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/host-bridge-reports" \
  python3 "${SCRIPTS_DIR}/auto-issue-reporter.py" --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "ignored"'

it "auto issue hook wrapper is advisory and exits 0"
printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/hook-gh.log" \
  AGENT_CREW_HOME="${REPO_ROOT}/core" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/hook-reports" \
  bash "${HOOKS_DIR}/auto-issue-report.sh" >"${TMP}/hook.out" 2>&1
rc=$?
assert_exit 0 "${rc}"

end_report
