#!/usr/bin/env bash
# Tests for core/scripts/migrate-rm-stale.sh
#
# Contract:
#   usage: migrate-rm-stale.sh LABEL PATH [PATH ...]
#   exit 0 on success (regardless of removal count)
#   exit 1 on invalid args (no label or no paths)

set -u
source "$(dirname "$0")/_lib.bash"

SCRIPT="${SCRIPTS_DIR}/migrate-rm-stale.sh"

# --------------------------------------------------------------------------- #
# All paths absent → "no stale files found" + exit 0                         #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)

it "all paths absent: exit 0"
out=$(bash "${SCRIPT}" "test-label" "${TMP}/missing1" "${TMP}/missing2" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "all paths absent: stdout reports 'no stale files found'"
assert_contains "${out}" "no stale files found"

# --------------------------------------------------------------------------- #
# Some paths exist → remove them + exit 0                                    #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
touch "${TMP}/file-a" "${TMP}/file-b"

it "some paths exist: exit 0"
out=$(bash "${SCRIPT}" "real" "${TMP}/file-a" "${TMP}/file-b" \
        "${TMP}/file-missing" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "some paths exist: removed files no longer present"
assert_file_absent "${TMP}/file-a"

it "some paths exist: second removed file absent"
assert_file_absent "${TMP}/file-b"

it "some paths exist: stdout reports removal count"
# Output is "[crew:update] real: removed 2 stale file(s)."
assert_contains "${out}" "removed 2"

# --------------------------------------------------------------------------- #
# Idempotent re-run                                                           #
# --------------------------------------------------------------------------- #

it "re-run on already-cleaned dir: exit 0"
out=$(bash "${SCRIPT}" "real" "${TMP}/file-a" "${TMP}/file-b" 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "re-run reports 'no stale files found'"
assert_contains "${out}" "no stale files found"

# --------------------------------------------------------------------------- #
# Invalid args                                                                #
# --------------------------------------------------------------------------- #

it "no args: exit 1"
out=$(bash "${SCRIPT}" 2>&1)
rc=$?
assert_exit 1 "${rc}"

it "only label, no paths: exit 1"
out=$(bash "${SCRIPT}" "label-only" 2>&1)
rc=$?
assert_exit 1 "${rc}"

it "usage message on invalid args"
assert_contains "${out}" "usage"

# --------------------------------------------------------------------------- #
# Label appears in output                                                     #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
touch "${TMP}/stale.md"

it "label appears in log lines"
out=$(bash "${SCRIPT}" "Phase 3.1 scribe" "${TMP}/stale.md" 2>&1)
assert_contains "${out}" "Phase 3.1 scribe"

end_report
