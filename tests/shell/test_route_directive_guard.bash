#!/usr/bin/env bash
# Regression coverage for issue #125: STOP/ROUTE soft directives need
# post-response validation when a host hook surface exists.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

VALIDATOR="${SCRIPTS_DIR}/check-route-directive-compliance.py"
WRAPPER="${HOOKS_DIR}/route-directive-guard.sh"

make_payload() {
  local directive="$1"
  local response="$2"
  python3 - "$directive" "$response" <<'PYEOF'
import json
import sys

print(json.dumps({
    "tool_name": "Agent",
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

it "route directive validator allows STOP responses with crew-run evidence"
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

it "route directive validator allows ROUTE responses with crew-agent evidence"
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

it "auto-route STOP directive carries a route lock"
CTX="$(run_auto_route_ctx "$(make_prompt_payload '수정해줘 파일')")"
assert_contains "${CTX}" "ROUTE_LOCK: crew-run" "STOP route lock"

it "auto-route ROUTE directive carries a route lock"
CTX="$(run_auto_route_ctx "$(make_prompt_payload '코덱스는 백그라운드 팬아웃이 되나요?')")"
assert_contains "${CTX}" "ROUTE_LOCK: crew-agent" "ROUTE route lock"

it "auto-route ROUTE directive removes inline-answer escape wording"
assert_not_contains "${CTX}" "ONLY permitted inline response" "ROUTE directive should not invite expanded inline exceptions"

it "global auto-execution rule requires agent-crew for substantive responses"
assert_contains "$(cat "${REPO_ROOT}/core/global-agents.md")" "Every substantive user-facing response must enter an agent-crew route" "global rule requires routing"
assert_contains "$(cat "${REPO_ROOT}/core/global-agents.md")" "Never use inline output as a shortcut" "global rule forbids inline bypass"

it "hook-system rule documents route directive compliance"
assert_contains "$(cat "${REPO_ROOT}/core/rules/capabilities/hook-system.md")" "Route directive compliance" "hook-system docs"

end_report
