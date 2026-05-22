#!/usr/bin/env bash
# Verify the update dry-run verifier mutates only temporary install trees.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

VERIFIER="${SCRIPTS_DIR}/verify-update-dry-run.sh"

it "update dry-run verifier exits 0"
OUTPUT=$(bash "${VERIFIER}" "${REPO_ROOT}" 2>&1)
rc=$?
assert_exit 0 "${rc}" "verify-update-dry-run"

it "update dry-run verifier reports PASS"
assert_contains "${OUTPUT}" "PASS: update dry-run verifier"

it "update dry-run verifier does not leak task-runner into real Codex template"
assert_file_absent "${REPO_ROOT}/adapters/codex/template/agents/task-runner.toml"

end_report
