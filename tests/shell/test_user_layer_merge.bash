#!/usr/bin/env bash
# Verify the user layer contract for rules and user commands:
#   - user/rules/ merges into the rules discovery view with user-wins
#   - the host mirror receives the merged result
#   - no user-layer file is ever deleted or rewritten by a sync
#   - repeated syncs are byte-stable
#   - user commands are seeded from source, refreshed only while pristine,
#     and reported (never overwritten) once the user has edited them

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

TMP=$(make_tmp)
HOME_T="${TMP}/home"
ACHOME="${TMP}/agent-crew-home"
CLAUDE_T="${HOME_T}/.claude"
PROJECT_ROOT_T="${TMP}/project"
mkdir -p "${HOME_T}" "${PROJECT_ROOT_T}" "${CLAUDE_T}/agent-crew"
mkdir -p "${ACHOME}/user/rules/capabilities"

printf '# local override\n' > "${ACHOME}/user/rules/code-quality.md"
printf '# local only rule\n' > "${ACHOME}/user/rules/local-only.md"
printf '# local capability\n' > "${ACHOME}/user/rules/capabilities/local-cap.md"

USER_RULES_BEFORE=$(cd "${ACHOME}/user/rules" && find . -type f -exec shasum {} \; | sort)

run_sync() {
  HOME="${HOME_T}" AGENT_CREW_HOME="${ACHOME}" CLAUDE_DIR="${CLAUDE_T}" \
    CODEX_HOME="${HOME_T}/.codex" AGENT_CREW_HOST=claude \
    bash "${REPO_ROOT}/core/scripts/sync-local-install.sh" "${REPO_ROOT}" "${PROJECT_ROOT_T}" 2>&1
}

it "first sync exits 0"
out=$(run_sync)
rc=$?
assert_exit 0 "${rc}" "output: ${out: -400}"

it "user-only rule reaches the rules discovery view"
assert_file_exists "${ACHOME}/rules/local-only.md"

it "user rule in a subdirectory reaches the discovery view"
assert_file_exists "${ACHOME}/rules/capabilities/local-cap.md"

it "user rule wins over the system rule of the same name"
assert_eq "# local override" "$(cat "${ACHOME}/rules/code-quality.md" 2>/dev/null)"

it "system rules still populate the discovery view"
assert_file_exists "${ACHOME}/rules/task-injection.md"

it "host mirror receives the user-only rule"
assert_file_exists "${CLAUDE_T}/agent-crew/rules/local-only.md"

it "host mirror receives the user-wins override"
assert_eq "# local override" "$(cat "${CLAUDE_T}/agent-crew/rules/code-quality.md" 2>/dev/null)"

it "sync leaves every user rule byte-identical"
assert_eq "${USER_RULES_BEFORE}" "$(cd "${ACHOME}/user/rules" && find . -type f -exec shasum {} \; | sort)"

it "stale discovery rule absent from both layers is pruned"
printf 'stale\n' > "${ACHOME}/rules/zz-stale-rule.md"
out=$(run_sync)
assert_file_absent "${ACHOME}/rules/zz-stale-rule.md"

it "pruning does not remove the user-owned rule from discovery"
assert_file_exists "${ACHOME}/rules/local-only.md"

it "repeated sync leaves the rules discovery view byte-stable"
before=$(cd "${ACHOME}/rules" && find . -type f -exec shasum {} \; | sort)
out=$(run_sync)
assert_eq "${before}" "$(cd "${ACHOME}/rules" && find . -type f -exec shasum {} \; | sort)"

it "user command edits survive a sync"
printf '# edited by the user\n' > "${ACHOME}/user/commands/parity-check.md"
out=$(run_sync)
assert_eq "# edited by the user" "$(cat "${ACHOME}/user/commands/parity-check.md" 2>/dev/null)"

it "a diverged user command is reported to the operator"
assert_contains "${out}" "parity-check.md diverged from source"

it "the edited user command wins in the commands discovery view"
assert_eq "# edited by the user" "$(cat "${ACHOME}/commands/parity-check.md" 2>/dev/null)"

# ── seed-user-commands.sh unit behavior ──────────────────────────────────────
SEED_SRC="${TMP}/seed-src"
SEED_DEST="${TMP}/seed-dest"
SEED_MANIFEST="${TMP}/seed-manifest/commands.json"
mkdir -p "${SEED_SRC}"
printf 'v1\n' > "${SEED_SRC}/alpha.md"
printf 'v1\n' > "${SEED_SRC}/beta.md"

seed() {
  bash "${REPO_ROOT}/core/setup/seed-user-commands.sh" \
    "${SEED_SRC}" "${SEED_DEST}" "${SEED_MANIFEST}" 2>&1
}

it "seeding copies absent commands"
out=$(seed)
rc=$?
assert_exit 0 "${rc}" "output: ${out}"

it "seeded command has the source content"
assert_eq "v1" "$(cat "${SEED_DEST}/alpha.md" 2>/dev/null)"

it "a pristine seeded command is refreshed when the source changes"
printf 'v2\n' > "${SEED_SRC}/alpha.md"
out=$(seed)
assert_eq "v2" "$(cat "${SEED_DEST}/alpha.md" 2>/dev/null)"

it "an edited command is never overwritten by a source change"
printf 'mine\n' > "${SEED_DEST}/beta.md"
printf 'v2\n' > "${SEED_SRC}/beta.md"
out=$(seed)
assert_eq "mine" "$(cat "${SEED_DEST}/beta.md" 2>/dev/null)"

it "the edited command is reported as diverged"
assert_contains "${out}" "beta.md diverged from source"

it "re-seeding an unchanged tree writes nothing new"
before=$(cd "${SEED_DEST}" && find . -type f -exec shasum {} \; | sort)
manifest_before=$(cat "${SEED_MANIFEST}")
out=$(seed)
assert_eq "${before}" "$(cd "${SEED_DEST}" && find . -type f -exec shasum {} \; | sort)"

it "re-seeding leaves the manifest unchanged"
assert_eq "${manifest_before}" "$(cat "${SEED_MANIFEST}")"

end_report
