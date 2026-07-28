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

detect_active_host() {
  local host="$1"
  local detect="${AGENT_CREW_HOME}/adapters/${host}/detect.sh"
  [ -x "${detect}" ] || return 1
  "${detect}" >/dev/null 2>&1
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
      [ -d "${CODEX_HOME:-${HOME}/.codex}/skills/crew:run" ] \
        || [ -d "${CODEX_HOME:-${HOME}/.codex}/skills/crew:setup" ] \
        || [ -d "${CODEX_HOME:-${HOME}/.codex}/agent-crew" ]
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

ACTIVE_HOST=""
for candidate in claude codex; do
  if detect_active_host "${candidate}"; then
    ACTIVE_HOST="${candidate}"
    break
  fi
done

# Fan-out: iterate all known adapter directories and run each one that is
# installed on this machine (filesystem check via is_installed()).  This
# replaces the previous detect.sh-gated loop so that all installed adapters
# are refreshed regardless of which host is currently running.  detect.sh
# keeps its role in crew:setup for runtime adapter selection; it is no longer
# load-bearing for the update fan-out path.
detected_any=0
for adapter_dir in "${AGENT_CREW_HOME}"/adapters/*/; do
  [ -d "${adapter_dir}" ] || continue
  host_name="$(basename "${adapter_dir}")"
  # Skip generic here; it is handled as the unconditional fallback below.
  [ "${host_name}" = "generic" ] && continue
  if [ "${host_name}" = "${ACTIVE_HOST}" ] || is_installed "${host_name}"; then
    if [ "${AGENT_CREW_MODE}" = "update" ] && [ "${host_name}" != "${ACTIVE_HOST}" ]; then
      AGENT_CREW_WRITE_CAPABILITIES=0 run_adapter "${host_name}"
    else
      run_adapter "${host_name}"
    fi
    detected_any=1
  else
    printf 'Skipping %s adapter (not installed on this machine)\n' "${host_name}"
  fi
done

# Always run the generic adapter as a fallback so project-local paths are
# refreshed regardless of which named host was detected.
run_adapter "generic"
