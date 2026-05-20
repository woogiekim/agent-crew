#!/usr/bin/env bash
# E2E: native crew CLI state transition with fake-host completion.

set -u
source "$(dirname "$0")/../shell/_lib.bash"
set +e

CREW="${REPO_ROOT}/core/bin/crew"
TMP_HOME=$(make_tmp)
TMP_PROJECT=$(make_tmp)

it "fake-host crew run completes"
out=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" run --fake-host-result completed "fake host e2e" 2>&1)
rc=$?
assert_exit 0 "${rc}"

TASK_DIR=$(printf '%s\n' "${out}" | awk -F': ' '/^TASK_DIR:/ {print $2; exit}')

it "fake-host run writes handoff"
assert_file_exists "${TASK_DIR}/handoff.md"

it "fake-host run writes completed result"
result=$(cat "${TASK_DIR}/result.md")
assert_contains "${result}" "STATUS: completed"

it "fake-host status sees completed task"
status=$(AGENT_CREW_HOME="${TMP_HOME}" PROJECT_ROOT="${TMP_PROJECT}" bash "${CREW}" status --json 2>&1)
assert_contains "${status}" "\"status\": \"completed\""

it "fake-host status points at temp state dir"
assert_contains "${status}" "${TMP_HOME}/state/$(basename "${TMP_PROJECT}")"

it "fake-host state has no schema errors"
schema=$(AGENT_CREW_HOME="${TMP_HOME}" python3 "${REPO_ROOT}/core/scripts/validate-state-schema.py" \
  --state-dir "${TMP_HOME}/state/$(basename "${TMP_PROJECT}")" \
  --task-dir "${TASK_DIR}" \
  --format json 2>&1)
assert_contains "${schema}" '"errors": 0'

end_report
