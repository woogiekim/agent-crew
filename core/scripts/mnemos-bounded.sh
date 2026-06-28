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

python3 - "${TIMEOUT_SECONDS}" "${MNEMOS_BIN}" "$@" <<'PY'
import subprocess
import sys
import tempfile

timeout = int(sys.argv[1])
command = sys.argv[2:]

with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
    proc = subprocess.Popen(
        command,
        stdout=stdout_file,
        stderr=stderr_file,
    )

    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.terminate()
        except Exception:
            pass

        try:
            proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass

        stdout_file.seek(0)
        stderr_file.seek(0)
        sys.stdout.buffer.write(stdout_file.read())
        sys.stderr.buffer.write(stderr_file.read())
        sys.stderr.write(
            f"mnemos-bounded: timed out after {timeout}s: {' '.join(command)}\n"
        )
        raise SystemExit(124)

    stdout_file.seek(0)
    stderr_file.seek(0)
    sys.stdout.buffer.write(stdout_file.read())
    sys.stderr.buffer.write(stderr_file.read())
    raise SystemExit(rc)
PY
