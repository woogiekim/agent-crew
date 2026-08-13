#!/usr/bin/env bash
# PostToolUse[Agent] hook: forbid free-text approval prompts.
#
# Capability: hook_system (advertised by adapters/claude/setup.sh).
# Contract documented in core/rules/capabilities/hook-system.md.
# Validator: core/scripts/check-plaintext-approval.py.
#
# This hook is a thin shell wrapper around the provider-neutral
# validator. It forwards the host's hook-payload JSON on stdin and
# preserves the validator's exit code so the host can surface the
# stderr message to the model (claude PostToolUse exit 2 → message
# fed back).

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
. "${HOOK_DIR}/read-hook-input.sh"
INPUT="$(read_agent_crew_hook_input || true)"

# Resolve the validator path. Prefer ${AGENT_CREW_HOME}/scripts/ over
# system/scripts/ (compat-alias parity with cost-tracker.sh / direct-edit-guard.sh).
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
VALIDATOR=""
for candidate in \
  "${AGENT_CREW_HOME}/scripts/check-plaintext-approval.py" \
  "${AGENT_CREW_HOME}/system/scripts/check-plaintext-approval.py"; do
  if [ -f "${candidate}" ]; then
    VALIDATOR="${candidate}"
    break
  fi
done

# Absence: validator not installed — silently no-op.
if [ -z "${VALIDATOR}" ]; then
  exit 0
fi

printf '%s' "${INPUT}" | python3 "${VALIDATOR}" --tool Agent
