#!/usr/bin/env bash
# Shell helpers for collision-safe agent-crew project state resolution.

project_state_helper_script() {
  local candidate
  for candidate in \
    "${ASSET_ROOT:-}/scripts/project_state.py" \
    "${AGENT_CREW_HOME:-${HOME}/.agent-crew}/system/scripts/project_state.py" \
    "${AGENT_CREW_HOME:-${HOME}/.agent-crew}/scripts/project_state.py"; do
    [ -n "${candidate}" ] || continue
    [ -f "${candidate}" ] || continue
    printf '%s\n' "${candidate}"
    return 0
  done
  return 1
}

project_state_resolve() {
  local helper
  helper="$(project_state_helper_script 2>/dev/null || true)"
  if [ -z "${helper}" ]; then
    local root="${PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
    local name
    name="$(basename "${root}")"
    cat <<EOF
export PROJECT_ROOT=$(printf '%q' "${root}")
export PROJECT_NAME=$(printf '%q' "${name}")
export PROJECT_STATE_KEY=$(printf '%q' "${name}")
export STATE_DIR=$(printf '%q' "${AGENT_CREW_HOME:-${HOME}/.agent-crew}/state/${name}")
export LEGACY_STATE_DIR=$(printf '%q' "${AGENT_CREW_HOME:-${HOME}/.agent-crew}/state/${name}")
export PROJECT_STATE_LEGACY_MATCH=unknown
export PROJECT_STATE_MIGRATED=0
EOF
    return 0
  fi

  python3 "${helper}" resolve "$@" --format shell
}

project_state_load() {
  eval "$(project_state_resolve "$@")"
}

project_state_setup_existing() {
  local helper
  helper="$(project_state_helper_script 2>/dev/null || true)"
  [ -n "${helper}" ] || return 2
  python3 "${helper}" setup-existing-state "$@" --format shell
}
