#!/usr/bin/env bash
# PostToolUse[Agent] hook: detect ignored STOP/ROUTE auto-route directives.

INPUT=$(cat)

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
VALIDATOR=""
for candidate in \
  "${AGENT_CREW_HOME}/scripts/check-route-directive-compliance.py" \
  "${AGENT_CREW_HOME}/system/scripts/check-route-directive-compliance.py"; do
  if [ -f "${candidate}" ]; then
    VALIDATOR="${candidate}"
    break
  fi
done

if [ -z "${VALIDATOR}" ]; then
  exit 0
fi

printf '%s' "${INPUT}" | python3 "${VALIDATOR}" --tool Agent
