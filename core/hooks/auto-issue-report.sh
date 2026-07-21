#!/bin/bash
# Advisory hook wrapper for automatic agent-crew bug/error reporting.
# Never blocks the user's prompt/tool flow; failures are intentionally ignored.

INPUT=$(cat)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
CREW_BIN="${AGENT_CREW_HOME}/bin/crew"
SCRIPT="${AGENT_CREW_HOME}/scripts/auto-issue-reporter.py"

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
    print("1" if data.get("contains_auto_issue_signal") else "0")
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
      (
        if [ -x "${CREW_BIN}" ]; then
          "${CREW_BIN}" report auto < "${_PAYLOAD_PATH}" >/dev/null 2>&1 || true
        elif command -v crew >/dev/null 2>&1; then
          crew report auto < "${_PAYLOAD_PATH}" >/dev/null 2>&1 || true
        elif [ -f "${SCRIPT}" ]; then
          python3 "${SCRIPT}" auto < "${_PAYLOAD_PATH}" >/dev/null 2>&1 || true
        fi
      ) >/dev/null 2>&1 &
      exit 0
    fi
    ;;
esac

# Fast reject the overwhelmingly common no-signal path before starting the
# native crew CLI. Claude runs this hook for every prompt and Bash result, so
# the idle path must stay cheap and independent from Python/CLI startup.
if ! printf '%s' "${INPUT}" | grep -Eiq \
  '(^|[^./[:alnum:]_-])agent[-_[:space:]]?crew([^/[:alnum:]_-]|$)|(^|[^[:alnum:]_])crew[[:space:]]+(run|agent|status|repair|report|update|setup|sync|cost|smm)([^[:alnum:]_]|$)|crew:[[:alpha:]-]+|[$]crew|에이전트[[:space:]]*크루|에이전트크루|supervisor_blocked|blocked_by|STATUS:[[:space:]]*blocked|BLOCKER:'; then
  exit 0
fi

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
