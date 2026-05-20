#!/usr/bin/env bash
# Tests for deterministic dangerous command blocking and audit trail.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

HOOK="${HOOKS_DIR}/guard-dangerous-commands.sh"

payload_for() {
  local cmd="$1"
  python3 -c '
import json, sys
print(json.dumps({"tool_name": "exec_command", "tool_input": {"cmd": sys.argv[1]}}))
' "${cmd}"
}

run_hook() {
  local payload="$1"
  shift
  printf '%s' "${payload}" | env "$@" bash "${HOOK}" 2>&1
}

TMP_HOME=$(make_tmp)

it "git push is blocked without deterministic approval"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"

it "git push block output identifies push kind"
assert_contains "${out}" "Kind: push"

it "git push block writes audit trail"
audit=$(cat "${TMP_HOME}/audit/dangerous-commands.jsonl")
assert_contains "${audit}" '"decision": "block"'

it "approved git push is allowed silently"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=1")
rc=$?
assert_exit 0 "${rc}"

it "approved git push writes allow audit trail"
audit=$(cat "${TMP_HOME}/audit/dangerous-commands.jsonl")
assert_contains "${audit}" '"decision": "allow"'

it "inline approval env prefix does not self-approve git push"
out=$(run_hook "$(payload_for "AGENT_CREW_APPROVED_DANGEROUS=1 git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: push"

it "approval marker file allows git push"
mkdir -p "${TMP_HOME}/approvals"
printf 'APPROVED\n' > "${TMP_HOME}/approvals/dangerous-commands.approved"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"

it "git merge is blocked without deterministic approval"
rm -f "${TMP_HOME}/approvals/dangerous-commands.approved"
out=$(run_hook "$(payload_for "git merge feature/example")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: merge"

it "deploy script is blocked without deterministic approval"
out=$(run_hook "$(payload_for "./deploy.sh production")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: deploy"

it "read-only git status is allowed"
out=$(run_hook "$(payload_for "git status -sb")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_eq "" "${out}" "read-only command should produce no block JSON"

end_report
