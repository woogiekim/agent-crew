#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HOST="${AGENT_CREW_HOST:-auto}"

# AGENT_CREW_MODE: "install" (default) or "update".
# The dispatcher selects exactly one project host adapter. Global update fan-out
# is handled by update-global-adapters.sh; project setup must not refresh every
# installed adapter or materialize the generic mirror after a native adapter.
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

if [ -n "${ACTIVE_HOST}" ]; then
  run_adapter "${ACTIVE_HOST}"
  exit $?
fi

run_adapter "generic"
