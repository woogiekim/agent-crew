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
STATE_DIR="${TMP_ROOT}/state"
FAKE_CODEX="${TMP_ROOT}/codex"
ARGV_PATH="${TMP_ROOT}/argv.txt"
STDIN_PATH="${TMP_ROOT}/stdin.txt"
ENV_PATH="${TMP_ROOT}/env.txt"

mkdir -p "${TASK_DIR}" "${PROJECT_ROOT}" "${STATE_DIR}/tasks"
printf 'handoff\n' > "${TMP_ROOT}/handoff.md"

cat > "${FAKE_CODEX}" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "${FAKE_CODEX_ARGV_PATH}"
{
  printf 'ACTIVE:%s\n' "${AGENT_CREW_HOST_BRIDGE_ACTIVE:-}"
  printf 'AUTO_ROUTE_DISABLED:%s\n' "${AGENT_CREW_AUTO_ROUTE_DISABLED:-}"
} > "${FAKE_CODEX_ENV_PATH}"
cat > "${FAKE_CODEX_STDIN_PATH}"
printf 'tokens used\n28,904\n'
exit 0
EOF
chmod +x "${FAKE_CODEX}"

it "codex host bridge passes approval policy as a top-level Codex option"
out=$(
  AGENT_CREW_CODEX_BIN="${FAKE_CODEX}" \
  AGENT_CREW_CODEX_ALLOW_NESTED=1 \
  FAKE_CODEX_ARGV_PATH="${ARGV_PATH}" \
  FAKE_CODEX_STDIN_PATH="${STDIN_PATH}" \
  FAKE_CODEX_ENV_PATH="${ENV_PATH}" \
  AGENT_CREW_TASK_ID="task-1" \
  AGENT_CREW_TASK_DIR="${TASK_DIR}" \
  AGENT_CREW_STATE_DIR="${STATE_DIR}" \
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
sixth_arg=$(sed -n '6p' "${ARGV_PATH}")
seventh_arg=$(sed -n '7p' "${ARGV_PATH}")
assert_eq "--ask-for-approval" "${first_arg}"
assert_eq "never" "${second_arg}"
assert_eq "exec" "${third_arg}"
assert_eq "--add-dir" "${sixth_arg}"
assert_eq "${TASK_DIR}" "${seventh_arg}"
assert_not_contains "${argv}" $'exec\n-a'
assert_contains "$(cat "${ENV_PATH}")" "ACTIVE:1"
assert_contains "$(cat "${ENV_PATH}")" "AUTO_ROUTE_DISABLED:1"

it "codex host bridge records measured token usage from CLI output"
assert_contains "${out}" "tokens used"
cost_payload="$(cat "${STATE_DIR}/cost/task-1.jsonl")"
assert_contains "${cost_payload}" '"provider":"codex"'
assert_contains "${cost_payload}" '"total_tokens":28904'

it "codex host bridge still writes and pipes the resume prompt"
stdin_payload=$(cat "${STDIN_PATH}")
assert_contains "${stdin_payload}" "Resume this existing agent-crew crew:run handoff in Codex."
assert_contains "${stdin_payload}" "AGENT_CREW_TASK_ID: task-1"

it "codex host bridge narrows crew-run normalization prompts"
NORMALIZATION_TASK_DIR="${TMP_ROOT}/normalization-task"
NORMALIZATION_HANDOFF="${TMP_ROOT}/normalization-handoff.md"
mkdir -p "${NORMALIZATION_TASK_DIR}"
cat > "${NORMALIZATION_HANDOFF}" <<'EOF'
# Input Normalization Handoff

NORMALIZATION_GATE: required
RAW_TASK: 진행해주세요
OUTPUT_CONTRACT: Return JSON with source_language and normalized_task.
EOF
out=$(
  AGENT_CREW_CODEX_BIN="${FAKE_CODEX}" \
  AGENT_CREW_CODEX_ALLOW_NESTED=1 \
  FAKE_CODEX_ARGV_PATH="${ARGV_PATH}" \
  FAKE_CODEX_STDIN_PATH="${STDIN_PATH}" \
  FAKE_CODEX_ENV_PATH="${ENV_PATH}" \
  AGENT_CREW_TASK_ID="normalization-task-1" \
  AGENT_CREW_TASK_DIR="${NORMALIZATION_TASK_DIR}" \
  AGENT_CREW_STATE_DIR="${STATE_DIR}" \
  AGENT_CREW_HANDOFF_PATH="${NORMALIZATION_HANDOFF}" \
  AGENT_CREW_RESULT_PATH="${TMP_ROOT}/normalization-result.md" \
  AGENT_CREW_PROJECT_ROOT="${PROJECT_ROOT}" \
  bash "${BRIDGE}" 2>&1
)
rc=$?
assert_exit 0 "${rc}"
stdin_payload=$(cat "${STDIN_PATH}")
assert_contains "${stdin_payload}" "Complete only the input-normalizer contract"
assert_contains "${stdin_payload}" "Do not continue to supervisor"
assert_not_contains "${stdin_payload}" "installed agent-crew supervisor workflow"

it "codex direct-agent bridge forbids normalizer subagent spawn"
out=$(
  AGENT_CREW_CODEX_BIN="${FAKE_CODEX}" \
  AGENT_CREW_CODEX_ALLOW_NESTED=1 \
  FAKE_CODEX_ARGV_PATH="${ARGV_PATH}" \
  FAKE_CODEX_STDIN_PATH="${STDIN_PATH}" \
  FAKE_CODEX_ENV_PATH="${ENV_PATH}" \
  AGENT_CREW_TASK_ID="agent-task-1" \
  AGENT_CREW_TASK_DIR="${TASK_DIR}" \
  AGENT_CREW_STATE_DIR="${STATE_DIR}" \
  AGENT_CREW_HANDOFF_PATH="${TMP_ROOT}/handoff.md" \
  AGENT_CREW_RESULT_PATH="${TMP_ROOT}/result.md" \
  AGENT_CREW_PROJECT_ROOT="${PROJECT_ROOT}" \
  AGENT_CREW_AGENT_REQUEST_ID="agent-request-1" \
  AGENT_CREW_AGENT_NAME="analyst" \
  bash "${BRIDGE}" 2>&1
)
rc=$?
assert_exit 0 "${rc}"
stdin_payload=$(cat "${STDIN_PATH}")
argv=$(cat "${ARGV_PATH}")
assert_contains "${argv}" "--sandbox"
assert_contains "${argv}" "read-only"
assert_contains "${argv}" "-C"
assert_contains "${argv}" "${TASK_DIR}"
assert_contains "${argv}" "--skip-git-repo-check"
assert_not_contains "${argv}" "--add-dir"
assert_not_contains "${argv}" "${PROJECT_ROOT}"
assert_contains "${stdin_payload}" "Resume this existing agent-crew direct-agent handoff in Codex."
assert_contains "${stdin_payload}" "perform the input-normalizer contract inline"
assert_contains "${stdin_payload}" "Do not spawn input-normalizer"
assert_contains "${stdin_payload}" "Direct-agent bridges run with a read-only project sandbox."
assert_contains "${stdin_payload}" "AGENT_CREW_AGENT_NAME: analyst"

it "codex host bridge fails fast for nested Codex sessions"
NESTED_DIR="${TMP_ROOT}/nested"
mkdir -p "${NESTED_DIR}"
NESTED_CODEX="${NESTED_DIR}/codex"
cat > "${NESTED_CODEX}" <<EOF
#!/usr/bin/env bash
AGENT_CREW_CODEX_BIN="${FAKE_CODEX}" \
FAKE_CODEX_ARGV_PATH="${ARGV_PATH}" \
FAKE_CODEX_STDIN_PATH="${STDIN_PATH}" \
FAKE_CODEX_ENV_PATH="${ENV_PATH}" \
AGENT_CREW_TASK_ID="nested-task-1" \
AGENT_CREW_TASK_DIR="${TASK_DIR}" \
AGENT_CREW_HANDOFF_PATH="${TMP_ROOT}/handoff.md" \
AGENT_CREW_RESULT_PATH="${TMP_ROOT}/result.md" \
AGENT_CREW_PROJECT_ROOT="${PROJECT_ROOT}" \
  bash "${BRIDGE}"
EOF
chmod +x "${NESTED_CODEX}"
out=$("${NESTED_CODEX}" 2>&1)
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "refusing nested Codex exec"
assert_contains "${out}" "AGENT_CREW_CODEX_ALLOW_NESTED=1"

end_report
