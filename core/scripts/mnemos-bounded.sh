#!/usr/bin/env bash
# mnemos-bounded.sh — run one mnemos CLI command with a hard wall-clock bound.
#
# Inputs:
#   argv            mnemos subcommand and arguments, for example:
#                     bash core/scripts/mnemos-bounded.sh search agent-crew
#   MNEMOS_BIN      path to mnemos CLI (default: ~/.local/bin/mnemos, then PATH)
#   AGENT_CREW_MNEMOS_TIMEOUT_SECONDS
#                   positive integer timeout in seconds (default: 8)
#   AGENT_CREW_MNEMOS_POLL_INTERVAL_SECONDS
#                   polling interval in seconds (default: 0.1)
#
# Outputs:
#   stdout/stderr   forwarded from mnemos on success/failure before timeout;
#                   timeout message on stderr if the command exceeds the bound.
#
# Exit codes:
#   mnemos rc       command completed before the timeout
#   124             command timed out and was killed
#   2               usage/configuration error
#
# This script deliberately does not use GNU timeout/gtimeout so it behaves the
# same on macOS, Linux, and minimal CI images.

set -u

usage() {
  cat <<'EOF'
usage: mnemos-bounded.sh <mnemos-subcommand> [args...]

Run mnemos with a hard timeout.

Environment:
  MNEMOS_BIN                         path to mnemos CLI
  AGENT_CREW_MNEMOS_TIMEOUT_SECONDS  timeout seconds (default: 8)
  AGENT_CREW_MNEMOS_POLL_INTERVAL_SECONDS
                                      poll interval seconds (default: 0.1)
EOF
}

if [ "${1:-}" = "--help" ] || [ $# -eq 0 ]; then
  usage
  [ $# -eq 0 ] && exit 2 || exit 0
fi

TIMEOUT_SECONDS="${AGENT_CREW_MNEMOS_TIMEOUT_SECONDS:-8}"
POLL_INTERVAL_SECONDS="${AGENT_CREW_MNEMOS_POLL_INTERVAL_SECONDS:-0.1}"
case "${TIMEOUT_SECONDS}" in
  ''|*[!0-9]*)
    printf 'mnemos-bounded: timeout must be a positive integer, got %s\n' "${TIMEOUT_SECONDS}" >&2
    exit 2
    ;;
  0)
    printf 'mnemos-bounded: timeout must be greater than zero\n' >&2
    exit 2
    ;;
esac

case "${POLL_INTERVAL_SECONDS}" in
  ''|*[!0-9.]*)
    printf 'mnemos-bounded: poll interval must be numeric, got %s\n' "${POLL_INTERVAL_SECONDS}" >&2
    exit 2
    ;;
esac

MNEMOS_BIN="${MNEMOS_BIN:-${HOME}/.local/bin/mnemos}"
if [ ! -x "${MNEMOS_BIN}" ]; then
  MNEMOS_PATH="$(command -v "${MNEMOS_BIN}" 2>/dev/null || true)"
  if [ -n "${MNEMOS_PATH}" ]; then
    MNEMOS_BIN="${MNEMOS_PATH}"
  else
    printf 'mnemos-bounded: mnemos CLI not found or not executable: %s\n' "${MNEMOS_BIN}" >&2
    exit 2
  fi
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

OUT_FILE="${TMP_DIR}/stdout"
ERR_FILE="${TMP_DIR}/stderr"
RC_FILE="${TMP_DIR}/rc"

"${MNEMOS_BIN}" "$@" >"${OUT_FILE}" 2>"${ERR_FILE}" &
PID=$!
START_EPOCH="$(date +%s)"

while kill -0 "${PID}" 2>/dev/null; do
  NOW_EPOCH="$(date +%s)"
  ELAPSED=$((NOW_EPOCH - START_EPOCH))
  if [ "${ELAPSED}" -ge "${TIMEOUT_SECONDS}" ]; then
    kill "${PID}" 2>/dev/null || true
    sleep 1
    kill -9 "${PID}" 2>/dev/null || true
    wait "${PID}" 2>/dev/null || true
    cat "${OUT_FILE}" 2>/dev/null || true
    cat "${ERR_FILE}" >&2 2>/dev/null || true
    printf 'mnemos-bounded: timed out after %ss: %s %s\n' \
      "${TIMEOUT_SECONDS}" "${MNEMOS_BIN}" "$*" >&2
    exit 124
  fi
  sleep "${POLL_INTERVAL_SECONDS}"
done

wait "${PID}"
RC=$?
printf '%s\n' "${RC}" >"${RC_FILE}"

cat "${OUT_FILE}" 2>/dev/null || true
cat "${ERR_FILE}" >&2 2>/dev/null || true
exit "${RC}"
