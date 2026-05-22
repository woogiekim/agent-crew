#!/usr/bin/env bash
# Guard crew:update/install interactions that can overwrite active host capabilities.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

TMP=$(make_tmp)
ACHOME="${TMP}/agent-crew-home"
mkdir -p "${ACHOME}"

it "sourcing install.sh only loads helpers"
output=$(
  AGENT_CREW_HOME="${ACHOME}" \
  AGENT_CREW_INSTALL_CLAUDE_COMPAT=0 \
    bash -c '. "'"${REPO_ROOT}"'/install.sh"; declare -F install_global >/dev/null; [ ! -d "'"${ACHOME}"'/system" ]' 2>&1
)
rc=$?
assert_exit 0 "${rc}" "source install.sh should not run install_global; output=${output}"

it "install.sh prevents Claude compatibility pass from writing capabilities"
install_content=$(cat "${REPO_ROOT}/install.sh")
assert_contains "${install_content}" "AGENT_CREW_WRITE_CAPABILITIES=0" "Claude compat setup must not overwrite active host capabilities"

it "Claude setup honors the write-capabilities opt-out"
claude_setup=$(cat "${REPO_ROOT}/adapters/claude/setup.sh")
assert_contains "${claude_setup}" 'AGENT_CREW_WRITE_CAPABILITIES:-1' "Claude adapter must expose an opt-out guard"

it "Codex setup honors the write-capabilities opt-out"
codex_setup=$(cat "${REPO_ROOT}/adapters/codex/setup.sh")
assert_contains "${codex_setup}" 'AGENT_CREW_WRITE_CAPABILITIES:-1' "Codex adapter must expose an opt-out guard"

it "Codex setup registers automatic issue reporter hooks"
assert_contains "${codex_setup}" "auto-issue-report.sh" "Codex hooks must route agent-crew bug reports"

it "Claude setup registers automatic issue reporter hooks"
claude_setup=$(cat "${REPO_ROOT}/adapters/claude/setup.sh")
assert_contains "${claude_setup}" "auto-issue-report.sh" "Claude hooks must route agent-crew bug reports"

it "crew:update install pass uses repository root as source"
update_doc=$(cat "${REPO_ROOT}/core/commands/update.md")
assert_contains "${update_doc}" 'AGENT_CREW_SOURCE_DIR="${SOURCE_ROOT}"' "install.sh expects the repository root, not core/"

it "crew:update install pass skips Claude compatibility before project-local setup"
assert_contains "${update_doc}" "AGENT_CREW_INSTALL_CLAUDE_COMPAT=0" "global hook registration must not clobber project capabilities"

it "crew:update no longer documents the broken core/core source path"
assert_not_contains "${update_doc}" 'AGENT_CREW_SOURCE_DIR="${SOURCE_DIR}"' "SOURCE_DIR points at core/ and makes install.sh look for core/core"

it "Phase 3.1 scribe migration preserves user-owned discovery outputs"
assert_contains "${update_doc}" '[ ! -f "${AGENT_CREW_HOME}/user/agents/scribe.md" ]' "scribe discovery cleanup must be gated by absence of user scribe"

it "Phase 3.1 scribe migration documents the re-removal loop guard"
assert_contains "${update_doc}" "MUST NOT be removed" "user-owned discovery files must not be deleted on every update"

it "Phase 3.1 scribe migration keeps system cleanup separate from discovery cleanup"
assert_contains "${update_doc}" "Phase 3.1 scribe discovery" "discovery cleanup must be its own guarded migration label"

end_report
