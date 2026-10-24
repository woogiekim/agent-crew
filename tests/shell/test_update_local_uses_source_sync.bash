#!/usr/bin/env bash
# `crew update --local` must run the SOURCE tree's installer, not the copy that
# is already installed.
#
# Why this matters: when a release changes the install layout itself, running
# the previously installed sync script applies the OLD layout while the drift
# verifier (always read from source) checks for the NEW one. The first update
# after such a release then fails, and only a second run converges. The remote
# update path and the runtime-drift sync path already read the source script;
# the --local path was the outlier.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

CREW="${REPO_ROOT}/core/bin/crew"
export AGENT_CREW_AUTO_SYNC_RUNTIME_ON_RUN=0
export AGENT_CREW_RUNTIME_DRIFT_CHECK_ON_RUN=0

TMP=$(make_tmp)
HOME_T="${TMP}/home"
ACHOME="${TMP}/agent-crew-home"
PROJECT_T="${TMP}/project"
mkdir -p "${HOME_T}" "${PROJECT_T}" "${TMP}/bin"

# Invoke crew the way an installed machine does: from a plain bin directory, so
# ASSET_ROOT falls back to AGENT_CREW_HOME instead of resolving to the repo's
# own core/ tree. Running the in-repo copy would hide the bug entirely.
cp "${CREW}" "${TMP}/bin/crew"
chmod +x "${TMP}/bin/crew"
CREW_INSTALLED="${TMP}/bin/crew"

run_update() {
  HOME="${HOME_T}" AGENT_CREW_HOME="${ACHOME}" CLAUDE_DIR="${HOME_T}/.claude" \
    CODEX_HOME="${HOME_T}/.codex" AGENT_CREW_SKIP_PATH_CLI=1 \
    bash "${CREW_INSTALLED}" update --local "${REPO_ROOT}" 2>&1
}

it "first update against a fresh home exits 0"
out=$(run_update)
rc=$?
assert_exit 0 "${rc}" "output: ${out: -500}"

# A user-created command exercises the concrete trigger: the layout change
# projects the installed user layer into discovery, so a stale installer leaves
# this file out of ~/.agent-crew/commands while the source-side verifier expects
# it there.
printf '# my own command\n' > "${ACHOME}/user/commands/my-local-cmd.md"

# Simulate the release-transition case: the installed sync script is an older
# build whose behavior differs from source. A stale installer that merely
# reports success would leave the install un-migrated.
STALE_MARKER="${TMP}/stale-installer-ran"
cat > "${ACHOME}/scripts/sync-local-install.sh" <<STALE
#!/usr/bin/env bash
# stale installed build from a previous release
touch "${STALE_MARKER}"
exit 0
STALE
chmod +x "${ACHOME}/scripts/sync-local-install.sh"

it "update does not execute the stale installed sync script"
out=$(run_update)
rc=$?
assert_file_absent "${STALE_MARKER}"

it "update still exits 0 when the installed sync script is stale"
assert_exit 0 "${rc}" "output: ${out: -500}"

it "update reports a passing drift check on that first run"
assert_contains "${out}" "PASS: install drift check"

it "update projects the user-created command into discovery"
assert_file_exists "${ACHOME}/commands/my-local-cmd.md"

it "update restores the installed sync script from source"
assert_true "$(cmp -s "${REPO_ROOT}/core/scripts/sync-local-install.sh" "${ACHOME}/scripts/sync-local-install.sh" && echo 0 || echo 1)" \
  "installed sync script should match source after update"

end_report
