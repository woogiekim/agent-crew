#!/usr/bin/env bash
# tests/run-all.sh — top-level test runner for the agent-crew suite.
#
# Discovers tests under tests/python/, tests/shell/, tests/integration/
# and runs them with the right invocation per suite. Emits a final
# summary table; exits 0 if every suite passes, exit 1 otherwise.
#
# Usage:
#   bash tests/run-all.sh                # all suites
#   bash tests/run-all.sh python         # python suite only
#   bash tests/run-all.sh shell          # shell suite only
#   bash tests/run-all.sh integration    # integration suite only
#
# Environment:
#   PYTEST_BIN   — override pytest executable (default: `pytest`; falls back
#                  to `python3 -m pytest` when the executable is absent)

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}" || exit 2

TESTS_DIR="${REPO_ROOT}/tests"
PYTEST_BIN="${PYTEST_BIN:-pytest}"

# Suite selection
SUITES=()
if [ "$#" -eq 0 ]; then
  SUITES=(python shell integration)
else
  SUITES=("$@")
fi

# Counters
SUITE_NAMES=()
SUITE_RESULTS=()
SUITE_PASS=()
SUITE_FAIL=()
SUITE_DURATION=()

OVERALL_RC=0

# Wall-clock start
START_EPOCH=$(date +%s)

run_python_suite() {
  echo ""
  echo "==> Python suite (pytest)"
  echo ""
  local suite_start
  suite_start=$(date +%s)
  local pytest_cmd=()
  if command -v "${PYTEST_BIN}" >/dev/null 2>&1; then
    pytest_cmd=("${PYTEST_BIN}")
  elif [ "${PYTEST_BIN}" = "pytest" ] && python3 -c 'import pytest' >/dev/null 2>&1; then
    pytest_cmd=(python3 -m pytest)
  else
    echo "  pytest not on PATH — skipping python suite."
    echo "  Install with: python3 -m pip install --user pytest"
    SUITE_NAMES+=("python")
    SUITE_RESULTS+=("SKIPPED")
    SUITE_PASS+=(0)
    SUITE_FAIL+=(0)
    SUITE_DURATION+=("0s")
    return 0
  fi
  local out rc
  # Use -q for concise output; -rN to show short summary.
  out=$("${pytest_cmd[@]}" tests/python/ 2>&1)
  rc=$?
  echo "${out}"
  local suite_end
  suite_end=$(date +%s)
  local dur=$((suite_end - suite_start))

  # Extract pass/fail counts from pytest summary line (e.g. "43 passed in 2.58s")
  local p_count f_count
  p_count=$(echo "${out}" | grep -oE '[0-9]+ passed' | tail -1 | awk '{print $1}')
  f_count=$(echo "${out}" | grep -oE '[0-9]+ failed' | tail -1 | awk '{print $1}')
  p_count="${p_count:-0}"
  f_count="${f_count:-0}"

  SUITE_NAMES+=("python")
  if [ "${rc}" -eq 0 ]; then
    SUITE_RESULTS+=("PASS")
  else
    SUITE_RESULTS+=("FAIL")
    OVERALL_RC=1
  fi
  SUITE_PASS+=("${p_count}")
  SUITE_FAIL+=("${f_count}")
  SUITE_DURATION+=("${dur}s")
}

# Run every *.bash file in the given dir as its own suite entry.
run_bash_dir() {
  local label="$1" dir="$2"
  echo ""
  echo "==> ${label} suite (bash)"
  echo ""
  local total_pass=0 total_fail=0
  local suite_start
  suite_start=$(date +%s)
  local any_failed=0
  if [ ! -d "${dir}" ]; then
    echo "  (no ${label} suite directory at ${dir})"
    SUITE_NAMES+=("${label}")
    SUITE_RESULTS+=("SKIPPED")
    SUITE_PASS+=(0)
    SUITE_FAIL+=(0)
    SUITE_DURATION+=("0s")
    return 0
  fi
  local has_tests=0
  for f in "${dir}"/test_*.bash; do
    [ -f "${f}" ] || continue
    has_tests=1
    echo "--- $(basename "${f}") ---"
    local out rc
    out=$(bash "${f}" 2>&1)
    rc=$?
    echo "${out}"
    # Each lib script prints "tests=N  passed=P  failed=F"
    local p f_n
    p=$(echo "${out}" | grep -oE 'passed=[0-9]+' | tail -1 | sed 's/passed=//')
    f_n=$(echo "${out}" | grep -oE 'failed=[0-9]+' | tail -1 | sed 's/failed=//')
    p="${p:-0}"
    f_n="${f_n:-0}"
    total_pass=$((total_pass + p))
    total_fail=$((total_fail + f_n))
    if [ "${rc}" -ne 0 ]; then
      any_failed=1
    fi
    echo ""
  done
  local suite_end
  suite_end=$(date +%s)
  local dur=$((suite_end - suite_start))

  if [ "${has_tests}" -eq 0 ]; then
    echo "  (no test_*.bash files in ${dir})"
    SUITE_NAMES+=("${label}")
    SUITE_RESULTS+=("SKIPPED")
    SUITE_PASS+=(0)
    SUITE_FAIL+=(0)
    SUITE_DURATION+=("${dur}s")
    return 0
  fi

  SUITE_NAMES+=("${label}")
  if [ "${any_failed}" -eq 0 ]; then
    SUITE_RESULTS+=("PASS")
  else
    SUITE_RESULTS+=("FAIL")
    OVERALL_RC=1
  fi
  SUITE_PASS+=("${total_pass}")
  SUITE_FAIL+=("${total_fail}")
  SUITE_DURATION+=("${dur}s")
}

for suite in "${SUITES[@]}"; do
  case "${suite}" in
    python)
      run_python_suite
      ;;
    shell)
      run_bash_dir "shell" "${TESTS_DIR}/shell"
      ;;
    integration)
      run_bash_dir "integration" "${TESTS_DIR}/integration"
      ;;
    *)
      echo "WARN: unknown suite '${suite}' (valid: python, shell, integration)" >&2
      ;;
  esac
done

END_EPOCH=$(date +%s)
TOTAL_DUR=$((END_EPOCH - START_EPOCH))

# --------------------------------------------------------------------------- #
# Summary table                                                               #
# --------------------------------------------------------------------------- #

echo ""
echo "================================================================"
echo "  agent-crew test suite — summary"
echo "================================================================"
printf "  %-14s %-8s %8s %8s %10s\n" "SUITE" "RESULT" "PASSED" "FAILED" "DURATION"
echo "  --------------------------------------------------------------"
i=0
for name in "${SUITE_NAMES[@]}"; do
  printf "  %-14s %-8s %8s %8s %10s\n" \
    "${name}" \
    "${SUITE_RESULTS[$i]}" \
    "${SUITE_PASS[$i]}" \
    "${SUITE_FAIL[$i]}" \
    "${SUITE_DURATION[$i]}"
  i=$((i + 1))
done
echo "  --------------------------------------------------------------"
echo "  Total wall-clock: ${TOTAL_DUR}s"
if [ "${OVERALL_RC}" -eq 0 ]; then
  echo "  Overall: PASS"
else
  echo "  Overall: FAIL"
fi
echo "================================================================"

exit "${OVERALL_RC}"
