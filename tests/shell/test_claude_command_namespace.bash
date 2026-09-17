#!/usr/bin/env bash
# Verify Claude command discovery uses /crew:<intent>, not flat /<intent>.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

project_state_dir() {
  python3 "${REPO_ROOT}/core/scripts/project_state.py" resolve \
    --agent-crew-home "$1" \
    --project-root "$2" \
    --prefer-existing-legacy \
    --format json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["state_dir"])'
}

TMP=$(make_tmp)
ACHOME="${TMP}/agent-crew-home"
CLAUDE_DIR_T="${TMP}/claude-home"
PROJECT_ROOT_T="${TMP}/project"
mkdir -p \
  "${ACHOME}/commands" \
  "${ACHOME}/hooks" \
  "${ACHOME}/rules" \
  "${ACHOME}/scripts" \
  "${ACHOME}/setup" \
  "${ACHOME}/adapters/claude/bin" \
  "${ACHOME}/system/agents" \
  "${ACHOME}/system/skills" \
  "${ACHOME}/user/agents" \
  "${ACHOME}/user/commands" \
  "${ACHOME}/user/skills" \
  "${CLAUDE_DIR_T}/commands" \
  "${CLAUDE_DIR_T}/agent-crew" \
  "${PROJECT_ROOT_T}"

cp "${SETUP_DIR}/common.sh" "${ACHOME}/setup/common.sh"
cp "${REPO_ROOT}/core/commands/run.md" "${ACHOME}/commands/run.md"
cp "${REPO_ROOT}/core/commands/agent.md" "${ACHOME}/commands/agent.md"
printf '# /stager\n\nuser-owned command\n' > "${ACHOME}/user/commands/stager.md"
printf '# /post-audit\n\nuser-owned command\n' > "${ACHOME}/user/commands/post-audit.md"
printf 'legacy flat run\n' > "${CLAUDE_DIR_T}/commands/run.md"
printf 'legacy flat agent\n' > "${CLAUDE_DIR_T}/commands/agent.md"

it "claude setup exits 0"
AGENT_CREW_HOME="${ACHOME}" \
CLAUDE_DIR="${CLAUDE_DIR_T}" \
SOURCE_ROOT="${REPO_ROOT}" \
AGENT_CREW_MODE=update \
AGENT_CREW_WRITE_CAPABILITIES=0 \
  bash "${REPO_ROOT}/adapters/claude/setup.sh" "${PROJECT_ROOT_T}" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}" "claude setup"

it "claude setup installs crew namespace slash commands"
assert_file_exists "${CLAUDE_DIR_T}/commands/crew/run.md"

it "claude setup installs direct-agent command in crew namespace"
assert_file_exists "${CLAUDE_DIR_T}/commands/crew/agent.md"

it "claude setup installs parity-check as a flat user command"
assert_file_exists "${CLAUDE_DIR_T}/commands/parity-check.md"

it "claude setup installs parity-implement as a flat user command"
assert_file_exists "${CLAUDE_DIR_T}/commands/parity-implement.md"

it "claude setup installs installed user commands as flat user commands"
assert_file_exists "${CLAUDE_DIR_T}/commands/stager.md"
assert_file_exists "${CLAUDE_DIR_T}/commands/post-audit.md"

it "claude setup does not install parity commands in crew namespace"
assert_file_absent "${CLAUDE_DIR_T}/commands/crew/parity-check.md"
assert_file_absent "${CLAUDE_DIR_T}/commands/crew/parity-implement.md"

it "claude setup prunes legacy flat run command"
assert_file_absent "${CLAUDE_DIR_T}/commands/run.md"

it "claude setup prunes legacy flat agent command"
assert_file_absent "${CLAUDE_DIR_T}/commands/agent.md"

TMP_CAPS=$(make_tmp)
ACHOME_CAPS="${TMP_CAPS}/agent-crew-home"
CLAUDE_DIR_CAPS="${TMP_CAPS}/claude-home"
PROJECT_ROOT_CAPS="${TMP_CAPS}/project"
mkdir -p \
  "${ACHOME_CAPS}/commands" \
  "${ACHOME_CAPS}/hooks" \
  "${ACHOME_CAPS}/rules" \
  "${ACHOME_CAPS}/scripts" \
  "${ACHOME_CAPS}/setup" \
  "${ACHOME_CAPS}/adapters/claude/bin" \
  "${ACHOME_CAPS}/system/agents" \
  "${ACHOME_CAPS}/system/skills" \
  "${ACHOME_CAPS}/user/agents" \
  "${ACHOME_CAPS}/user/commands" \
  "${ACHOME_CAPS}/user/skills" \
  "${CLAUDE_DIR_CAPS}/commands" \
  "${CLAUDE_DIR_CAPS}/agent-crew" \
  "${PROJECT_ROOT_CAPS}"

cp "${SETUP_DIR}/common.sh" "${ACHOME_CAPS}/setup/common.sh"
cp "${REPO_ROOT}/core/commands/run.md" "${ACHOME_CAPS}/commands/run.md"
cp "${REPO_ROOT}/core/commands/agent.md" "${ACHOME_CAPS}/commands/agent.md"

it "claude setup with capabilities exits 0"
AGENT_CREW_HOME="${ACHOME_CAPS}" \
CLAUDE_DIR="${CLAUDE_DIR_CAPS}" \
SOURCE_ROOT="${REPO_ROOT}" \
AGENT_CREW_MODE=update \
  bash "${REPO_ROOT}/adapters/claude/setup.sh" "${PROJECT_ROOT_CAPS}" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}" "claude setup with capabilities"

it "claude setup exposes Claude system review as host-native lens"
CLAUDE_STATE="$(project_state_dir "${ACHOME_CAPS}" "${PROJECT_ROOT_CAPS}")"
assert_file_exists "${CLAUDE_STATE}/review-lenses.json"
assert_contains "$(cat "${CLAUDE_STATE}/review-lenses.json")" '"lens_id": "claude-system-review"'
assert_contains "$(cat "${CLAUDE_STATE}/review-lenses.json")" '"provider": "claude"'
assert_contains "$(cat "${CLAUDE_STATE}/review-lenses.json")" '"surface": "host-native"'
assert_contains "$(cat "${CLAUDE_STATE}/review-lenses.json")" '"read_only": true'
assert_contains "$(cat "${CLAUDE_STATE}/review-lenses.json")" '"mutates": false'
assert_contains "$(cat "${CLAUDE_STATE}/review-lenses.json")" '"path": "'"${CLAUDE_DIR_CAPS}"'/commands/review-synthesis.md"'
assert_contains "$(cat "${CLAUDE_STATE}/review-lenses.json")" '"runner": "claude-current-session-review"'
assert_contains "$(cat "${CLAUDE_STATE}/review-lenses.json")" '"result_source_label": "source_lens=claude-system-review"'

end_report
