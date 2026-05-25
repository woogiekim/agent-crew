#!/usr/bin/env bash
# Tests for artifact-mutation routing in core/hooks/auto-route.sh
# Regression suite for GitHub issue #37.
#
# Acceptance criteria coverage:
#   AC1 — Korean reproduction prompt emits [agent-crew] STOP from auto-route.sh
#   AC2 — Codex skill metadata routes artifact/doc edits through crew:run
#   AC3 — apply_patch is covered by direct-edit-guard in Codex setup.sh
#   AC4 — Korean artifact-edit prompts with no explicit file extension are routed
#   AC5 — User should not need to type crew:run for NL artifact-edit requests

set -u  # do NOT set -e — failed assertions must keep running

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

HOOK="${HOOKS_DIR}/auto-route.sh"

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

# Build a UserPromptSubmit JSON payload.
make_prompt_payload() {
  local prompt="$1"
  python3 -c "
import json, sys
print(json.dumps({'prompt': sys.argv[1]}))
" "${prompt}"
}

# Run auto-route.sh with given prompt and return the additionalContext string.
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

# Run auto-route.sh and return its exit code.
run_hook_rc() {
  local payload="$1"
  printf '%s' "${payload}" | bash "${HOOK}" >/dev/null 2>&1
  echo $?
}

# --------------------------------------------------------------------------- #
# AC1 + AC4: Korean reproduction prompt from issue #37                        #
# --------------------------------------------------------------------------- #

it "AC1: Korean reproduction prompt emits [agent-crew] STOP"
PAYLOAD="$(make_prompt_payload '네 여기까지 내용 정리해서 클로드가 저장했던 파일에 수정해주세요')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "[agent-crew] STOP" "STOP directive present in additionalContext"

it "host bridge child processes disable auto-route directives"
PAYLOAD="$(make_prompt_payload '네 여기까지 내용 정리해서 클로드가 저장했던 파일에 수정해주세요')"
CTX="$(AGENT_CREW_HOST_BRIDGE_ACTIVE=1 run_hook_ctx "${PAYLOAD}")"
assert_eq "" "${CTX}"

it "AC1: Korean reproduction prompt identifies as 'project implementation'"
PAYLOAD="$(make_prompt_payload '네 여기까지 내용 정리해서 클로드가 저장했던 파일에 수정해주세요')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "project implementation" "detected type is project implementation"

it "AC4: Korean artifact verb 정리해서 + 파일 routes through STOP"
PAYLOAD="$(make_prompt_payload '내용 정리해서 파일에 저장해줘')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "[agent-crew] STOP" "정리해서 + 파일 triggers STOP"

it "AC4: Korean 이슈 초안에 반영해줘 routes through STOP (no file extension)"
PAYLOAD="$(make_prompt_payload '이슈 초안에 내용 반영해줘')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "[agent-crew] STOP" "이슈 초안 반영 triggers STOP"

it "AC4: Korean 문서 업데이트해줘 routes through STOP"
PAYLOAD="$(make_prompt_payload '문서 업데이트해줘')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "[agent-crew] STOP" "문서 업데이트 triggers STOP"

it "AC4: Korean 수정해줘 파일 routes through STOP"
PAYLOAD="$(make_prompt_payload '수정해줘 파일')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "[agent-crew] STOP" "수정해줘 파일 triggers STOP"

it "AC5: English 'update the saved file' routes through STOP"
PAYLOAD="$(make_prompt_payload 'update the saved file with this content')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "[agent-crew] STOP" "English artifact update triggers STOP"

it "AC5: English 'save this to the issue draft' routes through STOP"
PAYLOAD="$(make_prompt_payload 'save this to the issue draft')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "[agent-crew] STOP" "English save-to-draft triggers STOP"

it "issue publication requests route through issuer pipeline"
PAYLOAD="$(make_prompt_payload 'publish these issues to Plane')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "implementation request detected (issue publication)" "issue publication detected"
assert_contains "${CTX}" 'crew:run "issuer task"' "issuer pipeline suggested"

it "direct Plane MCP work item calls are blocked into crew:run issuer"
PAYLOAD="$(make_prompt_payload 'use mcp__plane__create_work_item to create these tasks')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "[agent-crew] STOP" "direct MCP work item call triggers STOP"
assert_contains "${CTX}" 'crew:run "issuer task"' "direct MCP call routes to issuer"

it "work item title updates route through issuer pipeline"
PAYLOAD="$(make_prompt_payload 'update the work item title for ENRTC-236')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "issue publication" "work item update detected"
assert_contains "${CTX}" 'crew:run "issuer task"' "work item update routes to issuer"

it "Korean issue publication request routes through issuer pipeline"
PAYLOAD="$(make_prompt_payload 'ENRTC-236 하위 작업 26건 이슈 발행해줘')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_contains "${CTX}" "issue publication" "Korean issue publication detected"
assert_contains "${CTX}" 'crew:run "issuer task"' "Korean request routes to issuer"

# --------------------------------------------------------------------------- #
# Negative cases: pure questions must NOT emit STOP                           #
# --------------------------------------------------------------------------- #

