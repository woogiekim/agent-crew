#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PROJECT_STATE_SCRIPT="${AGENT_CREW_HOME}/scripts/project_state.py"

if [ ! -f "${PROJECT_STATE_SCRIPT}" ]; then
  PROJECT_STATE_SCRIPT="${AGENT_CREW_HOME}/system/scripts/project_state.py"
fi

eval "$(python3 "${PROJECT_STATE_SCRIPT}" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --prefer-existing-legacy \
  --format shell)"

CAPABILITIES_FILE="${STATE_DIR}/capabilities.json"
if [ -f "${CAPABILITIES_FILE}" ]; then
  exit 0
fi

if [ -e "${STATE_DIR}" ]; then
  printf 'Error: Project '\''%s'\'' has partial or damaged agent-crew state.\nRun crew:setup to recover the workspace.\n' \
    "${PROJECT_NAME}" >&2
  exit 1
fi

LOCK_DIR="${STATE_DIR}.initialize.lock"
mkdir -p "$(dirname "${STATE_DIR}")"

if mkdir "${LOCK_DIR}" 2>/dev/null; then
  cleanup_lock() {
    rmdir "${LOCK_DIR}" 2>/dev/null || true
  }
  trap cleanup_lock EXIT

  bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "${PROJECT_ROOT}"

  eval "$(python3 "${PROJECT_STATE_SCRIPT}" resolve \
    --agent-crew-home "${AGENT_CREW_HOME}" \
    --project-root "${PROJECT_ROOT}" \
    --ensure \
    --migrate-legacy \
    --format shell)"
  mkdir -p "${STATE_DIR}/tasks"

  if [ -x "${AGENT_CREW_HOME}/setup/seed-skill-templates.sh" ]; then
    AGENT_CREW_SEED_TAG="crew:run-auto-init" \
      bash "${AGENT_CREW_HOME}/setup/seed-skill-templates.sh"
  fi
else
  for _attempt in $(seq 1 100); do
    [ -f "${CAPABILITIES_FILE}" ] && break
    sleep 0.05
  done
fi

if [ ! -f "${CAPABILITIES_FILE}" ]; then
  printf 'Error: Project '\''%s'\'' could not be initialized automatically.\nRun crew:setup to recover the workspace.\n' \
    "${PROJECT_NAME}" >&2
  exit 1
fi

printf 'AUTO_INIT: project=%s state=%s\n' "${PROJECT_NAME}" "${STATE_DIR}"
