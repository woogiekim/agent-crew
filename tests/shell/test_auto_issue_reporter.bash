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

CREW_BIN="${REPO_ROOT}/core/bin/crew"
PROMPT_PAYLOAD='{"hook_event_name":"UserPromptSubmit","prompt":"에이전트크루에서 crew run 실행 중 오류가 납니다: traceback boom"}'

it "crew report auto records agent-crew error prompts locally by default"
out=$(printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${GH_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${STATE_DIR}" \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew report auto reports recorded status"
assert_contains "${out}" '"status": "recorded"'

it "crew report auto does not call gh by default"
assert_file_absent "${GH_LOG}"

it "crew report auto stores a local dedup record"
reported_count=$(find "${STATE_DIR}/reported" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
assert_eq "1" "${reported_count}"

it "crew report auto stores an outbox report"
outbox_count=$(find "${STATE_DIR}/outbox" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
assert_eq "1" "${outbox_count}"

it "crew report auto stores structured classification metadata"
assert_contains "$(cat "${STATE_DIR}"/outbox/*.json)" '"classification": "user_reported_error"'

it "crew report auto marks captured evidence as untrusted"
assert_contains "$(cat "${STATE_DIR}"/outbox/*.json)" 'Detected Signal (Untrusted Evidence)'

it "legacy reporter entrypoint still stores native reports"
out=$(printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/legacy-reports" \
  python3 "${SCRIPTS_DIR}/auto-issue-reporter.py" --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "recorded"'

SECRET_STATE_DIR="${TMP}/secret-reports"
SECRET_PAYLOAD='{"hook_event_name":"UserPromptSubmit","prompt":"agent-crew error: traceback with token=ghp_SECRETSECRET123 and password=my-secret"}'
printf '%s' "${SECRET_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${SECRET_STATE_DIR}" \
  bash "${CREW_BIN}" report auto --format json >/dev/null 2>&1

it "crew report auto redacts secrets in native outbox"
grep -R "ghp_SECRETSECRET123\|my-secret" "${SECRET_STATE_DIR}" >/dev/null 2>&1
rc=$?
assert_exit 1 "${rc}"

it "crew report auto leaves redaction markers in native outbox"
grep -R "\[REDACTED\]" "${SECRET_STATE_DIR}" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

it "crew report auto skips duplicate prompt reports locally"
out=$(printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${GH_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${STATE_DIR}" \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew report auto duplicate status is skipped"
assert_contains "${out}" '"status": "skipped_duplicate"'

it "crew report auto duplicate still did not create an issue"
create_count=0
if [ -f "${GH_LOG}" ]; then
  create_count=$(grep -c 'issue create' "${GH_LOG}" 2>/dev/null || true)
fi
assert_eq "0" "${create_count}"

PUBLISH_STATE_DIR="${TMP}/publish-reports"
PUBLISH_GH_LOG="${TMP}/publish-gh.log"

it "crew report auto can publish through GitHub backend when explicitly enabled"
out=$(printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${PUBLISH_GH_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${PUBLISH_STATE_DIR}" \
  AGENT_CREW_REPORT_PUBLISH=github \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "created"'

it "crew report GitHub publisher targets the agent-crew remote repo"
assert_contains "$(cat "${PUBLISH_GH_LOG}")" "issue create"
assert_contains "$(cat "${PUBLISH_GH_LOG}")" "--repo woogiekim/agent-crew"

PENDING_STATE_DIR="${TMP}/pending-reports"
PENDING_GH_LOG="${TMP}/pending-gh.log"
printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${PENDING_STATE_DIR}" \
  bash "${CREW_BIN}" report auto --format json >/dev/null 2>&1

it "crew report publish flushes local outbox through GitHub backend"
out=$(PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${PENDING_GH_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${PENDING_STATE_DIR}" \
  bash "${CREW_BIN}" report publish --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "published"'

it "crew report publish removes successfully published outbox item"
pending_outbox_count=$(find "${PENDING_STATE_DIR}/outbox" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
assert_eq "0" "${pending_outbox_count}"

it "crew report auto ignores unrelated errors"
out=$(printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"my local app has an error"}' | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${GH_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/ignore-reports" \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew report auto ignored status is explicit"
assert_contains "${out}" '"status": "ignored"'

it "crew report auto dry-run avoids GitHub publication"
DRY_LOG="${TMP}/dry-gh.log"
out=$(printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${DRY_LOG}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/dry-reports" \
  AGENT_CREW_AUTO_ISSUE_DRY_RUN=1 \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew report auto dry-run status is explicit"
assert_contains "${out}" '"status": "dry_run"'

it "crew report auto dry-run does not call gh"
assert_file_absent "${DRY_LOG}"

TOOL_PAYLOAD='{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"crew status"},"tool_response":{"stderr":"crew: traceback error while reading state","returncode":1}}'

it "crew report auto handles Bash tool failures involving crew"
out=$(printf '%s' "${TOOL_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/tool-gh.log" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/tool-reports" \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "recorded"'

HOST_BRIDGE_PAYLOAD='{"hook_event_name":"PostToolUse","status":"failed","tool_name":"Bash","tool_input":{"command":"crew run \"demo\""},"tool_response":{"stderr":"STATUS: blocked\nBLOCKER: host AI bridge has not completed this handoff","returncode":3}}'

it "crew report auto ignores normal host bridge blocked handoffs"
out=$(printf '%s' "${HOST_BRIDGE_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/host-bridge-gh.log" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/host-bridge-reports" \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "ignored"'

HANDOFF_READY_PAYLOAD='{"hook_event_name":"PostToolUse","status":"completed","tool_name":"Bash","tool_input":{"command":"crew run \"demo\""},"tool_response":{"stdout":"STATUS: handoff_ready\nHOST_BRIDGE: internal_handoff_ready","returncode":0}}'

it "crew report auto ignores resumable internal handoff-ready runs"
out=$(printf '%s' "${HANDOFF_READY_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/handoff-ready-gh.log" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/handoff-ready-reports" \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "ignored"'

STRUCTURED_BLOCKER_PAYLOAD='{"hook_event_name":"PostToolUse","status":"failed","tool_name":"Bash","tool_input":{"command":"crew status"},"tool_response":{"stderr":"STATUS: blocked\nBLOCKER: state_schema_invalid","returncode":3}}'

it "crew report auto records structured infrastructure blockers from Bash crew output"
out=$(printf '%s' "${STRUCTURED_BLOCKER_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/structured-blocker-gh.log" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/structured-blocker-reports" \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "recorded"'

SUPERVISOR_BLOCKED_PAYLOAD='{"source":"supervisor_blocked","status":"blocked","blocker":"state_schema_invalid","task_id":"20260523-000000-0","detail":"validate-state-schema.py failed with token=secret123"}'

it "crew report auto records sanitized supervisor infrastructure blocked reports"
out=$(printf '%s' "${SUPERVISOR_BLOCKED_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/supervisor-blocked-gh.log" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/supervisor-blocked-reports" \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "recorded"'
assert_contains "$(cat "${TMP}"/supervisor-blocked-reports/outbox/*.json)" '"classification": "infrastructure_blocker"'
grep -R "token=secret123" "${TMP}/supervisor-blocked-reports" >/dev/null 2>&1
rc=$?
assert_exit 1 "${rc}"

SUPERVISOR_HOOK_BLOCKED_PAYLOAD='{"source":"supervisor_blocked","status":"blocked","blocker":"hook_failure_missing_asset","task_id":"20260523-000001-0","detail":"hook failed because runtime asset is missing"}'

it "crew report auto recognizes hook and missing-asset supervisor blockers"
out=$(printf '%s' "${SUPERVISOR_HOOK_BLOCKED_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/supervisor-hook-blocked-gh.log" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/supervisor-hook-blocked-reports" \
  bash "${CREW_BIN}" report auto --format json 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"status": "recorded"'

FAKE_HOME="${TMP}/fake-home"
FAKE_CREW_LOG="${TMP}/fake-crew.log"
mkdir -p "${FAKE_HOME}/bin"
cat > "${FAKE_HOME}/bin/crew" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_CREW_LOG}"
cat >/dev/null
exit 0
EOF
chmod +x "${FAKE_HOME}/bin/crew"

it "auto issue hook wrapper delegates to crew report"
printf '%s' "${PROMPT_PAYLOAD}" | \
  FAKE_CREW_LOG="${FAKE_CREW_LOG}" \
  AGENT_CREW_HOME="${FAKE_HOME}" \
  bash "${HOOKS_DIR}/auto-issue-report.sh" >"${TMP}/hook.out" 2>&1
rc=$?
assert_exit 0 "${rc}"
assert_contains "$(cat "${FAKE_CREW_LOG}")" "report auto"

it "auto issue hook wrapper fast-rejects unrelated prompts"
cat > "${FAKE_HOME}/bin/crew" <<'EOF'
#!/usr/bin/env bash
printf 'crew should not run\n' >&2
exit 88
EOF
chmod +x "${FAKE_HOME}/bin/crew"
printf '{"hook_event_name":"UserPromptSubmit","prompt":"hello"}' | \
  AGENT_CREW_HOME="${FAKE_HOME}" \
  bash "${HOOKS_DIR}/auto-issue-report.sh" >"${TMP}/hook-fast.out" 2>&1
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "$(cat "${TMP}/hook-fast.out")"

it "auto issue hook wrapper is advisory and exits 0 when reporting fails"
cat > "${FAKE_HOME}/bin/crew" <<'EOF'
#!/usr/bin/env bash
cat >/dev/null
exit 42
EOF
chmod +x "${FAKE_HOME}/bin/crew"
printf '%s' "${PROMPT_PAYLOAD}" | \
  PATH="${BIN_DIR}:${PATH}" \
  GH_LOG="${TMP}/hook-gh.log" \
  AGENT_CREW_HOME="${FAKE_HOME}" \
  AGENT_CREW_AUTO_ISSUE_STATE_DIR="${TMP}/hook-reports" \
  bash "${HOOKS_DIR}/auto-issue-report.sh" >"${TMP}/hook.out" 2>&1
rc=$?
assert_exit 0 "${rc}"

end_report
