#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HOST="${AGENT_CREW_HOST:-auto}"

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
