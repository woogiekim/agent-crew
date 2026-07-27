#!/usr/bin/env bash
# Verify Claude command discovery uses /crew:<intent>, not flat /<intent>.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

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
  "${ACHOME}/user/skills" \
  "${CLAUDE_DIR_T}/commands" \
  "${CLAUDE_DIR_T}/agent-crew" \
  "${PROJECT_ROOT_T}"

cp "${SETUP_DIR}/common.sh" "${ACHOME}/setup/common.sh"
cp "${REPO_ROOT}/core/commands/run.md" "${ACHOME}/commands/run.md"
cp "${REPO_ROOT}/core/commands/agent.md" "${ACHOME}/commands/agent.md"
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

it "claude setup does not install parity commands in crew namespace"
assert_file_absent "${CLAUDE_DIR_T}/commands/crew/parity-check.md"
assert_file_absent "${CLAUDE_DIR_T}/commands/crew/parity-implement.md"

it "claude setup prunes legacy flat run command"
assert_file_absent "${CLAUDE_DIR_T}/commands/run.md"

it "claude setup prunes legacy flat agent command"
assert_file_absent "${CLAUDE_DIR_T}/commands/agent.md"

end_report
