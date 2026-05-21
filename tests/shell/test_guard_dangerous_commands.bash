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

run_hook_split() {
  local payload="$1"
  local stdout_file="$2"
  local stderr_file="$3"
  shift 3
  printf '%s' "${payload}" | env "$@" bash "${HOOK}" >"${stdout_file}" 2>"${stderr_file}"
}

write_approval() {
  local home="$1"
  local kind="$2"
  local cmd="$3"
  mkdir -p "${home}/approvals"
  python3 -c '
import json, pathlib, sys
from datetime import datetime, timedelta, timezone
path = pathlib.Path(sys.argv[1]) / "approvals" / "dangerous-commands.approved"
path.write_text(json.dumps({
    "approved": True,
    "kind": sys.argv[2],
    "command": sys.argv[3],
    "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
}) + "\n", encoding="utf-8")
' "${home}" "${kind}" "${cmd}"
}

TMP_HOME=$(make_tmp)

it "git push is blocked without deterministic approval"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"

it "git push block output identifies push kind"
assert_contains "${out}" "Kind: push"

it "git push block reason is written to stderr"
STDOUT_FILE="$(make_tmp)/stdout"
STDERR_FILE="$(make_tmp)/stderr"
run_hook_split "$(payload_for "git push origin main")" "${STDOUT_FILE}" "${STDERR_FILE}" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_APPROVED_DANGEROUS="
rc=$?
assert_exit 2 "${rc}"
assert_eq "" "$(cat "${STDOUT_FILE}")" "stdout must be empty on block"
assert_contains "$(cat "${STDERR_FILE}")" "Kind: push" "stderr contains block reason"

it "git push block writes audit trail"
audit=$(cat "${TMP_HOME}/audit/dangerous-commands.jsonl")
assert_contains "${audit}" '"decision": "block"'

it "environment approval does not bypass git push"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=1")
rc=$?
assert_exit 2 "${rc}"

it "command-bound approval marker allows git push"
write_approval "${TMP_HOME}" "push" "git push origin main"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"

it "command-bound approval writes allow audit trail"
audit=$(cat "${TMP_HOME}/audit/dangerous-commands.jsonl")
assert_contains "${audit}" '"decision": "allow"'

it "command-bound approval marker is consumed after use"
assert_file_absent "${TMP_HOME}/approvals/dangerous-commands.approved"

it "inline approval env prefix does not self-approve git push"
out=$(run_hook "$(payload_for "AGENT_CREW_APPROVED_DANGEROUS=1 git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: push"

it "legacy APPROVED marker does not allow git push"
mkdir -p "${TMP_HOME}/approvals"
printf 'APPROVED\n' > "${TMP_HOME}/approvals/dangerous-commands.approved"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"

it "approval marker without expiry does not allow git push"
python3 -c '
import json, pathlib, sys
path = pathlib.Path(sys.argv[1]) / "approvals" / "dangerous-commands.approved"
path.write_text(json.dumps({
    "approved": True,
    "kind": "push",
    "command": "git push origin main",
}) + "\n", encoding="utf-8")
' "${TMP_HOME}"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: push"

it "expired approval marker does not allow git push"
python3 -c '
import json, pathlib, sys
path = pathlib.Path(sys.argv[1]) / "approvals" / "dangerous-commands.approved"
path.write_text(json.dumps({
    "approved": True,
    "kind": "push",
    "command": "git push origin main",
    "expires_at": "2000-01-01T00:00:00Z",
}) + "\n", encoding="utf-8")
' "${TMP_HOME}"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: push"

it "approval marker for different command does not allow git push"
write_approval "${TMP_HOME}" "push" "git push origin other"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"

it "rm -fr root is blocked"
out=$(run_hook "$(payload_for "rm -fr /")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: destructive-delete"

it "rm -rf quoted HOME is blocked"
out=$(run_hook "$(payload_for 'rm -rf "$HOME"')" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: destructive-delete"

it "rm -rf braced HOME is blocked"
out=$(run_hook "$(payload_for 'rm -rf ${HOME}')" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: destructive-delete"

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
