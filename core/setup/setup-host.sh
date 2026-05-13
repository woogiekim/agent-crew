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

dispatch_adapter() {
  local host="$1"
  local adapter="${AGENT_CREW_HOME}/adapters/${host}/setup.sh"

  if [ ! -x "${adapter}" ]; then
    printf 'Unsupported host adapter: %s\n' "${host}" >&2
    exit 1
  fi

  exec "${adapter}" "${PROJECT_ROOT}"
}

if [ "${HOST}" != "auto" ]; then
  dispatch_adapter "${HOST}"
fi

for detect_script in "${AGENT_CREW_HOME}"/adapters/*/detect.sh; do
  [ -x "${detect_script}" ] || continue
  if "${detect_script}" "${PROJECT_ROOT}"; then
    host_dir="$(dirname "${detect_script}")"
    dispatch_adapter "$(basename "${host_dir}")"
  fi
done

dispatch_adapter "generic"
