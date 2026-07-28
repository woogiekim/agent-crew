#!/usr/bin/env bash
# Regression coverage for issue #125: STOP/ROUTE soft directives need
# post-response validation when a host hook surface exists.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

VALIDATOR="${SCRIPTS_DIR}/check-route-directive-compliance.py"
WRAPPER="${HOOKS_DIR}/route-directive-guard.sh"
# Widened alias list under test (prd.md § "Selected Solution", AC-001..AC-003):
# both gates must accept this pipe-delimited alternation instead of the bare
# "Agent" literal.
ALIAS_TOOL='Agent|multi_agent_v1wait_agent'

make_payload() {
  local directive="$1"
  local response="$2"
  local tool_name="${3:-Agent}"
  python3 - "$directive" "$response" "$tool_name" <<'PYEOF'
import json
import sys

print(json.dumps({
    "tool_name": sys.argv[3],
    "tool_input": {"prompt": sys.argv[1]},
    "tool_response": {"content": sys.argv[2]},
}))
PYEOF
}

make_payload_no_tool_name() {
  local directive="$1"
  local response="$2"
  python3 - "$directive" "$response" <<'PYEOF'
import json
import sys

print(json.dumps({
    "tool_input": {"prompt": sys.argv[1]},
    "tool_response": {"content": sys.argv[2]},
}))
PYEOF
}

run_validator_payload() {
  local payload="$1"
  local err_file="$2"
  set +e
  printf '%s' "${payload}" | python3 "${VALIDATOR}" 2>"${err_file}"
  local rc=$?
  printf '%s' "${rc}"
}

run_validator_payload_with_tool() {
  local payload="$1"
  local err_file="$2"
  local tool="$3"
  set +e
  printf '%s' "${payload}" | python3 "${VALIDATOR}" --tool "${tool}" 2>"${err_file}"
  local rc=$?
  printf '%s' "${rc}"
}

make_prompt_payload() {
  local prompt="$1"
  python3 -c 'import json,sys; print(json.dumps({"prompt": sys.argv[1]}))' "${prompt}"
}

run_auto_route_ctx() {
  local payload="$1"
  python3 -c '
import json, sys
raw = sys.stdin.read().strip()
if raw:
    print(json.loads(raw).get("hookSpecificOutput", {}).get("additionalContext", ""))
' < <(printf '%s' "${payload}" | bash "${HOOKS_DIR}/auto-route.sh" 2>/dev/null)
}

TMP="$(make_tmp)"

it "route directive validator blocks STOP responses that answer inline"
ERR="${TMP}/stop.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.')"
RC="$(run_validator_payload "${PAYLOAD}" "${ERR}")"
assert_exit 2 "${RC}"

it "route directive validator explains expected STOP action"
assert_contains "$(cat "${ERR}")" "crew:run" "STOP violation should point to crew:run"

it "route directive validator allows STOP responses with crew:run evidence"
ERR="${TMP}/stop-ok.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'TASK_ID: 20260528-1\nSTATUS: handoff_ready')"
RC="$(run_validator_payload "${PAYLOAD}" "${ERR}")"
assert_exit 0 "${RC}"

it "route directive validator blocks ROUTE responses that answer inline"
ERR="${TMP}/route.err"
PAYLOAD="$(make_payload '[agent-crew] ROUTE — question detected, routing to analyst.' '네, Codex에는 그런 기능이 있습니다.')"
RC="$(run_validator_payload "${PAYLOAD}" "${ERR}")"
assert_exit 2 "${RC}"

it "route directive validator explains expected ROUTE action"
assert_contains "$(cat "${ERR}")" "crew:agent" "ROUTE violation should point to crew:agent"

it "route directive validator allows ROUTE responses with crew:agent evidence"
ERR="${TMP}/route-ok.err"
PAYLOAD="$(make_payload '[agent-crew] ROUTE — question detected, routing to analyst.' 'AGENT_REQUEST_ID: agent-1\nSTATUS: handoff_ready')"
RC="$(run_validator_payload "${PAYLOAD}" "${ERR}")"
assert_exit 0 "${RC}"

it "route directive validator ignores Agent responses without route directives"
ERR="${TMP}/none.err"
PAYLOAD="$(make_payload 'ordinary agent prompt' 'plain answer')"
RC="$(run_validator_payload "${PAYLOAD}" "${ERR}")"
assert_exit 0 "${RC}"

