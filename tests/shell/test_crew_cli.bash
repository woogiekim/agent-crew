#!/usr/bin/env bash
# Tests for the native core/bin/crew shell entrypoint.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

CREW="${REPO_ROOT}/core/bin/crew"

it "crew help exits 0"
out=$(bash "${CREW}" --help 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew help mentions setup/status/update"
assert_contains "${out}" "setup [PROJECT_ROOT]"

it "crew help states prompt-workflow control plane"
assert_contains "${out}" "local control plane for AI-host prompt workflows"

TMP_HOME=$(make_tmp)
TMP_PROJECT=$(make_tmp)
mkdir -p "${TMP_HOME}/state/$(basename "${TMP_PROJECT}")/tasks"

it "crew status exits 0 with empty task directory"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" status 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew status prints project state path"
assert_contains "${out}" "State  : ${TMP_HOME}/state/$(basename "${TMP_PROJECT}")"

it "crew status --json exits 0"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" status --json 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew status --json contains tasks key"
assert_contains "${out}" "\"tasks\""

it "crew run writes deterministic state then exits blocked"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run "demo task" 2>&1)
rc=$?
assert_exit 3 "${rc}"

it "crew run output includes task directory"
assert_contains "${out}" "TASK_DIR:"

TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')

it "crew run writes register.json"
assert_file_exists "${TASK_DIR}/register.json"

it "crew run writes supervisor handoff"
assert_file_exists "${TASK_DIR}/handoff.md"

it "crew run writes blocked result"
result=$(cat "${TASK_DIR}/result.md")
assert_contains "${result}" "STATUS: blocked"

it "crew run fake host can complete"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run --fake-host-result completed "fake host task" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew run fake host output is completed"
assert_contains "${out}" "STATUS: completed"

it "crew agent fails fast with guided prompt mode message"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" agent analyst "what changed?" 2>&1)
rc=$?
assert_exit 2 "${rc}"

it "crew agent failure is explicit"
assert_contains "${out}" "native crew agent dispatch is not implemented yet"

it "crew update --help exits 0"
out=$(bash "${CREW}" update --help 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "crew update --help documents local mode"
assert_contains "${out}" "crew update [--local [SOURCE_ROOT]]"

it "crew update --help documents remote default"
assert_contains "${out}" "clones origin/main into a fresh temporary checkout"

end_report
