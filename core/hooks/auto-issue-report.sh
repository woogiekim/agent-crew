#!/bin/bash
# Advisory hook wrapper for automatic agent-crew bug/error issue reporting.
# Never blocks the user's prompt/tool flow; failures are intentionally ignored.

INPUT=$(cat)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
SCRIPT="${AGENT_CREW_HOME}/scripts/auto-issue-reporter.py"

if [ ! -f "${SCRIPT}" ]; then
  exit 0
fi

printf '%s' "${INPUT}" | python3 "${SCRIPT}" >/dev/null 2>&1 || true
exit 0