it "route directive hook wrapper forwards to installed validator"
HOME_DIR="${TMP}/home"
mkdir -p "${HOME_DIR}/.agent-crew/scripts"
cp "${VALIDATOR}" "${HOME_DIR}/.agent-crew/scripts/check-route-directive-compliance.py"
ERR="${TMP}/wrapper.err"
PAYLOAD="$(make_payload '[agent-crew] ROUTE — question detected.' 'Inline answer')"
set +e
AGENT_CREW_HOME="${HOME_DIR}/.agent-crew" printf '%s' "${PAYLOAD}" | AGENT_CREW_HOME="${HOME_DIR}/.agent-crew" bash "${WRAPPER}" 2>"${ERR}"
RC=$?
assert_exit 2 "${RC}"

it "Claude setup registers route-directive-guard for Agent PostToolUse"
assert_contains "$(cat "${REPO_ROOT}/adapters/claude/setup.sh")" "route-directive-guard.sh" "Claude adapter registration"

it "Codex setup registers PostToolUse dispatcher in hooks.json"
assert_contains "$(cat "${REPO_ROOT}/adapters/codex/setup.sh")" "post-tool-use-dispatcher.sh" "Codex adapter dispatcher registration"

it "Codex PostToolUse dispatcher invokes route-directive-guard"
assert_contains "$(cat "${REPO_ROOT}/core/hooks/post-tool-use-dispatcher.sh")" "route-directive-guard.sh" "Codex dispatcher route guard registration"

it "auto-route natural language emits no route lock"
CTX="$(run_auto_route_ctx "$(make_prompt_payload '수정해줘 파일')")"
assert_eq "" "${CTX}"

it "auto-route explicit crew:run emits command context without route lock"
CTX="$(run_auto_route_ctx "$(make_prompt_payload '$crew:run 수정해줘 파일')")"
assert_contains "${CTX}" "[agent-crew] COMMAND" "explicit command context"
assert_not_contains "${CTX}" "ROUTE_LOCK: crew:run" "no STOP route lock"
assert_not_contains "${CTX}" "ROUTE_LOCK: crew:agent" "no ROUTE route lock"

it "auto-route command context removes inline-answer escape wording"
assert_not_contains "${CTX}" "ONLY permitted inline response" "ROUTE directive should not invite expanded inline exceptions"

it "global explicit execution rule forbids hidden natural-language routing"
assert_contains "$(cat "${REPO_ROOT}/core/global-agents.md")" "Agent Crew never infers execution intent from plain conversation" "global rule forbids hidden routing"
assert_contains "$(cat "${REPO_ROOT}/core/global-agents.md")" "The user chooses the execution boundary" "global rule requires explicit command"

it "hook-system rule documents route directive compliance"
assert_contains "$(cat "${REPO_ROOT}/core/rules/capabilities/hook-system.md")" "Route directive compliance" "hook-system docs"

# --- multi_agent_v1wait_agent alias widening ---
# Spec: prd.md § "Acceptance Criteria" AC-001..AC-006; handoff.md § "Key
# Technical Decisions". Codex's real spooled PostToolUse payloads never carry
# the literal tool_name "Agent"; these cases prove the widened alias list
# fires end-to-end while spawn_agent / multi_agent_v1send_input stay excluded.

it "success-case - dispatcher default_children widens the route-directive-guard matcher to alias multi_agent_v1wait_agent"
# given: post-tool-use-dispatcher.sh's default_children() fan-out matcher line
# when: inspecting the emitted matcher literal for the route-directive-guard.sh child
# then: it reads the pipe alternation "Agent|multi_agent_v1wait_agent", not the bare "Agent" literal
assert_contains "$(cat "${HOOKS_DIR}/post-tool-use-dispatcher.sh")" "Agent|multi_agent_v1wait_agent:bash" "AC-001 dispatcher matcher widened"

it "success-case - route-directive-guard.sh call site passes the widened --tool alias list"
# given: route-directive-guard.sh's validator invocation line
# when: inspecting its --tool argument literal
# then: it reads --tool "Agent|multi_agent_v1wait_agent", not the bare --tool Agent
assert_contains "$(cat "${WRAPPER}")" '--tool "Agent|multi_agent_v1wait_agent"' "AC-003 call site widened"

it "success-case - validator allows multi_agent_v1wait_agent STOP responses with crew:run evidence"
# given: a multi_agent_v1wait_agent payload with a STOP directive and a compliant response
# when: the validator is invoked with the widened --tool alias list
# then: exit code is 0 (compliant path is not blocked)
ERR="${TMP}/magent-stop-ok.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'TASK_ID: 20260528-1\nSTATUS: handoff_ready' 'multi_agent_v1wait_agent')"
RC="$(run_validator_payload_with_tool "${PAYLOAD}" "${ERR}" "${ALIAS_TOOL}")"
assert_exit 0 "${RC}"

