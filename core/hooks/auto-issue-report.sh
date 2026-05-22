#!/bin/bash
# Advisory hook wrapper for automatic agent-crew bug/error reporting.
# Never blocks the user's prompt/tool flow; failures are intentionally ignored.

INPUT=$(cat)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
CREW_BIN="${AGENT_CREW_HOME}/bin/crew"
SCRIPT="${AGENT_CREW_HOME}/scripts/auto-issue-reporter.py"

if [ -x "${CREW_BIN}" ]; then
  printf '%s' "${INPUT}" | "${CREW_BIN}" report auto >/dev/null 2>&1 || true
  exit 0
fi

if command -v crew >/dev/null 2>&1; then
  printf '%s' "${INPUT}" | crew report auto >/dev/null 2>&1 || true
  exit 0
fi

if [ -f "${SCRIPT}" ]; then
  printf '%s' "${INPUT}" | python3 "${SCRIPT}" auto >/dev/null 2>&1 || true
fi

exit 0
