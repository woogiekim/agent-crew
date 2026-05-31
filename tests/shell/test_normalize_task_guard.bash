#!/usr/bin/env bash
# Tests for core/hooks/normalize-task-guard.sh
# Regression coverage for GitHub issue #130.
#
# Acceptance criteria coverage:
#   AC1 — Hangul in TASK: slot blocks (exit 2)
#   AC2 — Hangul in REQUIREMENTS: slot blocks (exit 2)
#   AC3 — English-only TASK: slot passes (exit 0)
#   AC4 — Korean inside input-normalizer agent prompt passes (exemption)
#   AC5 — Korean inside korean-normalizer agent prompt passes (exemption)
#   AC6 — AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK=1 escape hatch (exit 0)
#   AC7 — TASK: slot with paired NORMALIZED_TASK: provenance line passes (exit 0)
#   AC8 — Block reason references the canonical rule
#   AC9 — Hook is registered in adapters/claude/setup.sh
#   AC10 — Canonical rule files document the audit artifact contract
#   AC11 — Hook is composable: not registered for the same event/matcher as
#          route-directive-guard / direct-edit-guard (no clobber)

set -u  # do NOT set -e — failed assertions must keep running

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

HOOK="${HOOKS_DIR}/normalize-task-guard.sh"

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

# Build a PreToolUse JSON payload for an Agent / Task tool call carrying the
# given prompt body. The hook is matched on `Agent|Task` PreToolUse.
make_agent_payload() {
  local tool_name="$1"; shift
  local prompt="$1"
  python3 -c "
import json, sys
print(json.dumps({
    'tool_name': sys.argv[1],
    'tool_input': {
        'subagent_type': 'supervisor',
        'prompt': sys.argv[2],
    },
}))
" "${tool_name}" "${prompt}"
}

# Run the hook with given stdin JSON payload. Returns stdout+stderr combined.
run_hook() {
  local payload="$1"
  printf '%s' "${payload}" | bash "${HOOK}" 2>&1
}

# Run the hook and return its exit code.
run_hook_rc() {
  local payload="$1"
  printf '%s' "${payload}" | bash "${HOOK}" >/dev/null 2>&1
  echo $?
}

# Run the hook with a custom environment.
run_hook_env_rc() {
  local payload="$1"
  shift
  printf '%s' "${payload}" | env "$@" bash "${HOOK}" >/dev/null 2>&1
  echo $?
}

# --------------------------------------------------------------------------- #
# AC1 — Hangul in TASK: slot must block                                       #
# --------------------------------------------------------------------------- #

it "AC1: Hangul (U+AC00 block) in TASK: slot blocks (exit 2)"
PROMPT="$(printf 'TASK: 한국어 작업 설명입니다\nTASK_DIR: /tmp/x\nPROJECT_ROOT: /tmp/r')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "Hangul in TASK: must block"

it "AC1: Hangul Jamo (U+1100–U+11FF) in TASK: slot blocks (exit 2)"
PROMPT="$(printf 'TASK: \xe1\x84\x80\xe1\x85\xa1 sample\nTASK_DIR: /tmp/x')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "Hangul Jamo in TASK: must block"

it "AC1: Hangul Compatibility Jamo (U+3130–U+318F) in TASK: slot blocks (exit 2)"
PROMPT="$(printf 'TASK: \xe3\x84\xb1\xe3\x85\x8f sample\nTASK_DIR: /tmp/x')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "Hangul Compatibility Jamo in TASK: must block"

it "AC1: also blocks when tool_name is Task (not just Agent)"
PROMPT="$(printf 'TASK: 한국어\n')"
PAYLOAD="$(make_agent_payload Task "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "Task tool_name also matched"

# --------------------------------------------------------------------------- #
# AC2 — Hangul in REQUIREMENTS: slot must block                                #
# --------------------------------------------------------------------------- #

it "AC2: Hangul in REQUIREMENTS: slot blocks (exit 2)"
PROMPT="$(printf 'TASK: implement order API\nREQUIREMENTS: |\n  scope: 한국어 요구사항\n  target: api')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "Hangul in REQUIREMENTS: must block"

# --------------------------------------------------------------------------- #
# AC3 — English-only TASK passes                                              #
# --------------------------------------------------------------------------- #

it "AC3: English-only TASK: slot passes (exit 0)"
PROMPT="$(printf 'TASK: Implement order management API\nREQUIREMENTS: scope: backend\nTASK_DIR: /tmp/x')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 0 "${rc}" "ASCII-only must pass"

