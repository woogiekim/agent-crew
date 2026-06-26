#!/usr/bin/env bash
# Tests for core/setup/common.sh — exercises each function in a tmp dir
# against synthetic source / system / user / dest layouts.

set -u  # do NOT set -e — failed assertions must keep running

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
# shellcheck source=../../core/setup/common.sh
# common.sh has `set -euo pipefail`. We source it, then turn off -e for tests.
source "${SETUP_DIR}/common.sh"
set +e

# --------------------------------------------------------------------------- #
# copy_dir_contents                                                           #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
mkdir -p "${TMP}/src/sub"
echo "alpha" > "${TMP}/src/alpha.md"
echo "beta"  > "${TMP}/src/sub/beta.md"

it "copy_dir_contents copies files and subdirs"
copy_dir_contents "${TMP}/src" "${TMP}/dst" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}" "copy_dir_contents exit"

it "copy_dir_contents preserved top-level file"
assert_file_exists "${TMP}/dst/alpha.md"

it "copy_dir_contents preserved nested file"
assert_file_exists "${TMP}/dst/sub/beta.md"

it "copy_dir_contents tolerates missing source dir"
copy_dir_contents "${TMP}/does-not-exist" "${TMP}/dst-empty" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}" "missing-source-dir return"

# --------------------------------------------------------------------------- #
# sync_dir_contents_prune                                                     #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
mkdir -p "${TMP}/src/sub" "${TMP}/dst/sub"
echo "alpha" > "${TMP}/src/alpha.md"
echo "beta" > "${TMP}/src/sub/beta.md"
echo "old" > "${TMP}/dst/stale.md"
echo "old-nested" > "${TMP}/dst/sub/stale-nested.md"

it "sync_dir_contents_prune exits 0"
sync_dir_contents_prune "${TMP}/src" "${TMP}/dst" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}" "sync_dir_contents_prune exit"

it "sync_dir_contents_prune copies top-level source file"
assert_file_exists "${TMP}/dst/alpha.md"

it "sync_dir_contents_prune copies nested source file"
assert_file_exists "${TMP}/dst/sub/beta.md"

it "sync_dir_contents_prune removes stale top-level file"
assert_file_absent "${TMP}/dst/stale.md"

it "sync_dir_contents_prune removes stale nested file"
assert_file_absent "${TMP}/dst/sub/stale-nested.md"

# --------------------------------------------------------------------------- #
# sync_system_agents                                                          #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
mkdir -p "${TMP}/source-agents" "${TMP}/system-agents"
echo "current" > "${TMP}/source-agents/current.md"
# Pre-existing stale system agent that's not in source and not in exceptions
echo "stale"   > "${TMP}/system-agents/stale.md"
echo "keepme"  > "${TMP}/system-agents/mcp-manager.md"  # exception, must be kept
echo "current-old" > "${TMP}/system-agents/current.md"

it "sync_system_agents runs and exits 0"
sync_system_agents "${TMP}/source-agents" "${TMP}/system-agents" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

it "sync_system_agents copied source agent into system"
assert_file_exists "${TMP}/system-agents/current.md"

it "sync_system_agents updated current.md contents from source"
actual=$(cat "${TMP}/system-agents/current.md")
assert_eq "current" "${actual}"

it "sync_system_agents removed stale agent not in source"
assert_file_absent "${TMP}/system-agents/stale.md"

it "sync_system_agents preserved exception agent (mcp-manager.md)"
assert_file_exists "${TMP}/system-agents/mcp-manager.md"

# --------------------------------------------------------------------------- #
# sync_system_skills                                                          #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
mkdir -p "${TMP}/source-skills" "${TMP}/system-skills"
echo "x" > "${TMP}/source-skills/keep.md"
echo "y" > "${TMP}/system-skills/keep.md"
echo "z" > "${TMP}/system-skills/stale-skill.md"

it "sync_system_skills exits 0"
sync_system_skills "${TMP}/source-skills" "${TMP}/system-skills" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

it "sync_system_skills updates kept skill"
assert_file_exists "${TMP}/system-skills/keep.md"

it "sync_system_skills removes stale skill"
assert_file_absent "${TMP}/system-skills/stale-skill.md"

# --------------------------------------------------------------------------- #
# merge_agents_to_discovery                                                   #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
mkdir -p "${TMP}/sys-agents" "${TMP}/user-agents" "${TMP}/dest"
echo "sys-only" > "${TMP}/sys-agents/sys.md"
echo "user-only" > "${TMP}/user-agents/user.md"
echo "stale" > "${TMP}/dest/stale.md"   # not in either source — must be removed

it "merge_agents_to_discovery (no conflicts) exits 0"
merge_agents_to_discovery \
  "${TMP}/sys-agents" "${TMP}/user-agents" "${TMP}/dest" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

it "merge_agents_to_discovery copied system agent to dest"
assert_file_exists "${TMP}/dest/sys.md"

it "merge_agents_to_discovery copied user agent to dest"
assert_file_exists "${TMP}/dest/user.md"

it "merge_agents_to_discovery removed stale dest file"
assert_file_absent "${TMP}/dest/stale.md"

# Regression: user-owned agents with names removed from system/ remain in
# generated host discovery paths. This protects custom scribe agents from the
# Phase 3.1 migration loop.
TMP=$(make_tmp)
mkdir -p "${TMP}/sys-agents" "${TMP}/user-agents" "${TMP}/dest"
echo "user-scribe" > "${TMP}/user-agents/scribe.md"
echo "old-generated" > "${TMP}/dest/scribe.md"

it "merge_agents_to_discovery preserves user-owned scribe discovery output"
merge_agents_to_discovery \
  "${TMP}/sys-agents" "${TMP}/user-agents" "${TMP}/dest" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

