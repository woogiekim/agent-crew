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

make_task_approval() {
  local task_dir="$1"
  local tool_name="$2"
  local tool_input_json="$3"
  local expires_at="${4:-2099-01-01T00:00:00Z}"
  mkdir -p "${task_dir}/context"
  python3 - "${task_dir}/context/tracker-mutation-approval.json" "${tool_name}" "${tool_input_json}" "${expires_at}" <<'PY'
import hashlib
import json
import sys

path, tool_name, tool_input_raw, expires_at = sys.argv[1:5]
tool_input = json.loads(tool_input_raw)
canonical = json.dumps(tool_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
payload = {
    "schema_version": "agent-crew.tracker-mutation-approval.v1",
    "approved": True,
    "tool_name": tool_name,
    "tool_input_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    "scope": "single_tool_payload",
    "external_side_effect": "Plane work item mutation",
    "approved_by": "user",
    "expires_at": expires_at,
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, sort_keys=True)
    f.write("\n")
PY
}

make_blocked_issuer_context() {
  local task_dir="$1"
  mkdir -p "${task_dir}/context"
  cat >"${task_dir}/context/issuer-pipeline.md" <<'EOF'
STATUS: quality_blocked
reason: missing_quality_loop_pipeline
EOF
}

make_active_task_contract() {
  local home_dir="$1"
  local state_key="$2"
  local task_id="$3"
  local project_root="$4"
  local task_dir="${home_dir}/state/${state_key}/tasks/${task_id}"
  mkdir -p "${home_dir}/state/${state_key}/tasks"
  make_task_contract "${task_dir}" "passed"
  cat >"${task_dir}/register.json" <<EOF
{
  "task_id": "${task_id}",
  "project_root": "${project_root}"
}
EOF
  : >"${home_dir}/state/${state_key}/tasks/active.${task_id}"
}

plain_tracker_payload='{
  "project_identifier": "TRACKER",
  "title": "Follow-up work item",
  "description_html": "<p>runtime adapter owns project-specific body validation</p>",
  "label_ids": []
}'

label_payload='{
  "workspace_slug": "workspace",
  "project_id": "project",
  "name": "review-followup",
  "color": "#6366f1"
}'

comment_payload='{
  "workspace_slug": "workspace",
  "project_id": "project",
  "work_item_id": "work-item",
  "comment_html": "<p>status note</p>"
}'

it "direct Plane create without tracker fallback evidence is blocked"
out=$(run_hook "$(payload_for "mcp__plane__create_work_item" "${plain_tracker_payload}")")
rc=$?
assert_exit 2 "${rc}" "missing fallback evidence must block"
assert_contains "${out}" "tracker fallback contract" "block reason names generic contract"
assert_contains "${out}" "approval_required" "block reason escalates to user approval"
assert_contains "${out}" "mcp__plane__create_work_item" "block reason names blocked tool"
assert_contains "${out}" "external_side_effect" "block reason names side effect"
assert_contains "${out}" "approval_scope" "block reason explains approved retry scope"
assert_contains "${out}" "reject" "block reason explains rejection leaves mutation unrun"

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

it "active tracker fallback evidence from another project is ignored"
TMP_HOME="$(make_tmp)/home"
OTHER_PROJECT="$(make_tmp)/other-project"
CURRENT_PROJECT="$(make_tmp)/current-project"
make_active_task_contract "${TMP_HOME}" "other-state" "active-task" "${OTHER_PROJECT}"
out=$(run_hook "$(payload_for "mcp__plane__create_work_item" "${plain_tracker_payload}")" "AGENT_CREW_HOME=${TMP_HOME}" "PROJECT_ROOT=${CURRENT_PROJECT}")
rc=$?
assert_exit 2 "${rc}" "cross-project active fallback evidence must not allow mutation"
assert_contains "${out}" "tracker fallback contract" "cross-project active evidence is ignored"

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

