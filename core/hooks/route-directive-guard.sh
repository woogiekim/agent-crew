#!/usr/bin/env bash
# PostToolUse[Agent|multi_agent_v1wait_agent] hook: detect ignored STOP/ROUTE
# auto-route directives (Issue #125 follow-up widens coverage beyond the
# bare "Agent" tool_name to also catch the aliased Codex subagent call).

INPUT=$(cat)

case "${INPUT}" in
  *\"agent_crew_hook_envelope\"*)
    _ENVELOPE_PARSED=$(python3 3<<<"${INPUT}" <<'PYEOF'
import json

with open(3, encoding="utf-8", closefd=False) as payload_stream:
    try:
        data = json.load(payload_stream)
    except Exception:
        data = {}

if data.get("agent_crew_hook_envelope") == 1:
    print("1")
    print("1" if data.get("contains_route_directive_signal") else "0")
    print(data.get("payload_path") or "")
else:
    print("0")
    print("0")
    print("")
PYEOF
)
    _IS_ENVELOPE=$(printf '%s\n' "${_ENVELOPE_PARSED}" | sed -n '1p')
    _HAS_SIGNAL=$(printf '%s\n' "${_ENVELOPE_PARSED}" | sed -n '2p')
    _PAYLOAD_PATH=$(printf '%s\n' "${_ENVELOPE_PARSED}" | sed -n '3p')
    if [ "${_IS_ENVELOPE}" = "1" ]; then
      [ "${_HAS_SIGNAL}" = "1" ] || exit 0
      [ -f "${_PAYLOAD_PATH}" ] || exit 0
      INPUT="$(cat "${_PAYLOAD_PATH}" 2>/dev/null || true)"
    fi
    ;;
esac

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

printf '%s' "${INPUT}" | python3 "${VALIDATOR}" --tool "Agent|multi_agent_v1wait_agent"
