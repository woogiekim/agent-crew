#!/usr/bin/env bash
# Tests for the Codex native host bridge wrapper.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

BRIDGE="${REPO_ROOT}/adapters/codex/bin/codex-host-bridge"
TMP_ROOT=$(make_tmp)
TASK_DIR="${TMP_ROOT}/task"
PROJECT_ROOT="${TMP_ROOT}/project"
FAKE_CODEX="${TMP_ROOT}/codex"
ARGV_PATH="${TMP_ROOT}/argv.txt"
STDIN_PATH="${TMP_ROOT}/stdin.txt"

mkdir -p "${TASK_DIR}" "${PROJECT_ROOT}"
printf 'handoff\n' > "${TMP_ROOT}/handoff.md"

cat > "${FAKE_CODEX}" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "${FAKE_CODEX_ARGV_PATH}"
cat > "${FAKE_CODEX_STDIN_PATH}"
exit 0
EOF
chmod +x "${FAKE_CODEX}"

it "codex host bridge passes approval policy as a top-level Codex option"
out=$(
  AGENT_CREW_CODEX_BIN="${FAKE_CODEX}" \
  FAKE_CODEX_ARGV_PATH="${ARGV_PATH}" \
  FAKE_CODEX_STDIN_PATH="${STDIN_PATH}" \
  AGENT_CREW_TASK_ID="task-1" \
  AGENT_CREW_TASK_DIR="${TASK_DIR}" \
  AGENT_CREW_HANDOFF_PATH="${TMP_ROOT}/handoff.md" \
  AGENT_CREW_RESULT_PATH="${TMP_ROOT}/result.md" \
  AGENT_CREW_PROJECT_ROOT="${PROJECT_ROOT}" \
  bash "${BRIDGE}" 2>&1
)
rc=$?
assert_exit 0 "${rc}"

argv=$(cat "${ARGV_PATH}")
first_arg=$(sed -n '1p' "${ARGV_PATH}")
second_arg=$(sed -n '2p' "${ARGV_PATH}")
third_arg=$(sed -n '3p' "${ARGV_PATH}")
assert_eq "--ask-for-approval" "${first_arg}"
assert_eq "never" "${second_arg}"
assert_eq "exec" "${third_arg}"
assert_not_contains "${argv}" $'exec\n-a'

it "codex host bridge still writes and pipes the resume prompt"
stdin_payload=$(cat "${STDIN_PATH}")
assert_contains "${stdin_payload}" "Resume this existing agent-crew crew:run handoff in Codex."
assert_contains "${stdin_payload}" "AGENT_CREW_TASK_ID: task-1"

end_report
