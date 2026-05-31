#!/usr/bin/env bash
# Tests for the Channel B template seed + reconcile helpers:
#   core/setup/seed-skill-templates.sh
#   core/setup/reconcile-skill-templates.sh
#
# Contracts covered:
#   - seed: copy-if-absent; NEVER overwrite a user-edited file
#   - seed: skip README.md and SKILL-TEMPLATE.md
#   - seed: idempotent (re-run produces no further writes)
#   - seed: silent no-op when source dir is absent
#   - reconcile (check mode): emit advisory line for divergent skills
#   - reconcile (--write-diffs): write *.diff files to output dir
#   - reconcile: NEVER mutates the user-skills layer

set -u
source "$(dirname "$0")/_lib.bash"

SEED_SCRIPT="${SETUP_DIR}/seed-skill-templates.sh"
RECONCILE_SCRIPT="${SETUP_DIR}/reconcile-skill-templates.sh"

# --------------------------------------------------------------------------- #
# seed: copy-if-absent — fresh user dir gets all templates                    #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
TPL_DIR="${TMP}/templates"
USER_DIR="${TMP}/user/skills"
mkdir -p "${TPL_DIR}"
cat > "${TPL_DIR}/issuer-plane.md" <<'EOF'
# issuer-plane template
plane content v1
EOF
cat > "${TPL_DIR}/issuer-github.md" <<'EOF'
# issuer-github template
github content v1
EOF
cat > "${TPL_DIR}/README.md" <<'EOF'
this is documentation
EOF
cat > "${TPL_DIR}/SKILL-TEMPLATE.md" <<'EOF'
this is a structural stub
EOF

