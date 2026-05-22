#!/usr/bin/env bash
# CLI smoke tests: every core/scripts/*.py supports --help cleanly, and
# every core/scripts/*.sh either accepts --help or fails with a usage
# message (documented usage exit). Low-coverage but catches
# syntax/import errors and broken argparse setup quickly.

set -u
source "$(dirname "$0")/../shell/_lib.bash"

PYTHON_SCRIPTS=(
  "validate-state-schema.py"
  "check-plaintext-approval.py"
  "auto-issue-reporter.py"
  "telemetry-aggregate.py"
  "cost-aggregate.py"
  "framework-review-check.py"
  "agent-capability-check.py"
  "pipeline-capability-check.py"
  "workflow-replay-check.py"
  "crew-runtime.py"
  "pipeline-quality-plan-check.py"
  "quality-loop-check.py"
  "reviewer-loop-decision.py"
)

# Shell scripts in core/scripts/ — exclude smoke-test-state which is itself
# a long-running smoke runner that mutates state, and bench-parallel which
# spawns parallel work. Tests that touch other persistent state are
# excluded by design.
SHELL_SCRIPTS=(
  "detect-inject-intent.sh"
  "migrate-rm-stale.sh"
  "sync-instructions.sh"
  "seed-instruction-rules.sh"
)

# --------------------------------------------------------------------------- #
# Python: --help must exit 0 + print "usage:"                                 #
# --------------------------------------------------------------------------- #

for s in "${PYTHON_SCRIPTS[@]}"; do
  it "python: ${s} --help exits 0"
  out=$(python3 "${SCRIPTS_DIR}/${s}" --help 2>&1)
  rc=$?
  assert_exit 0 "${rc}"

  it "python: ${s} --help prints usage"
  assert_contains "${out}" "usage"
done

# --------------------------------------------------------------------------- #
# Shell: invoke with --help or no args. Acceptable outcomes:                  #
#   exit 0 with usage/help text                                               #
#   exit 1 or 2 with usage text on stderr (documented usage exit)             #
# --------------------------------------------------------------------------- #

# sync-instructions.sh supports --help directly
it "shell: sync-instructions.sh --help exits 0 with usage"
out=$(bash "${SCRIPTS_DIR}/sync-instructions.sh" --help 2>&1)
rc=$?
assert_exit 0 "${rc}"

# migrate-rm-stale.sh: no args = usage exit 1
it "shell: migrate-rm-stale.sh (no args) exits 1 with usage"
out=$(bash "${SCRIPTS_DIR}/migrate-rm-stale.sh" 2>&1)
rc=$?
assert_exit 1 "${rc}"
it "shell: migrate-rm-stale.sh usage text printed"
assert_contains "${out}" "usage"

# seed-instruction-rules.sh: invalid mode = exit 2 with usage
it "shell: seed-instruction-rules.sh --foo exits 2"
out=$(MNEMOS_BIN=/bin/echo bash "${SCRIPTS_DIR}/seed-instruction-rules.sh" --foo 2>&1)
rc=$?
assert_exit 2 "${rc}"
it "shell: seed-instruction-rules.sh usage text printed on invalid mode"
assert_contains "${out}" "usage"

it "shell: mnemos-bounded.sh --help exits 0 with usage"
out=$(bash "${SCRIPTS_DIR}/mnemos-bounded.sh" --help 2>&1)
rc=$?
assert_exit 0 "${rc}"
it "shell: mnemos-bounded.sh help text printed"
assert_contains "${out}" "usage"

it "shell: sync-local-install.sh --help exits 0 with usage"
out=$(bash "${SCRIPTS_DIR}/sync-local-install.sh" --help 2>&1)
rc=$?
assert_exit 0 "${rc}"
it "shell: sync-local-install.sh help text printed"
assert_contains "${out}" "usage"

it "bin: crew --help exits 0"
out=$(bash "${REPO_ROOT}/core/bin/crew" --help 2>&1)
rc=$?
assert_exit 0 "${rc}"
it "bin: crew --help prints usage"
assert_contains "${out}" "usage: crew"

it "bin: crew report --help exits 0"
out=$(bash "${REPO_ROOT}/core/bin/crew" report --help 2>&1)
rc=$?
assert_exit 0 "${rc}"
it "bin: crew report --help prints usage"
assert_contains "${out}" "usage: crew report"

it "bin: crew-runtime agent --list exits 0"
out=$(python3 "${SCRIPTS_DIR}/crew-runtime.py" agent --asset-root "${REPO_ROOT}/core" --list 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "bin: crew-runtime agent --list includes analyst"
assert_contains "${out}" "analyst"

# detect-inject-intent.sh has no --help; an empty input is a no-op (exit 1).
# Just confirm the script parses cleanly (bash -n).
it "shell: detect-inject-intent.sh syntactically valid"
bash -n "${SCRIPTS_DIR}/detect-inject-intent.sh"
assert_exit 0 $?

# --------------------------------------------------------------------------- #
# Also bash-syntax-check every shell script in core/scripts/, core/setup/,    #
# core/hooks/ — cheap, catches editor accidents.                              #
# --------------------------------------------------------------------------- #

for f in "${SCRIPTS_DIR}"/*.sh "${SETUP_DIR}"/*.sh "${HOOKS_DIR}"/*.sh "${REPO_ROOT}/core/bin/"*; do
  [ -f "${f}" ] || continue
  base=$(basename "${f}")
  it "bash -n syntax check: ${base}"
  bash -n "${f}" 2>&1
  assert_exit 0 $?
done

end_report
