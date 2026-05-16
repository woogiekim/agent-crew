#!/usr/bin/env bash
# Minimal bash test harness — tracks PASS/FAIL counters per file.
#
# Usage:
#   source "$(dirname "$0")/_lib.bash"
#   it "describes the assertion" cmd args...
#   assert_eq "$expected" "$actual" "context"
#   assert_contains "$haystack" "$needle" "context"
#   assert_exit  "$expected_rc" "$actual_rc" "context"
#   assert_file_exists  "$path"
#   assert_file_absent  "$path"
#   end_report
#
# Resolve repo paths.

# Allow this lib to be sourced from anywhere; resolve repo root relative
# to this file's location.
_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${_LIB_DIR}/../.." && pwd)"
SCRIPTS_DIR="${REPO_ROOT}/core/scripts"
HOOKS_DIR="${REPO_ROOT}/core/hooks"
SETUP_DIR="${REPO_ROOT}/core/setup"

# Per-file counters.
PASS=0
FAIL=0
TESTS_TOTAL=0
FAILED_DETAILS=()

_test_name=""

it() {
  _test_name="$1"
  TESTS_TOTAL=$((TESTS_TOTAL + 1))
}

_pass() {
  PASS=$((PASS + 1))
  printf '  ok %s\n' "${_test_name}"
}

_fail() {
  local detail="$1"
  FAIL=$((FAIL + 1))
  FAILED_DETAILS+=("${_test_name}: ${detail}")
  printf '  NOT ok %s\n      %s\n' "${_test_name}" "${detail}"
}

assert_eq() {
  local expected="$1" actual="$2" context="${3:-}"
  if [ "${expected}" = "${actual}" ]; then
    _pass
  else
    _fail "expected=${expected} actual=${actual} ${context}"
  fi
}

assert_exit() {
  local expected="$1" actual="$2" context="${3:-}"
  if [ "${expected}" = "${actual}" ]; then
    _pass
  else
    _fail "expected exit=${expected} actual=${actual} ${context}"
  fi
}

assert_contains() {
  local haystack="$1" needle="$2" context="${3:-}"
  case "${haystack}" in
    *"${needle}"*) _pass ;;
    *) _fail "needle '${needle}' not found in haystack: ${haystack:0:200} ${context}" ;;
  esac
}

assert_not_contains() {
  local haystack="$1" needle="$2" context="${3:-}"
  case "${haystack}" in
    *"${needle}"*) _fail "needle '${needle}' unexpectedly found in haystack: ${haystack:0:200} ${context}" ;;
    *) _pass ;;
  esac
}

assert_file_exists() {
  local path="$1"
  if [ -e "${path}" ]; then
    _pass
  else
    _fail "file does not exist: ${path}"
  fi
}

assert_file_absent() {
  local path="$1"
  if [ ! -e "${path}" ]; then
    _pass
  else
    _fail "file unexpectedly exists: ${path}"
  fi
}

assert_true() {
  local cond_rc="$1" context="${2:-}"
  if [ "${cond_rc}" -eq 0 ]; then
    _pass
  else
    _fail "expected true (rc=0) got rc=${cond_rc} ${context}"
  fi
}

# Make a tmp dir; track for cleanup.
_TMP_DIRS=()
make_tmp() {
  local d
  d="$(mktemp -d)"
  _TMP_DIRS+=("${d}")
  printf '%s' "${d}"
}

cleanup_tmp() {
  # Tolerate empty array under `set -u`
  if [ "${#_TMP_DIRS[@]:-0}" -gt 0 ]; then
    for d in "${_TMP_DIRS[@]}"; do
      [ -n "${d}" ] && [ -d "${d}" ] && rm -rf "${d}"
    done
  fi
  _TMP_DIRS=()
}

end_report() {
  cleanup_tmp
  echo ""
  echo "--- summary ---"
  printf 'tests=%d  passed=%d  failed=%d\n' \
    "${TESTS_TOTAL}" "${PASS}" "${FAIL}"
  if [ "${FAIL}" -gt 0 ]; then
    echo ""
    echo "failed:"
    for d in "${FAILED_DETAILS[@]}"; do
      echo "  - ${d}"
    done
    exit 1
  fi
  exit 0
}

trap cleanup_tmp EXIT
