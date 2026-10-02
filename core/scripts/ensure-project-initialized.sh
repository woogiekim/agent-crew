#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PROJECT_STATE_SCRIPT="${AGENT_CREW_HOME}/scripts/project_state.py"

if [ ! -f "${PROJECT_STATE_SCRIPT}" ]; then
  PROJECT_STATE_SCRIPT="${AGENT_CREW_HOME}/system/scripts/project_state.py"
fi

# 전역 설치를 재사용하며 프로젝트에는 런타임 상태만 만든다.
RESOLVED_STATE=$(python3 "${PROJECT_STATE_SCRIPT}" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --ensure \
  --prefer-existing-legacy \
  --format shell)
eval "${RESOLVED_STATE}"
mkdir -p "${STATE_DIR}/tasks"
