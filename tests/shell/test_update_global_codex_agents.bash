#!/usr/bin/env bash
# Verify update-global-adapters refreshes and prunes ~/.codex/agents.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

TMP=$(make_tmp)
ACHOME="${TMP}/agent-crew-home"
CODEX_HOME="${TMP}/codex-home"
CLAUDE_DIR="${TMP}/claude-home"
mkdir -p "${ACHOME}/skills" "${ACHOME}/system/agents/skills" "${ACHOME}/setup" \
  "${ACHOME}/scripts" "${CODEX_HOME}/skills/agent-crew" "${CODEX_HOME}/agent-crew/skills" \
  "${CODEX_HOME}/agents"

cp "${SETUP_DIR}/setup-host.sh" "${ACHOME}/setup/setup-host.sh"
mkdir -p "${ACHOME}/adapters/generic"
cat > "${ACHOME}/adapters/generic/setup.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${ACHOME}/adapters/generic/setup.sh"

echo "stale" > "${CODEX_HOME}/agents/task-runner.toml"
echo "stale" > "${CODEX_HOME}/agent-crew/skills/stale.md"
echo "skill" > "${ACHOME}/skills/current.md"

it "update-global-adapters exits 0"
AGENT_CREW_HOME="${ACHOME}" \
CODEX_HOME="${CODEX_HOME}" \
CLAUDE_DIR="${CLAUDE_DIR}" \
SOURCE_ROOT="${REPO_ROOT}" \
  bash "${SCRIPTS_DIR}/update-global-adapters.sh" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}" "update-global-adapters"

it "global Codex agents include supervisor"
assert_file_exists "${CODEX_HOME}/agents/supervisor.toml"

it "global Codex agents include documenter"
assert_file_exists "${CODEX_HOME}/agents/documenter.toml"

it "global Codex agents prune task-runner"
assert_file_absent "${CODEX_HOME}/agents/task-runner.toml"

it "Codex crew skills mirror prunes stale skill"
assert_file_absent "${CODEX_HOME}/agent-crew/skills/stale.md"

it "Codex crew skills mirror copies unified current skill"
assert_file_exists "${CODEX_HOME}/agent-crew/skills/current.md"

end_report