it "merge_agents_to_discovery writes user-owned scribe to discovery"
actual=$(cat "${TMP}/dest/scribe.md" 2>/dev/null || true)
assert_eq "user-scribe" "${actual}"

# Regression: merge_agents_to_discovery must not treat the shared host
# dest/skills/ directory as wholly agent-crew-owned. Third-party skills placed
# there by other tooling must survive crew:update.
TMP=$(make_tmp)
mkdir -p "${TMP}/sys-agents/skills" "${TMP}/user-agents" "${TMP}/dest/skills"
echo "agent-crew-skill" > "${TMP}/sys-agents/skills/tdd.md"
echo "third-party-devstack" > "${TMP}/dest/skills/devstack.md"

it "merge_agents_to_discovery preserves third-party dest skill files"
merge_agents_to_discovery \
  "${TMP}/sys-agents" "${TMP}/user-agents" "${TMP}/dest" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

it "merge_agents_to_discovery leaves third-party dest skill in place"
assert_file_exists "${TMP}/dest/skills/devstack.md"

it "merge_agents_to_discovery preserves third-party dest skill contents"
actual=$(cat "${TMP}/dest/skills/devstack.md" 2>/dev/null || true)
assert_eq "third-party-devstack" "${actual}"

it "merge_agents_to_discovery still copies agent-crew system skills"
assert_file_exists "${TMP}/dest/skills/tdd.md"

# Now create a conflict
TMP=$(make_tmp)
mkdir -p "${TMP}/sys-agents" "${TMP}/user-agents" "${TMP}/dest"
echo "system-version" > "${TMP}/sys-agents/conflicted.md"
echo "user-version"   > "${TMP}/user-agents/conflicted.md"
echo "user-clean"     > "${TMP}/user-agents/clean.md"

it "merge_agents_to_discovery with conflict exits 0"
output=$(merge_agents_to_discovery \
  "${TMP}/sys-agents" "${TMP}/user-agents" "${TMP}/dest" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "merge_agents_to_discovery warns on conflict"
assert_contains "${output}" "conflict"

it "merge_agents_to_discovery copies system version of conflicted agent"
actual=$(cat "${TMP}/dest/conflicted.md")
assert_eq "system-version" "${actual}"

it "merge_agents_to_discovery copies non-conflicting user agent"
assert_file_exists "${TMP}/dest/clean.md"

# --------------------------------------------------------------------------- #
# merge_skills_to_discovery — user wins precedence                            #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
mkdir -p "${TMP}/sys-skills" "${TMP}/user-skills" "${TMP}/dest"
echo "system-skill" > "${TMP}/sys-skills/x.md"
echo "user-skill"   > "${TMP}/user-skills/x.md"

it "merge_skills_to_discovery exits 0"
output=$(merge_skills_to_discovery \
  "${TMP}/sys-skills" "${TMP}/user-skills" "${TMP}/dest" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "merge_skills_to_discovery: user version wins (overwrite)"
actual=$(cat "${TMP}/dest/x.md")
assert_eq "user-skill" "${actual}"

it "merge_skills_to_discovery explains user overrides are preserved"
assert_contains "${output}" "not overwritten by system updates"
assert_contains "${output}" "crew update --reconcile-skills"

# --------------------------------------------------------------------------- #
# register_local_git_excludes — append + idempotent                           #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
PROJ="${TMP}/proj"
mkdir -p "${PROJ}"
git -C "${PROJ}" init -q >/dev/null 2>&1

# Note: register_local_git_excludes uses `git rev-parse --git-path info/exclude`
# which returns a RELATIVE path. The current implementation then performs
# mkdir / touch / python writes against that relative path from the caller's
# CWD, so the function only works correctly if the caller has already cd'd
# into the project root. This matches how install.sh / setup-host.sh invoke
# it in practice (they cd into PROJECT_ROOT first), so we replicate that here.
#
# BUG (documented, not blocking): if a caller invokes the function from any
# other directory, the exclude file is written to `<caller-cwd>/.git/info/exclude`
# instead of `<project_root>/.git/info/exclude`. A robust fix would be to either
# pass --absolute-git-dir to git rev-parse, or to cd into project_root inside
# the function. See tests/README.md § Known issues.
pushd "${PROJ}" >/dev/null

it "register_local_git_excludes first call exits 0"
register_local_git_excludes "${PROJ}" ".agent-crew" "build/" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

it "register_local_git_excludes wrote marker block"
exclude_path="${PROJ}/.git/info/exclude"
content=$(cat "${exclude_path}" 2>/dev/null || echo "")
assert_contains "${content}" "agent-crew generated artifacts"

it "register_local_git_excludes wrote entry"
assert_contains "${content}" ".agent-crew"

it "register_local_git_excludes idempotent re-run does not duplicate"
register_local_git_excludes "${PROJ}" ".agent-crew" "build/" >/dev/null 2>&1
# Count marker-start occurrences (use grep -Fx for exact line match — the
# closing marker `# /agent-crew generated artifacts` also contains the
# substring 'agent-crew generated artifacts', so a substring count would
# return 2 even when there's just one marker block).
n=$(grep -cFx "# agent-crew generated artifacts" "${exclude_path}" \
      2>/dev/null | tr -d '[:space:]')
assert_eq 1 "${n}" "exact marker-start count"

it "register_local_git_excludes idempotent: closing marker also single"
n=$(grep -cFx "# /agent-crew generated artifacts" "${exclude_path}" \
      2>/dev/null | tr -d '[:space:]')
assert_eq 1 "${n}" "exact marker-end count"

popd >/dev/null

it "register_local_git_excludes no-op outside git worktree"
register_local_git_excludes "${TMP}" "x" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}" "non-git dir is a silent no-op"

end_report