it "failure-case(validation) - validator blocks multi_agent_v1wait_agent STOP responses that answer inline"
# given: the same payload shape but the response answers inline instead of carrying compliance evidence
# when: the validator is invoked with the widened --tool alias list
# then: exit code is 2 (membership-based matching fires for the new tool name)
ERR="${TMP}/magent-stop.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.' 'multi_agent_v1wait_agent')"
RC="$(run_validator_payload_with_tool "${PAYLOAD}" "${ERR}" "${ALIAS_TOOL}")"
assert_exit 2 "${RC}"

it "failure-case(validation) - validator explains expected STOP action for multi_agent_v1wait_agent"
assert_contains "$(cat "${ERR}")" "crew:run" "STOP violation should point to crew:run"

it "failure-case(validation) - validator blocks multi_agent_v1wait_agent ROUTE responses that answer inline"
# given: a multi_agent_v1wait_agent payload with a ROUTE directive and an inline non-compliant response
# when: the validator is invoked with the widened --tool alias list
# then: exit code is 2 with the existing ROUTE violation message
ERR="${TMP}/magent-route.err"
PAYLOAD="$(make_payload '[agent-crew] ROUTE — question detected, routing to analyst.' '네, Codex에는 그런 기능이 있습니다.' 'multi_agent_v1wait_agent')"
RC="$(run_validator_payload_with_tool "${PAYLOAD}" "${ERR}" "${ALIAS_TOOL}")"
assert_exit 2 "${RC}"

it "failure-case(validation) - validator explains expected ROUTE action for multi_agent_v1wait_agent"
assert_contains "$(cat "${ERR}")" "crew:agent" "ROUTE violation should point to crew:agent"

it "boundary-case - wildcard --tool bypasses alias membership for an arbitrary tool_name"
# given: an arbitrary tool_name that matches no alias, with a STOP directive and inline non-compliant response
# when: the validator is invoked with the "*" wildcard escape hatch
# then: exit code is 2 (the wildcard still matches any tool_name, unaffected by the membership-list change)
ERR="${TMP}/wildcard.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.' 'Bash')"
RC="$(run_validator_payload_with_tool "${PAYLOAD}" "${ERR}" "*")"
assert_exit 2 "${RC}"

it "boundary-case - validator does not substring-match a tool_name that only superstrings the alias"
# given: a tool_name that is a superstring of the new alias ("multi_agent_v1wait_agentX"), not an exact list element
# when: the validator is invoked with the widened --tool alias list
# then: exit code is 0 (membership test, not substring containment)
ERR="${TMP}/superstring.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.' 'multi_agent_v1wait_agentX')"
RC="$(run_validator_payload_with_tool "${PAYLOAD}" "${ERR}" "${ALIAS_TOOL}")"
assert_exit 0 "${RC}"

it "success-case - validator's new default --tool value blocks multi_agent_v1wait_agent without an explicit flag"
# given: a multi_agent_v1wait_agent payload with a STOP directive and inline non-compliant response
# when: the validator is invoked with no --tool flag at all (relying on the widened default)
# then: exit code is 2, identical to explicitly passing the alias list
ERR="${TMP}/magent-default.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.' 'multi_agent_v1wait_agent')"
RC="$(run_validator_payload "${PAYLOAD}" "${ERR}")"
assert_exit 2 "${RC}"

it "boundary-case - validator does not block spawn_agent even with an offending STOP prompt"
# given: a spawn_agent payload with a STOP directive and inline non-compliant response
# when: the validator is invoked with the widened --tool alias list
# then: exit code is 0 -- spawn_agent is confirmed ack-only and deliberately excluded (AC-004)
ERR="${TMP}/spawn-agent.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.' 'spawn_agent')"
RC="$(run_validator_payload_with_tool "${PAYLOAD}" "${ERR}" "${ALIAS_TOOL}")"
assert_exit 0 "${RC}"

it "boundary-case - validator does not block multi_agent_v1send_input even with an offending STOP prompt"
# given: a multi_agent_v1send_input payload with a STOP directive and inline non-compliant response
# when: the validator is invoked with the widened --tool alias list
# then: exit code is 0 -- multi_agent_v1send_input is confirmed ack-only and deliberately excluded (AC-004)
ERR="${TMP}/send-input.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.' 'multi_agent_v1send_input')"
RC="$(run_validator_payload_with_tool "${PAYLOAD}" "${ERR}" "${ALIAS_TOOL}")"
assert_exit 0 "${RC}"

