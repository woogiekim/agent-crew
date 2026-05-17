#!/usr/bin/env bash
# Tests for core/hooks/direct-edit-guard.sh
# Regression suite for GitHub issue #17.
#
# Acceptance criteria coverage:
#   AC1 — root cause documented (see core/rules/direct-edit-guard.md)
#   AC2 — hook blocks (exit 2) when main session edits code files and no active task
#   AC3 — escape hatch documented and functional
#   AC4 — regression test for the 2026-05-17 call pattern
#   AC5 — sub-agent edits (via active marker) must still pass

set -u  # do NOT set -e — failed assertions must keep running

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

HOOK="${HOOKS_DIR}/direct-edit-guard.sh"

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

# Build a PreToolUse JSON payload for an Edit call to a given file path.
make_edit_payload() {
  local file_path="$1"
  python3 -c "
import json, sys
print(json.dumps({
    'tool_name': 'Edit',
    'tool_input': {
        'file_path': sys.argv[1],
        'old_string': 'foo',
        'new_string': 'bar',
    }
}))
" "${file_path}"
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
run_hook_env() {
  local payload="$1"
  shift
  # Remaining args are VAR=value pairs forwarded to env(1).
  printf '%s' "${payload}" | env "$@" bash "${HOOK}" 2>&1
}

run_hook_env_rc() {
  local payload="$1"
  shift
  printf '%s' "${payload}" | env "$@" bash "${HOOK}" >/dev/null 2>&1
  echo $?
}

# --------------------------------------------------------------------------- #
# Test fixtures                                                                #
# --------------------------------------------------------------------------- #

# Use a temp directory as a fake project root so the git check is skipped by
# the hook (the hook runs git rev-parse; a non-git path will exit 0 — allow).
# To simulate a blocked edit we need an actual git repo path. Use REPO_ROOT.
PROJECT_CORE_FILE="${REPO_ROOT}/core/hooks/direct-edit-guard.sh"
FAKE_AGENT_CREW_HOME="$(make_tmp)"
FAKE_PROJECT_NAME="$(basename "${REPO_ROOT}")"
FAKE_TASKS_DIR="${FAKE_AGENT_CREW_HOME}/state/${FAKE_PROJECT_NAME}/tasks"
mkdir -p "${FAKE_TASKS_DIR}"

# --------------------------------------------------------------------------- #
# AC2 + AC4: 2026-05-17 incident pattern — no active marker, must block       #
# --------------------------------------------------------------------------- #

it "AC4/AC2: Edit to core/ with no active marker exits 2 (blocks)"
PAYLOAD="$(make_edit_payload "${PROJECT_CORE_FILE}")"
rc=$(run_hook_env_rc "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=")
assert_exit 2 "${rc}" "exit 2 when no active marker"

it "AC4/AC2: block output contains 'decision: block' JSON"
PAYLOAD="$(make_edit_payload "${PROJECT_CORE_FILE}")"
out=$(run_hook_env "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=")
assert_contains "${out}" '"decision"' "block JSON present"
assert_contains "${out}" '"block"' "decision is block"

it "AC4/AC2: block message mentions crew:run"
PAYLOAD="$(make_edit_payload "${PROJECT_CORE_FILE}")"
out=$(run_hook_env "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=")
assert_contains "${out}" "crew:run" "block message mentions crew:run"

# --------------------------------------------------------------------------- #
# AC5: Active task marker allows the edit (sub-agent / pipeline path)         #
# --------------------------------------------------------------------------- #

it "AC5: legacy active marker (tasks/active) allows Edit — exits 0"
touch "${FAKE_TASKS_DIR}/active"
PAYLOAD="$(make_edit_payload "${PROJECT_CORE_FILE}")"
rc=$(run_hook_env_rc "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=")
assert_exit 0 "${rc}" "active marker allows edit"
rm -f "${FAKE_TASKS_DIR}/active"

it "AC5: per-task active marker (tasks/active.TASK_ID) allows Edit — exits 0"
touch "${FAKE_TASKS_DIR}/active.20260517-170632-0"
PAYLOAD="$(make_edit_payload "${PROJECT_CORE_FILE}")"
rc=$(run_hook_env_rc "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=")
assert_exit 0 "${rc}" "per-task marker allows edit"
rm -f "${FAKE_TASKS_DIR}/active.20260517-170632-0"

# --------------------------------------------------------------------------- #
# AC3: Escape hatch — AGENT_CREW_ALLOW_DIRECT_EDIT=1                         #
# --------------------------------------------------------------------------- #

it "AC3: AGENT_CREW_ALLOW_DIRECT_EDIT=1 allows Edit — exits 0"
PAYLOAD="$(make_edit_payload "${PROJECT_CORE_FILE}")"
rc=$(run_hook_env_rc "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=1")
assert_exit 0 "${rc}" "escape hatch env var allows edit"

it "AC3: AGENT_CREW_ALLOW_DIRECT_EDIT=0 does not bypass guard"
PAYLOAD="$(make_edit_payload "${PROJECT_CORE_FILE}")"
rc=$(run_hook_env_rc "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=0")
assert_exit 2 "${rc}" "ALLOW_DIRECT_EDIT=0 still blocks"

# --------------------------------------------------------------------------- #
# Graceful degradation — non-project files must not be blocked                #
# --------------------------------------------------------------------------- #

it "non-repo file_path is allowed (exits 0)"
TMP_FILE="$(make_tmp)/outside_repo.sh"
touch "${TMP_FILE}"
PAYLOAD="$(make_edit_payload "${TMP_FILE}")"
rc=$(run_hook_env_rc "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=")
assert_exit 0 "${rc}" "non-repo file allowed"

it "empty JSON input is allowed (exits 0)"
rc=$(run_hook_rc "{}")
assert_exit 0 "${rc}" "empty payload allowed"

it "non-Edit tool_name is allowed (exits 0)"
PAYLOAD='{"tool_name":"Bash","tool_input":{"command":"echo hi"}}'
rc=$(run_hook_rc "${PAYLOAD}")
assert_exit 0 "${rc}" "Bash tool allowed"

it "Write tool_name with no active marker blocks (exits 2)"
PAYLOAD="$(python3 -c "
import json, sys
print(json.dumps({
    'tool_name': 'Write',
    'tool_input': {
        'file_path': '${PROJECT_CORE_FILE}',
        'content': 'new content',
    }
}))
")"
rc=$(run_hook_env_rc "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=")
assert_exit 2 "${rc}" "Write tool also blocked"

# --------------------------------------------------------------------------- #
# Path-prefix allow-list (agent-crew state, ~/.claude)                        #
# --------------------------------------------------------------------------- #

it "edits to ~/.agent-crew/ are always allowed (exits 0)"
TARGET="${FAKE_AGENT_CREW_HOME}/some/config.json"
mkdir -p "$(dirname "${TARGET}")"
touch "${TARGET}"
PAYLOAD="$(make_edit_payload "${TARGET}")"
rc=$(run_hook_env_rc "${PAYLOAD}" \
  "AGENT_CREW_HOME=${FAKE_AGENT_CREW_HOME}" \
  "AGENT_CREW_ALLOW_DIRECT_EDIT=")
assert_exit 0 "${rc}" "agent-crew-home path allowed"

# --------------------------------------------------------------------------- #
# AC3: Escape hatch documented in core/rules/direct-edit-guard.md             #
# --------------------------------------------------------------------------- #

it "AC3: core/rules/direct-edit-guard.md exists and documents escape hatch"
RULE_FILE="${REPO_ROOT}/core/rules/direct-edit-guard.md"
assert_file_exists "${RULE_FILE}"
RULE_CONTENT=$(cat "${RULE_FILE}")
assert_contains "${RULE_CONTENT}" "AGENT_CREW_ALLOW_DIRECT_EDIT" "escape hatch env var documented"
assert_contains "${RULE_CONTENT}" "Escape hatch" "escape hatch section present"

# --------------------------------------------------------------------------- #
# Hook is registered in setup.sh / install.sh                                 #
# --------------------------------------------------------------------------- #

it "direct-edit-guard.sh is registered in adapters/claude/setup.sh"
SETUP_CONTENT=$(cat "${REPO_ROOT}/adapters/claude/setup.sh")
assert_contains "${SETUP_CONTENT}" "direct-edit-guard.sh" "setup.sh registers guard"

it "direct-edit-guard.sh is registered in install.sh (claude compat layer)"
INSTALL_CONTENT=$(cat "${REPO_ROOT}/install.sh")
assert_contains "${INSTALL_CONTENT}" "direct-edit-guard.sh" "install.sh registers guard"

# --------------------------------------------------------------------------- #
# Summary                                                                     #
# --------------------------------------------------------------------------- #

end_report
