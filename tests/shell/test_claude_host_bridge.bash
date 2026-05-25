#!/usr/bin/env bash
# Tests for the Claude Code native host bridge wrapper.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

BRIDGE="${REPO_ROOT}/adapters/claude/bin/claude-host-bridge"
TMP_ROOT=$(make_tmp)
TASK_DIR="${TMP_ROOT}/task"
PROJECT_ROOT="${TMP_ROOT}/project"
FAKE_CLAUDE="${TMP_ROOT}/claude"
ARGV_PATH="${TMP_ROOT}/argv.txt"
CWD_PATH="${TMP_ROOT}/cwd.txt"
ACTIVE_PATH="${TMP_ROOT}/active.txt"

mkdir -p "${TASK_DIR}" "${PROJECT_ROOT}"
printf 'handoff\n' > "${TMP_ROOT}/handoff.md"

cat > "${FAKE_CLAUDE}" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "${FAKE_CLAUDE_ARGV_PATH}"
pwd > "${FAKE_CLAUDE_CWD_PATH}"
printf '%s\n' "${AGENT_CREW_HOST_BRIDGE_ACTIVE:-}" > "${FAKE_CLAUDE_ACTIVE_PATH}"
printf '{"type":"result","subtype":"success","result":"STATUS: completed"}\n'
exit 0
EOF
chmod +x "${FAKE_CLAUDE}"

it "claude host bridge invokes Claude with isolated low-context options"
out=$(
  AGENT_CREW_CLAUDE_BIN="${FAKE_CLAUDE}" \
  FAKE_CLAUDE_ARGV_PATH="${ARGV_PATH}" \
  FAKE_CLAUDE_CWD_PATH="${CWD_PATH}" \
  FAKE_CLAUDE_ACTIVE_PATH="${ACTIVE_PATH}" \
  AGENT_CREW_TASK_ID="task-1" \
  AGENT_CREW_TASK_DIR="${TASK_DIR}" \
  AGENT_CREW_HANDOFF_PATH="${TMP_ROOT}/handoff.md" \
  AGENT_CREW_RESULT_PATH="${TMP_ROOT}/result.md" \
  AGENT_CREW_PROJECT_ROOT="${PROJECT_ROOT}" \
  AGENT_CREW_CLAUDE_MAX_BUDGET_USD="0.25" \
  bash "${BRIDGE}" 2>&1
)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" '"STATUS: completed"'

argv=$(cat "${ARGV_PATH}")
assert_contains "${argv}" "--print"
assert_contains "${argv}" "--output-format"
assert_contains "${argv}" "--setting-sources"
assert_contains "${argv}" "user"
assert_contains "${argv}" "--disable-slash-commands"
assert_contains "${argv}" "--strict-mcp-config"
assert_contains "${argv}" "--mcp-config"
assert_contains "${argv}" '{"mcpServers":{}}'
assert_contains "${argv}" "--add-dir"
assert_contains "${argv}" "${PROJECT_ROOT}"
assert_contains "${argv}" "${TASK_DIR}"
assert_contains "${argv}" "--max-budget-usd"
assert_contains "${argv}" "0.25"
assert_contains "${argv}" "Resume this existing agent-crew crew:run handoff in Claude Code."
assert_contains "${argv}" "Do not invoke crew:run or any slash command."

it "claude host bridge runs outside the project cwd"
actual_cwd=$(cat "${CWD_PATH}")
if [ "${actual_cwd}" != "${PROJECT_ROOT}" ] && [ "${actual_cwd}" != "${REPO_ROOT}" ]; then
  _pass
else
  _fail "bridge cwd was not isolated: ${actual_cwd}"
fi

it "claude host bridge marks recursive invocation guard for child process"
assert_eq "1" "$(cat "${ACTIVE_PATH}")"

it "claude host bridge writes prompt and last message evidence"
assert_file_exists "${TASK_DIR}/context/claude-host-bridge-prompt.md"
assert_file_exists "${TASK_DIR}/context/claude-host-bridge-last-message.json"
assert_contains "$(cat "${TASK_DIR}/context/claude-host-bridge-prompt.md")" "AGENT_CREW_TASK_ID: task-1"

end_report
