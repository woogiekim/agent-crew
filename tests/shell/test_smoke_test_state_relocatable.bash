#!/usr/bin/env bash
# Verify smoke-test-state.sh resolves the source checkout when installed under
# ~/.agent-crew/scripts and launched from another project.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

TMP=$(make_tmp)
FAKE_HOME="${TMP}/agent-crew-home"
FAKE_PROJECT="${TMP}/project"
mkdir -p "${FAKE_HOME}/scripts" "${FAKE_PROJECT}"
cp "${SCRIPTS_DIR}/smoke-test-state.sh" "${FAKE_HOME}/scripts/smoke-test-state.sh"

it "installed smoke-test-state.sh exits 0 outside source checkout"
(
  cd "${FAKE_PROJECT}" || exit 1
  AGENT_CREW_HOME="${FAKE_HOME}" AGENT_CREW_SOURCE_DIR="${REPO_ROOT}" bash "${FAKE_HOME}/scripts/smoke-test-state.sh" >/dev/null 2>&1
)
rc=$?
assert_exit 0 "${rc}" "installed smoke test"

end_report