it "AC3: empty JSON input is allowed (exits 0)"
rc=$(run_hook_rc "{}")
assert_exit 0 "${rc}" "empty payload allowed"

it "AC3: non-Agent/Task tool_name is allowed (exits 0)"
PAYLOAD='{"tool_name":"Bash","tool_input":{"command":"echo 안녕"}}'
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 0 "${rc}" "Bash tool ignored regardless of content"

it "AC3: Agent payload with no prompt is allowed (exits 0)"
PAYLOAD='{"tool_name":"Agent","tool_input":{"subagent_type":"supervisor"}}'
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 0 "${rc}" "missing prompt is not a violation"

# --------------------------------------------------------------------------- #
# AC4/AC5 — Normalizer agents are exempt                                       #
# --------------------------------------------------------------------------- #

it "AC4: input-normalizer agent body with Korean passes (exit 0)"
PROMPT="$(printf 'You are running as input-normalizer.\nRAW_INPUT: 한국어 입력입니다\nSOURCE_LANGUAGE: ko')"
PAYLOAD="$(python3 -c "
import json, sys
print(json.dumps({
    'tool_name': 'Agent',
    'tool_input': {'subagent_type': 'input-normalizer', 'prompt': sys.argv[1]},
}))" "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 0 "${rc}" "input-normalizer must be exempt"

it "AC5: korean-normalizer agent body with Korean passes (exit 0)"
PROMPT="$(printf 'You are running as korean-normalizer.\nRAW_INPUT: 작업\n')"
PAYLOAD="$(python3 -c "
import json, sys
print(json.dumps({
    'tool_name': 'Agent',
    'tool_input': {'subagent_type': 'korean-normalizer', 'prompt': sys.argv[1]},
}))" "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 0 "${rc}" "korean-normalizer must be exempt"

it "AC4b: input-normalizer exemption is recognized via prompt body when subagent_type is absent"
PROMPT="$(printf 'You are acting as the input-normalizer agent.\nRAW_INPUT: 한국어 입력')"
PAYLOAD="$(python3 -c "
import json, sys
print(json.dumps({
    'tool_name': 'Agent',
    'tool_input': {'prompt': sys.argv[1]},
}))" "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 0 "${rc}" "input-normalizer marker in body also exempt"

# --------------------------------------------------------------------------- #
# AC6 — Escape hatch                                                           #
# --------------------------------------------------------------------------- #

it "AC6: AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK=1 allows raw Hangul (exit 0)"
PROMPT="$(printf 'TASK: 한국어 작업\n')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
rc=$(run_hook_env_rc "${PAYLOAD}" "AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK=1")
assert_exit 0 "${rc}" "escape hatch env var allows raw non-ASCII TASK"

it "AC6: AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK=0 does not bypass guard"
PROMPT="$(printf 'TASK: 한국어 작업\n')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
rc=$(run_hook_env_rc "${PAYLOAD}" "AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK=0")
assert_exit 2 "${rc}" "ALLOW=0 still blocks"

# --------------------------------------------------------------------------- #
# AC7 — Audit-artifact provenance pairing                                      #
# --------------------------------------------------------------------------- #

it "AC7: TASK: with paired NORMALIZED_TASK: line passes (exit 0)"
PROMPT="$(printf 'RAW_INPUT: 한국어 원본 작업\nNORMALIZED_TASK: Implement Korean input normalization for the order API.\nTASK: Implement Korean input normalization for the order API.\nTASK_DIR: /tmp/x')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 0 "${rc}" "audit provenance pair lets it through"

# --------------------------------------------------------------------------- #
# AC8 — Block reason actionable                                                #
# --------------------------------------------------------------------------- #

it "AC8: block reason references the canonical rule (korean-input.md or normalization-adapter.md)"
PROMPT="$(printf 'TASK: 한국어\n')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
out=$(run_hook "${PAYLOAD}")
assert_contains "${out}" "normaliz" "block message must reference normalization"

it "AC8: block reason names normalized_task.md audit artifact"
PROMPT="$(printf 'TASK: 한국어\n')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
out=$(run_hook "${PAYLOAD}")
assert_contains "${out}" "normalized_task.md" "block message must point at audit artifact"

it "AC8: block output contains decision/block JSON to stderr"
PROMPT="$(printf 'TASK: 한국어\n')"
PAYLOAD="$(make_agent_payload Agent "${PROMPT}")"
STDOUT_FILE="$(make_tmp)/stdout"
STDERR_FILE="$(make_tmp)/stderr"
printf '%s' "${PAYLOAD}" | bash "${HOOK}" >"${STDOUT_FILE}" 2>"${STDERR_FILE}"
rc=$?
assert_exit 2 "${rc}" "must exit 2"
assert_eq "" "$(cat "${STDOUT_FILE}")" "stdout must be empty on block"
assert_contains "$(cat "${STDERR_FILE}")" '"decision"' "stderr contains block JSON"
assert_contains "$(cat "${STDERR_FILE}")" '"block"' "stderr decision is block"