it "fresh user dir: exit 0"
out=$(bash "${SEED_SCRIPT}" "${TPL_DIR}" "${USER_DIR}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "fresh user dir: issuer-plane seeded"
assert_file_exists "${USER_DIR}/issuer-plane.md"

it "fresh user dir: issuer-github seeded"
assert_file_exists "${USER_DIR}/issuer-github.md"

it "fresh user dir: README.md NOT seeded (documentation, filtered)"
assert_file_absent "${USER_DIR}/README.md"

it "fresh user dir: SKILL-TEMPLATE.md NOT seeded (structural stub)"
assert_file_absent "${USER_DIR}/SKILL-TEMPLATE.md"

it "fresh user dir: log mentions seeded count"
assert_contains "${out}" "seeded=2"

it "fresh user dir: per-file log line for issuer-plane"
assert_contains "${out}" "issuer-plane.md"

# --------------------------------------------------------------------------- #
# seed: NEVER overwrites a user-edited file (load-bearing invariant)          #
# --------------------------------------------------------------------------- #

TMP2=$(make_tmp)
TPL_DIR2="${TMP2}/templates"
USER_DIR2="${TMP2}/user/skills"
mkdir -p "${TPL_DIR2}" "${USER_DIR2}"
cat > "${TPL_DIR2}/issuer-plane.md" <<'EOF'
# template content (framework version)
EOF
# User has already customized their copy with different content:
cat > "${USER_DIR2}/issuer-plane.md" <<'EOF'
# user-edited content
USER CUSTOM CONTENT — must NOT be overwritten by seed
EOF
ORIGINAL_USER_MTIME=$(stat -f '%m' "${USER_DIR2}/issuer-plane.md" 2>/dev/null \
                       || stat -c '%Y' "${USER_DIR2}/issuer-plane.md")

it "user-edited file: exit 0"
out=$(bash "${SEED_SCRIPT}" "${TPL_DIR2}" "${USER_DIR2}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "user-edited file: content preserved (NOT overwritten)"
grep -q "USER CUSTOM CONTENT" "${USER_DIR2}/issuer-plane.md"
assert_exit 0 "$?"

it "user-edited file: 'already present' message in log"
assert_contains "${out}" "already present, template not applied"

it "user-edited file: skipped count = 1"
assert_contains "${out}" "skipped=1"

it "user-edited file: seeded count = 0"
assert_contains "${out}" "seeded=0"

# --------------------------------------------------------------------------- #
# seed: idempotent — re-running produces no further writes                    #
# --------------------------------------------------------------------------- #

TMP3=$(make_tmp)
TPL_DIR3="${TMP3}/templates"
USER_DIR3="${TMP3}/user/skills"
mkdir -p "${TPL_DIR3}"
cat > "${TPL_DIR3}/issuer-plane.md" <<'EOF'
# template content
EOF

# First run: seeds the file.
bash "${SEED_SCRIPT}" "${TPL_DIR3}" "${USER_DIR3}" >/dev/null 2>&1
# Capture mtime after first run.
FIRST_MTIME=$(stat -f '%m' "${USER_DIR3}/issuer-plane.md" 2>/dev/null \
                || stat -c '%Y' "${USER_DIR3}/issuer-plane.md")

# Wait a second so mtime would visibly change if a copy happened.
sleep 1

# Second run: should NOT touch the file.
out=$(bash "${SEED_SCRIPT}" "${TPL_DIR3}" "${USER_DIR3}" 2>&1)

SECOND_MTIME=$(stat -f '%m' "${USER_DIR3}/issuer-plane.md" 2>/dev/null \
                 || stat -c '%Y' "${USER_DIR3}/issuer-plane.md")

it "idempotent: mtime unchanged after re-run"
assert_eq "${FIRST_MTIME}" "${SECOND_MTIME}"

it "idempotent: re-run reports skipped=1"
assert_contains "${out}" "skipped=1"

# --------------------------------------------------------------------------- #
# seed: silent no-op when source directory is absent                          #
# --------------------------------------------------------------------------- #

TMP4=$(make_tmp)
# Intentionally do NOT create ${TMP4}/templates

it "no source dir: exit 0"
out=$(bash "${SEED_SCRIPT}" "${TMP4}/templates" "${TMP4}/user/skills" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "no source dir: informational message"
assert_contains "${out}" "source directory absent"

# --------------------------------------------------------------------------- #
# reconcile (check mode): identical files produce no advisory                  #
# --------------------------------------------------------------------------- #

TMP5=$(make_tmp)
TPL_DIR5="${TMP5}/templates"
USER_DIR5="${TMP5}/user/skills"
mkdir -p "${TPL_DIR5}" "${USER_DIR5}"
cat > "${TPL_DIR5}/issuer-plane.md" <<'EOF'
# identical content
EOF
cp "${TPL_DIR5}/issuer-plane.md" "${USER_DIR5}/issuer-plane.md"

it "reconcile clean: exit 0"
out=$(bash "${RECONCILE_SCRIPT}" "${TPL_DIR5}" "${USER_DIR5}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "reconcile clean: NO 'diverged' line"
assert_not_contains "${out}" "diverged"

# --------------------------------------------------------------------------- #
# reconcile (check mode): divergent files produce single advisory             #
# --------------------------------------------------------------------------- #

TMP6=$(make_tmp)
TPL_DIR6="${TMP6}/templates"
USER_DIR6="${TMP6}/user/skills"
mkdir -p "${TPL_DIR6}" "${USER_DIR6}"
cat > "${TPL_DIR6}/issuer-plane.md" <<'EOF'
# template v2
new section added in v2
EOF
cat > "${USER_DIR6}/issuer-plane.md" <<'EOF'
# template v1
EOF

it "reconcile diverged: exit 0"
out=$(bash "${RECONCILE_SCRIPT}" "${TPL_DIR6}" "${USER_DIR6}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "reconcile diverged: advisory line printed"
assert_contains "${out}" "diverged"

it "reconcile diverged: filename in advisory"
assert_contains "${out}" "issuer-plane.md"

it "reconcile diverged: --reconcile-skills hint in advisory"
assert_contains "${out}" "--reconcile-skills"

it "reconcile diverged: user file NOT mutated (load-bearing)"
# The user file must still be the v1 template content
grep -q "template v1" "${USER_DIR6}/issuer-plane.md"
assert_exit 0 "$?"

it "reconcile diverged: user file does NOT contain v2 content"
out_check=$(grep -c "v2" "${USER_DIR6}/issuer-plane.md")
assert_eq "0" "${out_check}"

# --------------------------------------------------------------------------- #
# reconcile --write-diffs: writes *.diff files to output dir                  #
# --------------------------------------------------------------------------- #

DIFF_OUT="${TMP6}/reconcile-out"

it "reconcile --write-diffs: exit 0"
out=$(bash "${RECONCILE_SCRIPT}" --write-diffs "${DIFF_OUT}" \
        "${TPL_DIR6}" "${USER_DIR6}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "reconcile --write-diffs: diff file exists"
assert_file_exists "${DIFF_OUT}/issuer-plane.diff"

it "reconcile --write-diffs: diff contains template content marker"
grep -q "template v2" "${DIFF_OUT}/issuer-plane.diff"
assert_exit 0 "$?"

it "reconcile --write-diffs: diff contains user content marker"
grep -q "template v1" "${DIFF_OUT}/issuer-plane.diff"
assert_exit 0 "$?"

it "reconcile --write-diffs: user/skills NOT mutated by --write-diffs"
grep -q "template v1" "${USER_DIR6}/issuer-plane.md"
assert_exit 0 "$?"

it "reconcile --write-diffs: log lines mention the diff"
assert_contains "${out}" "reconcile diff written"

it "reconcile --write-diffs: summary line printed"
assert_contains "${out}" "1 diff"

it "reconcile --write-diffs: 'no automatic write' message"
assert_contains "${out}" "No automatic write"

# --------------------------------------------------------------------------- #
# reconcile: absent user skill is NOT a divergence (seed helper's job)        #
# --------------------------------------------------------------------------- #

TMP7=$(make_tmp)
TPL_DIR7="${TMP7}/templates"
USER_DIR7="${TMP7}/user/skills"
mkdir -p "${TPL_DIR7}" "${USER_DIR7}"
cat > "${TPL_DIR7}/issuer-plane.md" <<'EOF'
# template content
EOF
# Intentionally do NOT create the user-layer file

it "reconcile: absent user skill produces NO advisory"
out=$(bash "${RECONCILE_SCRIPT}" "${TPL_DIR7}" "${USER_DIR7}" 2>&1)
assert_not_contains "${out}" "diverged"

# --------------------------------------------------------------------------- #
# reconcile: invalid args                                                      #
# --------------------------------------------------------------------------- #

it "reconcile --write-diffs without arg: exit 1"
out=$(bash "${RECONCILE_SCRIPT}" --write-diffs 2>&1)
rc=$?
assert_exit 1 "${rc}"

it "reconcile unknown flag: exit 1"
out=$(bash "${RECONCILE_SCRIPT}" --bogus 2>&1)
rc=$?
assert_exit 1 "${rc}"

end_report
