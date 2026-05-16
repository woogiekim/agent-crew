#!/usr/bin/env bash
# Tests for core/scripts/detect-inject-intent.sh
#
# Contract:
#   stdin or $1 → user input
#   exit 0 on match (stdout = matched phrase)
#   exit 1 on no match

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

SCRIPT="${SCRIPTS_DIR}/detect-inject-intent.sh"

# Helper: feed text via stdin (matches how hooks invoke the script).
# The script's [ -t 0 ] check chooses the $1 fallback only when stdin is
# a tty; under command substitution / pipelines we must pipe.
run_detect() {
  printf '%s' "$1" | bash "${SCRIPT}"
}

# --------------------------------------------------------------------------- #
# Korean inject phrases — should match (exit 0)                               #
# --------------------------------------------------------------------------- #

it "matches Korean: 추가로 해줘"
out=$(run_detect "이것도 추가로 해줘")
rc=$?
assert_exit 0 "${rc}"

it "matches Korean: 이것도 부탁해"
out=$(run_detect "이것도 부탁해")
rc=$?
assert_exit 0 "${rc}"

it "matches Korean: 더해줘"
out=$(run_detect "더해줘")
rc=$?
assert_exit 0 "${rc}"

it "matches Korean: 더 해줘 (with space)"
out=$(run_detect "이것도 더 해줘")
rc=$?
assert_exit 0 "${rc}"

it "matches Korean: 이어서 해줘"
out=$(run_detect "이어서 해줘")
rc=$?
assert_exit 0 "${rc}"

it "matches Korean: 이것까지"
out=$(run_detect "이것까지 부탁")
rc=$?
assert_exit 0 "${rc}"

# --------------------------------------------------------------------------- #
# English inject phrases — should match                                       #
# --------------------------------------------------------------------------- #

it "matches English: also do"
out=$(run_detect "Also do the cleanup")
rc=$?
assert_exit 0 "${rc}"

it "matches English: and also"
out=$(run_detect "And also rename the file")
rc=$?
assert_exit 0 "${rc}"

it "matches English: additionally"
out=$(run_detect "Additionally, refactor X")
rc=$?
assert_exit 0 "${rc}"

it "matches English: one more thing"
out=$(run_detect "one more thing — update the README")
rc=$?
assert_exit 0 "${rc}"

it "matches English: while you're at it"
out=$(run_detect "while you're at it, fix the typo")
rc=$?
assert_exit 0 "${rc}"

it "matches English case-insensitive: ALSO DO"
out=$(run_detect "ALSO DO this")
rc=$?
assert_exit 0 "${rc}"

# --------------------------------------------------------------------------- #
# Negative cases — should NOT match                                           #
# --------------------------------------------------------------------------- #

it "does not match: 'implement X' (fresh request)"
out=$(run_detect "implement the new feature")
rc=$?
assert_exit 1 "${rc}"

it "does not match: 'add feature Y'"
out=$(run_detect "add feature Y to the codebase")
rc=$?
assert_exit 1 "${rc}"

it "does not match: incomplete Korean connector '더 추가'"
out=$(run_detect "더 추가")
rc=$?
assert_exit 1 "${rc}"

it "does not match: incomplete Korean connector '추가' alone"
out=$(run_detect "추가")
rc=$?
assert_exit 1 "${rc}"

it "does not match: lone 'also' without 'do'"
out=$(run_detect "also")
rc=$?
assert_exit 1 "${rc}"

it "does not match: empty input"
out=$(run_detect "")
rc=$?
assert_exit 1 "${rc}"

# --------------------------------------------------------------------------- #
# Output: matched phrase is echoed on stdout                                  #
# --------------------------------------------------------------------------- #

it "on match, stdout contains matched phrase"
out=$(run_detect "추가로 해줘")
rc=$?
# rc=0 already covered above; the phrase should appear in stdout
assert_contains "${out}" "추가로 해줘"

end_report
