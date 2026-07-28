#!/usr/bin/env bash
# Tests for explicit command-only behavior in core/hooks/auto-route.sh.

set -u  # do NOT set -e — failed assertions must keep running

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

HOOK="${HOOKS_DIR}/auto-route.sh"

make_prompt_payload() {
  local prompt="$1"
  python3 -c "
import json, sys
print(json.dumps({'prompt': sys.argv[1]}))
" "${prompt}"
}

run_hook_ctx() {
  local payload="$1"
  python3 -c "
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    sys.exit(0)
data = json.loads(raw)
ctx = data.get('hookSpecificOutput', {}).get('additionalContext', '')
print(ctx)
" < <(printf '%s' "${payload}" | bash "${HOOK}" 2>/dev/null)
}

it "natural-language artifact mutation emits no STOP or ROUTE directive"
PAYLOAD="$(make_prompt_payload '네 여기까지 내용 정리해서 클로드가 저장했던 파일에 수정해주세요')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_eq "" "${CTX}"

it "natural-language issue publication emits no STOP or ROUTE directive"
PAYLOAD="$(make_prompt_payload '이슈 초안에 반영해줘')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_eq "" "${CTX}"

it "explicit crew:run artifact mutation emits command context"
PAYLOAD="$(make_prompt_payload '$crew:run 네 여기까지 내용 정리해서 클로드가 저장했던 파일에 수정해주세요')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "[agent-crew] COMMAND" "explicit command directive present"
assert_contains "${CTX}" "commands/run.md" "run command selected"

it "host bridge child processes still disable auto-route directives"
PAYLOAD="$(make_prompt_payload '$crew:run 네 여기까지 내용 정리해서 클로드가 저장했던 파일에 수정해주세요')"
CTX="$(AGENT_CREW_HOST_BRIDGE_ACTIVE=1 run_hook_ctx "${PAYLOAD}")"
assert_eq "" "${CTX}"

it "Codex setup still covers apply_patch with direct-edit-guard"
assert_contains "$(cat "${REPO_ROOT}/adapters/codex/setup.sh")" "apply_patch" "apply_patch matcher is registered"
assert_contains "$(cat "${REPO_ROOT}/adapters/codex/setup.sh")" "direct-edit-guard.sh" "direct-edit-guard is registered"

end_report
