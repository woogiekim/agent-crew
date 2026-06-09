#!/usr/bin/env bash
# Regression coverage for issue #180.
#
# Direct Plane MCP mutations must not bypass a blocked issuer pipeline. The
# guard stays generic: project-specific tracker adapter rules must be validated
# by runtime fallback evidence, not encoded in tracked framework source.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

HOOK="${HOOKS_DIR}/tracker-mutation-guard.sh"

payload_for() {
  local tool_name="$1"
  local tool_input_json="$2"
  python3 -c '
import json, sys
print(json.dumps({
    "tool_name": sys.argv[1],
    "tool_input": json.loads(sys.argv[2]),
}))
' "${tool_name}" "${tool_input_json}"
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

make_task_contract() {
  local task_dir="$1"
  local validation_status="${2:-passed}"
  local adapter_contract_loaded="${3:-true}"
  local payload_validated="${4:-true}"
  mkdir -p "${task_dir}/context"
  cat >"${task_dir}/context/specialist-dispatch.md" <<'EOF'
selected_agent: issuer
selection_reason: tracker mutation fallback requires issuer lifecycle dispatcher
execution_mode: current-session-fallback
EOF
  cat >"${task_dir}/context/tracker-fallback-validation.json" <<EOF
{
  "status": "${validation_status}",
  "agent": "issuer",
  "adapter_contract_loaded": ${adapter_contract_loaded},
  "payload_validated": ${payload_validated}
}
EOF
}

make_blocked_issuer_context() {
  local task_dir="$1"
  mkdir -p "${task_dir}/context"
  cat >"${task_dir}/context/issuer-pipeline.md" <<'EOF'
STATUS: quality_blocked
reason: missing_quality_loop_pipeline
EOF
}

plain_tracker_payload='{
  "project_identifier": "TRACKER",
  "title": "Follow-up work item",
  "description_html": "<p>runtime adapter owns project-specific body validation</p>",
  "label_ids": []
}'

it "direct Plane create without tracker fallback evidence is blocked"
out=$(run_hook "$(payload_for "mcp__plane__create_work_item" "${plain_tracker_payload}")")
rc=$?
assert_exit 2 "${rc}" "missing fallback evidence must block"
assert_contains "${out}" "tracker fallback contract" "block reason names generic contract"

it "block reason is written to stderr"
STDOUT_FILE="$(make_tmp)/stdout"
STDERR_FILE="$(make_tmp)/stderr"
run_hook_split "$(payload_for "mcp__plane__create_work_item" "${plain_tracker_payload}")" "${STDOUT_FILE}" "${STDERR_FILE}"
rc=$?
assert_exit 2 "${rc}" "missing fallback evidence must block"
assert_eq "" "$(cat "${STDOUT_FILE}")" "stdout must be empty on block"
assert_contains "$(cat "${STDERR_FILE}")" '"decision": "block"' "stderr has block JSON"

it "blocked issuer pipeline cannot be followed by direct Plane mutation"
TASK_DIR="$(make_tmp)/task"
make_blocked_issuer_context "${TASK_DIR}"
out=$(run_hook "$(payload_for "mcp__plane__create_work_item" "${plain_tracker_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "missing_quality_loop_pipeline must not allow direct mutation"
assert_contains "${out}" "tracker fallback contract" "blocked issuer pipeline still requires fallback contract"

it "failed tracker fallback validation evidence still blocks"
TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "failed"
out=$(run_hook "$(payload_for "mcp__plane__update_work_item" "${plain_tracker_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "failed validation evidence must block"
assert_contains "${out}" "tracker fallback validation" "reason names validation status"

it "fallback evidence must confirm adapter contract and payload validation"
TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed" "false" "true"
out=$(run_hook "$(payload_for "mcp__plane__update_work_item" "${plain_tracker_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "missing adapter contract validation must block"
assert_contains "${out}" "adapter contract" "reason names adapter contract validation"

TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed" "true" "false"
out=$(run_hook "$(payload_for "mcp__plane__update_work_item" "${plain_tracker_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "missing payload validation must block"
assert_contains "${out}" "payload validation" "reason names payload validation"

it "Plane mutation with generic fallback contract evidence is allowed"
TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed"
out=$(run_hook "$(payload_for "mcp__plane__create_work_item" "${plain_tracker_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 0 "${rc}" "valid fallback payload should pass"
assert_eq "" "${out}" "allowed call emits no output"

it "non-mutating Plane reads are ignored"
out=$(run_hook "$(payload_for "mcp__plane__retrieve_work_item" '{"project_identifier":"TRACKER"}')")
rc=$?
assert_exit 0 "${rc}" "read-only Plane tool should pass"
assert_eq "" "${out}" "read-only call emits no output"

it "setup registers tracker mutation guard for Plane mutating tools"
codex_setup=$(cat "${REPO_ROOT}/adapters/codex/setup.sh")
claude_setup=$(cat "${REPO_ROOT}/adapters/claude/setup.sh")
assert_contains "${codex_setup}" "tracker-mutation-guard.sh" "Codex setup must register the guard"
assert_contains "${codex_setup}" "mcp__plane__create_work_item" "Codex matcher includes create"
assert_contains "${codex_setup}" "mcp__plane__update_work_item" "Codex matcher includes update"
assert_contains "${claude_setup}" "tracker-mutation-guard.sh" "Claude setup must register the guard"
assert_contains "${claude_setup}" "mcp__plane__delete_work_item" "Claude matcher includes delete"

it "tracked guard changes do not encode user skill or project-template specifics"
guard_source="$(cat "${HOOK}")"
test_source="$(cat "$0")"
setup_source="${codex_setup}${claude_setup}"
forbidden_skill="$(printf '%s-%s' "issuer" "plane")"
forbidden_project="$(printf '%s%s%s%s%s' "E" "N" "R" "T" "C")"
forbidden_project_id="$(
  python3 -c 'print("".join(chr(c) for c in [55,48,98,53,99,53,53,97,45,55,50,52,54,45,52,97,51,51,45,56,57,57,54,45,99,48,51,55,100,55,54,50,48,100,98,55]))'
)"
forbidden_section="$(printf '%s %s' "기본" "정보")"

assert_not_contains "${guard_source}" "${forbidden_skill}" "guard must not name user-owned adapter skill"
assert_not_contains "${guard_source}" "${forbidden_project}" "guard must not encode project identifier"
assert_not_contains "${guard_source}" "${forbidden_project_id}" "guard must not encode project id"
assert_not_contains "${guard_source}" "${forbidden_section}" "guard must not encode pinned project template sections"
assert_not_contains "${test_source}" "${forbidden_skill}" "regression test must stay generic"
assert_not_contains "${setup_source}" "${forbidden_skill}" "setup comments must stay generic"
assert_not_contains "${setup_source}" "${forbidden_project}" "setup comments must stay generic"

end_report
