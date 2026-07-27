#!/usr/bin/env bash
# Verify shipped user commands do not become system commands during install sync.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

TMP=$(make_tmp)
HOME_T="${TMP}/home"
ACHOME="${TMP}/agent-crew-home"
PROJECT_ROOT_T="${TMP}/project"
mkdir -p "${HOME_T}" "${PROJECT_ROOT_T}"

it "sync-local-install exits 0"
out=$(HOME="${HOME_T}" AGENT_CREW_HOME="${ACHOME}" CLAUDE_DIR="${HOME_T}/.claude" CODEX_HOME="${HOME_T}/.codex" \
  bash "${REPO_ROOT}/core/scripts/sync-local-install.sh" "${REPO_ROOT}" "${PROJECT_ROOT_T}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "parity commands install to user and discovery command paths"
assert_file_exists "${ACHOME}/user/commands/parity-check.md"
assert_file_exists "${ACHOME}/user/commands/parity-implement.md"
assert_file_exists "${ACHOME}/commands/parity-check.md"
assert_file_exists "${ACHOME}/commands/parity-implement.md"

it "parity commands are not installed as system commands"
assert_file_absent "${ACHOME}/system/commands/parity-check.md"
assert_file_absent "${ACHOME}/system/commands/parity-implement.md"

end_report