it "pure question 'what is in the file' must NOT emit STOP"
PAYLOAD="$(make_prompt_payload 'what is in the file')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_not_contains "${CTX}" "[agent-crew] STOP" "question does not trigger STOP"

it "pure question 'explain the doc structure' must NOT emit STOP"
PAYLOAD="$(make_prompt_payload 'explain the doc structure')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_not_contains "${CTX}" "[agent-crew] STOP" "explain does not trigger STOP"

it "pure Korean question 어떻게 작동하나요 must NOT emit STOP"
PAYLOAD="$(make_prompt_payload '파일이 어떻게 작동하나요')"
CTX="$(run_hook_ctx "${PAYLOAD}")"
assert_not_contains "${CTX}" "[agent-crew] STOP" "Korean question does not trigger STOP"

# --------------------------------------------------------------------------- #
# AC2: Codex SKILL.md covers artifact/doc edits                               #
# --------------------------------------------------------------------------- #

it "AC2: SKILL.md mentions artifact mutation routing"
SKILL_FILE="${REPO_ROOT}/adapters/codex/skill/agent-crew/SKILL.md"
assert_file_exists "${SKILL_FILE}"
SKILL_CONTENT=$(cat "${SKILL_FILE}")
assert_contains "${SKILL_CONTENT}" "artifact" "SKILL.md covers artifact edits"
assert_contains "${SKILL_CONTENT}" "apply_patch" "SKILL.md mentions apply_patch restriction"

it "AC2: SKILL.md lists Korean artifact verbs 정리, 저장, 발행, 고쳐, 업데이트"
SKILL_FILE="${REPO_ROOT}/adapters/codex/skill/agent-crew/SKILL.md"
SKILL_CONTENT=$(cat "${SKILL_FILE}")
assert_contains "${SKILL_CONTENT}" "정리" "정리 listed in SKILL.md"
assert_contains "${SKILL_CONTENT}" "저장" "저장 listed in SKILL.md"
assert_contains "${SKILL_CONTENT}" "발행" "발행 listed in SKILL.md"
assert_contains "${SKILL_CONTENT}" "고쳐" "고쳐 listed in SKILL.md"
assert_contains "${SKILL_CONTENT}" "업데이트" "업데이트 listed in SKILL.md"

# --------------------------------------------------------------------------- #
# AC3: Codex setup.sh includes apply_patch in direct-edit-guard matcher       #
# --------------------------------------------------------------------------- #

it "AC3: adapters/codex/setup.sh registers direct-edit-guard.sh for PreToolUse"
SETUP_FILE="${REPO_ROOT}/adapters/codex/setup.sh"
assert_file_exists "${SETUP_FILE}"
SETUP_CONTENT=$(cat "${SETUP_FILE}")
assert_contains "${SETUP_CONTENT}" "direct-edit-guard.sh" "setup.sh registers direct-edit-guard"

it "AC3: adapters/codex/setup.sh PreToolUse matcher includes apply_patch"
SETUP_FILE="${REPO_ROOT}/adapters/codex/setup.sh"
SETUP_CONTENT=$(cat "${SETUP_FILE}")
assert_contains "${SETUP_CONTENT}" "apply_patch" "setup.sh matcher includes apply_patch"

it "AC3: direct-edit-guard.sh itself handles apply_patch tool_name"
GUARD_FILE="${REPO_ROOT}/core/hooks/direct-edit-guard.sh"
GUARD_CONTENT=$(cat "${GUARD_FILE}")
assert_contains "${GUARD_CONTENT}" "apply_patch" "direct-edit-guard.sh handles apply_patch"

# --------------------------------------------------------------------------- #
# AC4: auto-route.sh ARTIFACT_VERB_PAT and ARTIFACT_NOUN_PAT are present      #
# --------------------------------------------------------------------------- #

it "AC4: auto-route.sh defines ARTIFACT_VERB_PAT"
HOOK_CONTENT=$(cat "${HOOK}")
assert_contains "${HOOK_CONTENT}" "ARTIFACT_VERB_PAT" "ARTIFACT_VERB_PAT defined in auto-route.sh"

it "AC4: auto-route.sh defines ARTIFACT_NOUN_PAT"
HOOK_CONTENT=$(cat "${HOOK}")
assert_contains "${HOOK_CONTENT}" "ARTIFACT_NOUN_PAT" "ARTIFACT_NOUN_PAT defined in auto-route.sh"

it "AC4: auto-route.sh ARTIFACT_VERB_PAT includes Korean verbs from issue #37"
HOOK_CONTENT=$(cat "${HOOK}")
assert_contains "${HOOK_CONTENT}" "정리" "정리 in ARTIFACT_VERB_PAT"
assert_contains "${HOOK_CONTENT}" "수정해" "수정해 in ARTIFACT_VERB_PAT"
assert_contains "${HOOK_CONTENT}" "반영해" "반영해 in ARTIFACT_VERB_PAT"
assert_contains "${HOOK_CONTENT}" "업데이트해" "업데이트해 in ARTIFACT_VERB_PAT"

# --------------------------------------------------------------------------- #
# Summary                                                                      #
# --------------------------------------------------------------------------- #

end_report