# --------------------------------------------------------------------------- #
# AC9 — Hook is registered in setup.sh                                         #
# --------------------------------------------------------------------------- #

it "AC9: normalize-task-guard.sh is registered in adapters/claude/setup.sh"
SETUP_CONTENT=$(cat "${REPO_ROOT}/adapters/claude/setup.sh")
assert_contains "${SETUP_CONTENT}" "normalize-task-guard.sh" "setup.sh registers the new guard"

it "AC9: registration matcher is Agent|Task and event is PreToolUse"
# The setup.sh python heredoc block for this hook should carry both tokens.
SETUP_CONTENT=$(cat "${REPO_ROOT}/adapters/claude/setup.sh")
# Look for any block that mentions both normalize-task-guard.sh and Agent|Task.
python3 - "${SETUP_CONTENT}" <<'PY' || _fail "registration block must use matcher Agent|Task and event PreToolUse"
import sys, re
content = sys.argv[1]
# Find the registration block boundaries
m = re.search(r"normalize-task-guard\.sh.{0,800}", content, re.DOTALL)
if not m:
    sys.exit(1)
block = m.group(0)
if "Agent|Task" in block and "PreToolUse" in block:
    sys.exit(0)
# Look backwards too
back = re.search(r".{0,800}normalize-task-guard\.sh", content, re.DOTALL)
if back and "Agent|Task" in back.group(0) and "PreToolUse" in back.group(0):
    sys.exit(0)
sys.exit(2)
PY
if [ $? -eq 0 ]; then _pass; fi

# --------------------------------------------------------------------------- #
# AC10 — Canonical rule files document the audit artifact contract             #
# --------------------------------------------------------------------------- #

it "AC10: core/rules/korean-input.md documents the normalized_task.md audit artifact"
KI_CONTENT=$(cat "${REPO_ROOT}/core/rules/korean-input.md")
assert_contains "${KI_CONTENT}" "normalized_task.md" "korean-input.md names the audit artifact"
assert_contains "${KI_CONTENT}" "RAW_INPUT" "korean-input.md documents RAW_INPUT field"

it "AC10: core/rules/normalization-adapter.md documents the audit artifact contract"
NA_CONTENT=$(cat "${REPO_ROOT}/core/rules/normalization-adapter.md")
assert_contains "${NA_CONTENT}" "normalized_task.md" "normalization-adapter.md names the audit artifact"
assert_contains "${NA_CONTENT}" "Audit Artifact" "normalization-adapter.md has the Audit Artifact section"

it "AC10: core/commands/run.md Step 1 references the audit artifact"
RUN_CONTENT=$(cat "${REPO_ROOT}/core/commands/run.md")
assert_contains "${RUN_CONTENT}" "normalized_task.md" "run.md Step 1 requires the audit artifact"

it "AC10: core/commands/agent.md Step 5 references the audit artifact"
AGENT_CONTENT=$(cat "${REPO_ROOT}/core/commands/agent.md")
assert_contains "${AGENT_CONTENT}" "normalized_task.md" "agent.md Step 5 requires the audit artifact"

# --------------------------------------------------------------------------- #
# AC11 — Composability with existing PreToolUse guards                         #
# --------------------------------------------------------------------------- #

it "AC11: new hook does not collide with route-directive-guard (different matcher/event)"
SETUP_CONTENT=$(cat "${REPO_ROOT}/adapters/claude/setup.sh")
# route-directive-guard runs on PostToolUse for Agent. The new guard runs on
# PreToolUse for Agent|Task. They live in different blocks.
assert_contains "${SETUP_CONTENT}" "route-directive-guard.sh" "route-directive-guard still registered"

it "AC11: new hook does not collide with direct-edit-guard (different matcher)"
SETUP_CONTENT=$(cat "${REPO_ROOT}/adapters/claude/setup.sh")
# direct-edit-guard runs on PreToolUse for Edit|Write. Different matcher.
assert_contains "${SETUP_CONTENT}" "direct-edit-guard.sh" "direct-edit-guard still registered"

# --------------------------------------------------------------------------- #
# Summary                                                                     #
# --------------------------------------------------------------------------- #

end_report
