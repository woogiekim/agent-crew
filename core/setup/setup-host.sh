#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HOST="${AGENT_CREW_HOST:-auto}"

# AGENT_CREW_MODE: "install" (default) or "update".
# In update mode, the dispatcher skips no work itself — the copy operations
# in each adapter setup.sh are already idempotent. The flag is exported so
# adapters can log mode-specific output and so future adapters can branch
# on it without contract changes.
AGENT_CREW_MODE="${AGENT_CREW_MODE:-install}"
export AGENT_CREW_MODE

if [ "${AGENT_CREW_MODE}" = "update" ]; then
  printf 'MODE: update\n'
fi

run_adapter() {
  local host="$1"
  local adapter="${AGENT_CREW_HOME}/adapters/${host}/setup.sh"

  if [ ! -x "${adapter}" ]; then
    printf 'Unsupported host adapter: %s\n' "${host}" >&2
    return 1
  fi

  bash "${adapter}" "${PROJECT_ROOT}" || true
}

# Installation-presence guard: return 0 if an adapter has been previously
# installed on this machine, 1 if it has never been set up.  Adapters that
# pass this check are eligible to be re-run during crew:update fan-out.
is_installed() {
  local host="$1"
  case "${host}" in
    claude)
      [ -d "${CLAUDE_DIR:-${HOME}/.claude}/agent-crew" ]
      ;;
    codex)
      [ -d "${CODEX_HOME:-${HOME}/.codex}/skills/agent-crew" ]
      ;;
    generic)
      # Generic is always project-local; treat as always eligible.
      return 0
      ;;
    *)
      # Unknown adapter — allow through so future adapters work automatically.
      return 0
      ;;
  esac
}

if [ "${HOST}" != "auto" ]; then
  run_adapter "${HOST}"
  exit $?
fi

# Fan-out: iterate all detected adapters, run each one that is installed.
# Unlike the previous exec-based dispatch, this loop does NOT stop at the
# first match — all adapters whose detect.sh succeeds and whose installation
# directory exists are updated in sequence.
detected_any=0
for detect_script in "${AGENT_CREW_HOME}"/adapters/*/detect.sh; do
  [ -x "${detect_script}" ] || continue
  if "${detect_script}" "${PROJECT_ROOT}" 2>/dev/null; then
    host_dir="$(dirname "${detect_script}")"
    host_name="$(basename "${host_dir}")"
    # Skip generic here; it is handled as the unconditional fallback below.
    [ "${host_name}" = "generic" ] && continue
    if is_installed "${host_name}"; then
      run_adapter "${host_name}"
      detected_any=1
    else
      printf 'Skipping %s adapter (not installed on this machine)\n' "${host_name}"
    fi
  fi
done

# Always run the generic adapter as a fallback so project-local paths are
# refreshed regardless of which named host was detected.
run_adapter "generic"
