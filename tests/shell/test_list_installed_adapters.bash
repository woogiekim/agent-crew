#!/usr/bin/env bash
# Tests for core/scripts/list-installed-adapters.sh
#
# Contract:
#   usage: list-installed-adapters.sh <agent-prefix>
#   exit 0 on success (with or without matches)
#   exit 1 on invalid args
#   stdout: one adapter name per line, sorted

set -u
source "$(dirname "$0")/_lib.bash"

SCRIPT="${SCRIPTS_DIR}/list-installed-adapters.sh"

# --------------------------------------------------------------------------- #
# Multiple installed adapters → list them, sorted                              #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
mkdir -p "${TMP}/user/skills"
touch "${TMP}/user/skills/issuer-plane.md"
touch "${TMP}/user/skills/issuer-github.md"
touch "${TMP}/user/skills/issuer-gitlab.md"
touch "${TMP}/user/skills/README.md"

it "multiple adapters: exit 0"
out=$(AGENT_CREW_HOME="${TMP}" bash "${SCRIPT}" issuer 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "multiple adapters: lists all three"
assert_contains "${out}" "plane"

it "multiple adapters: includes github"
assert_contains "${out}" "github"

it "multiple adapters: includes gitlab"
assert_contains "${out}" "gitlab"

it "multiple adapters: README.md not listed as adapter"
assert_not_contains "${out}" "README"

it "multiple adapters: sorted order (alphabetical)"
# Sorted output: github, gitlab, plane (one per line)
expected_sorted=$'github\ngitlab\nplane'
assert_eq "${expected_sorted}" "${out}"

# --------------------------------------------------------------------------- #
# Wrong prefix → empty output, still exit 0                                    #
# --------------------------------------------------------------------------- #

it "wrong prefix: exit 0"
out=$(AGENT_CREW_HOME="${TMP}" bash "${SCRIPT}" backend 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "wrong prefix: empty stdout"
assert_eq "" "${out}"

# --------------------------------------------------------------------------- #
# Filter discipline: prefix must match exactly at the start                    #
# --------------------------------------------------------------------------- #

TMP2=$(make_tmp)
mkdir -p "${TMP2}/user/skills"
touch "${TMP2}/user/skills/issuer-plane.md"
touch "${TMP2}/user/skills/my-issuer-helper.md"   # NOT an issuer adapter
touch "${TMP2}/user/skills/issuerless-thing.md"    # NOT an issuer adapter

it "prefix discipline: only files starting with '<prefix>-' are matched"
out=$(AGENT_CREW_HOME="${TMP2}" bash "${SCRIPT}" issuer 2>&1)
assert_eq "plane" "${out}"

# --------------------------------------------------------------------------- #
# Directory does not exist → empty output, exit 0                              #
# --------------------------------------------------------------------------- #

TMP3=$(make_tmp)
# Intentionally do NOT create ${TMP3}/user/skills

it "missing skills dir: exit 0"
out=$(AGENT_CREW_HOME="${TMP3}" bash "${SCRIPT}" issuer 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "missing skills dir: empty stdout"
assert_eq "" "${out}"

# --------------------------------------------------------------------------- #
# Empty skills dir → empty output, exit 0                                      #
# --------------------------------------------------------------------------- #

TMP4=$(make_tmp)
mkdir -p "${TMP4}/user/skills"

it "empty skills dir: exit 0"
out=$(AGENT_CREW_HOME="${TMP4}" bash "${SCRIPT}" issuer 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "empty skills dir: empty stdout"
assert_eq "" "${out}"

# --------------------------------------------------------------------------- #
# Compound prefix (e.g., `backend-typescript`) handled correctly               #
# --------------------------------------------------------------------------- #

TMP5=$(make_tmp)
mkdir -p "${TMP5}/user/skills"
touch "${TMP5}/user/skills/backend-kotlin-spring.md"
touch "${TMP5}/user/skills/backend-typescript-nest.md"
touch "${TMP5}/user/skills/backend-python-fastapi.md"

it "compound names: lists the lang-framework portion"
out=$(AGENT_CREW_HOME="${TMP5}" bash "${SCRIPT}" backend 2>&1)
assert_contains "${out}" "kotlin-spring"

it "compound names: typescript-nest preserved"
assert_contains "${out}" "typescript-nest"

it "compound names: python-fastapi preserved"
assert_contains "${out}" "python-fastapi"

# --------------------------------------------------------------------------- #
# Invalid args                                                                 #
# --------------------------------------------------------------------------- #

it "no args: exit 1"
out=$(bash "${SCRIPT}" 2>&1)
rc=$?
assert_exit 1 "${rc}"

it "no args: usage message"
assert_contains "${out}" "usage"

it "empty prefix: exit 1"
out=$(bash "${SCRIPT}" "" 2>&1)
rc=$?
assert_exit 1 "${rc}"

# --------------------------------------------------------------------------- #
# Idempotency: re-running produces identical output                            #
# --------------------------------------------------------------------------- #

it "idempotent: repeated invocation is identical"
out1=$(AGENT_CREW_HOME="${TMP}" bash "${SCRIPT}" issuer 2>&1)
out2=$(AGENT_CREW_HOME="${TMP}" bash "${SCRIPT}" issuer 2>&1)
assert_eq "${out1}" "${out2}"

end_report