it "Plane mutation with generic fallback contract evidence but no user approval is blocked"
TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed"
out=$(run_hook "$(payload_for "mcp__plane__create_work_item" "${plain_tracker_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "valid fallback payload still requires user approval"
assert_contains "${out}" "approval_required" "block reason asks for user approval"

it "Plane mutation with fallback contract and matching user approval is allowed"
TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed"
make_task_approval "${TASK_DIR}" "mcp__plane__create_work_item" "${plain_tracker_payload}"
out=$(run_hook "$(payload_for "mcp__plane__create_work_item" "${plain_tracker_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 0 "${rc}" "matching user-approved payload should pass"
assert_eq "" "${out}" "allowed call emits no output"
assert_file_absent "${TASK_DIR}/context/tracker-mutation-approval.json" "approval is consumed after allow"
assert_file_exists "${TASK_DIR}/context/tracker-mutation-approval.consumed.json" "consumed approval record is retained"

out=$(run_hook "$(payload_for "mcp__plane__create_work_item" "${plain_tracker_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "same approval must not allow the same mutation twice"
assert_contains "${out}" "approval_required" "replay requires a new user approval"

it "Plane mutation approval is bound to exact tool and payload"
TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed"
make_task_approval "${TASK_DIR}" "mcp__plane__create_work_item" "${plain_tracker_payload}"
out=$(run_hook "$(payload_for "mcp__plane__update_work_item" "${plain_tracker_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "approval for create must not allow update"
assert_contains "${out}" "approval tool mismatch" "block reason names tool mismatch"

changed_payload='{
  "project_identifier": "TRACKER",
  "title": "Changed follow-up work item",
  "description_html": "<p>runtime adapter owns project-specific body validation</p>",
  "label_ids": []
}'
out=$(run_hook "$(payload_for "mcp__plane__create_work_item" "${changed_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "approval for one payload must not allow another payload"
assert_contains "${out}" "approval payload mismatch" "block reason names payload mismatch"

it "additional Plane mutating tools require approval"
TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed"
out=$(run_hook "$(payload_for "mcp__plane__create_label" "${label_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "create_label must not bypass tracker mutation approval"
assert_contains "${out}" "approval_required" "create_label asks for user approval"

TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed"
out=$(run_hook "$(payload_for "mcp__plane__create_work_item_comment" "${comment_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 2 "${rc}" "create_work_item_comment must not bypass tracker mutation approval"
assert_contains "${out}" "approval_required" "create_work_item_comment asks for user approval"

it "additional Plane mutating tools with matching approval are allowed once"
TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed"
make_task_approval "${TASK_DIR}" "mcp__plane__create_label" "${label_payload}"
out=$(run_hook "$(payload_for "mcp__plane__create_label" "${label_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 0 "${rc}" "approved create_label should pass"

TASK_DIR="$(make_tmp)/task"
make_task_contract "${TASK_DIR}" "passed"
make_task_approval "${TASK_DIR}" "mcp__plane__create_work_item_comment" "${comment_payload}"
out=$(run_hook "$(payload_for "mcp__plane__create_work_item_comment" "${comment_payload}")" "AGENT_CREW_TASK_DIR=${TASK_DIR}")
rc=$?
assert_exit 0 "${rc}" "approved create_work_item_comment should pass"

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
assert_contains "${codex_setup}" "mcp__plane__create_label" "Codex matcher includes create_label"
assert_contains "${codex_setup}" "mcp__plane__create_work_item_comment" "Codex matcher includes create_work_item_comment"
assert_contains "${claude_setup}" "tracker-mutation-guard.sh" "Claude setup must register the guard"
assert_contains "${claude_setup}" "mcp__plane__delete_work_item" "Claude matcher includes delete"
assert_contains "${claude_setup}" "mcp__plane__create_label" "Claude matcher includes create_label"
assert_contains "${claude_setup}" "mcp__plane__create_work_item_comment" "Claude matcher includes create_work_item_comment"

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