it "success-case - route directive hook wrapper forwards multi_agent_v1wait_agent to the widened validator"
# given: a multi_agent_v1wait_agent payload with a STOP directive and inline non-compliant response
# when: piped through route-directive-guard.sh (the real wrapper call site, not the validator directly)
# then: exit code is 2 -- proves the call-site update, not just the validator's own default
ERR="${TMP}/wrapper-magent.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.' 'multi_agent_v1wait_agent')"
set +e
AGENT_CREW_HOME="${HOME_DIR}/.agent-crew" printf '%s' "${PAYLOAD}" | AGENT_CREW_HOME="${HOME_DIR}/.agent-crew" bash "${WRAPPER}" 2>"${ERR}"
RC=$?
assert_exit 2 "${RC}"

it "boundary-case - validator does not crash and does not block when tool_name is entirely absent"
# given: a payload with the tool_name key entirely absent
# when: the validator is invoked with the new default --tool value
# then: exit code is 0 -- falls back to the empty-string default, no match, no crash
ERR="${TMP}/no-tool-name.err"
PAYLOAD="$(make_payload_no_tool_name '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.')"
RC="$(run_validator_payload "${PAYLOAD}" "${ERR}")"
assert_exit 0 "${RC}"

it "success-case - validator returns the same result across repeated runs of an identical payload"
# given: an identical non-compliant multi_agent_v1wait_agent STOP payload
# when: the validator is run twice in succession
# then: both runs produce exit code 2 and the same stderr violation message (stateless, no shared state to drift)
ERR1="${TMP}/idempotent-1.err"
ERR2="${TMP}/idempotent-2.err"
PAYLOAD="$(make_payload '[agent-crew] STOP — implementation request detected.' 'I inspected the code and here is the fix.' 'multi_agent_v1wait_agent')"
RC1="$(run_validator_payload_with_tool "${PAYLOAD}" "${ERR1}" "${ALIAS_TOOL}")"
RC2="$(run_validator_payload_with_tool "${PAYLOAD}" "${ERR2}" "${ALIAS_TOOL}")"
assert_exit 2 "${RC1}"
assert_exit 2 "${RC2}"
assert_eq "$(cat "${ERR1}")" "$(cat "${ERR2}")" "repeated runs should produce identical violation messages"

it "success-case - check-route-directive-compliance.py documents why spawn_agent and multi_agent_v1send_input remain unaliased"
# given: the exclusion decision for spawn_agent / multi_agent_v1send_input (AC-004)
# when: inspecting check-route-directive-compliance.py near the --tool alias definition
# then: an inline comment documents the exclusion rationale (presence check; exact wording unprescribed)
assert_contains "$(cat "${VALIDATOR}")" "spawn_agent" "AC-004 exclusion documented in validator"
assert_contains "$(cat "${VALIDATOR}")" "multi_agent_v1send_input" "AC-004 exclusion documented in validator"

it "success-case - post-tool-use-dispatcher.sh documents why spawn_agent and multi_agent_v1send_input remain unaliased"
assert_contains "$(cat "${HOOKS_DIR}/post-tool-use-dispatcher.sh")" "spawn_agent" "AC-004 exclusion documented in dispatcher"

it "success-case - check-route-directive-compliance.py documents the unconfirmed nested status shape as a residual limitation"
# given: extract_response() / _text_from_value()'s fixed top-level key list
# when: inspecting the code near those functions
# then: a comment documents that the nested status.<target_id> shape for multi_agent_v1wait_agent is unconfirmed/undetected (AC-005)
assert_contains "$(cat "${VALIDATOR}")" "target_id" "AC-005 residual limitation documented"

it "success-case - route-directive-guard.sh header comment reflects the widened multi_agent_v1wait_agent coverage"
assert_contains "$(sed -n '2p' "${WRAPPER}")" "multi_agent_v1wait_agent" "stale PostToolUse[Agent] header comment updated"

it "success-case - check-route-directive-compliance.py module docstring reflects the widened multi_agent_v1wait_agent coverage"
assert_contains "$(head -30 "${VALIDATOR}")" "multi_agent_v1wait_agent" "stale PostToolUse[Agent] docstring updated"

it "success-case - hook-system.md Route directive compliance bullet reflects the widened multi_agent_v1wait_agent coverage"
assert_contains "$(sed -n '26,36p' "${REPO_ROOT}/core/rules/capabilities/hook-system.md")" "multi_agent_v1wait_agent" "stale PostToolUse[Agent] doc bullet updated"

it "boundary-case - hook-system.md Forbid plain-text approval bullet remains unchanged by the route-directive doc update"
assert_contains "$(sed -n '18,25p' "${REPO_ROOT}/core/rules/capabilities/hook-system.md")" "PostToolUse[Agent]" "unrelated bullet must stay untouched"

end_report
