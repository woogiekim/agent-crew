#!/usr/bin/env bash
# PostToolUse hook — validates ✻ 🧠 notifications against actual mnemos captures.
# Advisory only: always exits 0. mnemos absence = silent no-op.
#
# Capability: hook_system (advertised by adapters/claude/setup.sh).
# Related: core/rules/memory.md — capture notification convention.
# See also: GitHub issue #16.

if [ "$#" -gt 0 ]; then
  TURN_OUTPUT="$1"
else
  TURN_OUTPUT=""
  IFS= read -r -d '' TURN_OUTPUT || true
fi

case "${TURN_OUTPUT}" in
  *\"agent_crew_hook_envelope\"*)
    _ENVELOPE_PARSED=$(python3 3<<<"${TURN_OUTPUT}" <<'PYEOF'
import json
import sys

with open(3, encoding="utf-8", closefd=False) as payload_stream:
    try:
        data = json.load(payload_stream)
    except Exception:
        data = {}

if data.get("agent_crew_hook_envelope") == 1:
    print("1")
    print("1" if data.get("contains_mnemos_capture_notification") else "0")
    print(data.get("payload_path") or "")
else:
    print("0")
    print("0")
    print("")
PYEOF
)
    _IS_ENVELOPE=$(printf '%s\n' "${_ENVELOPE_PARSED}" | sed -n '1p')
    _HAS_NOTIFICATION=$(printf '%s\n' "${_ENVELOPE_PARSED}" | sed -n '2p')
    _PAYLOAD_PATH=$(printf '%s\n' "${_ENVELOPE_PARSED}" | sed -n '3p')
    if [ "${_IS_ENVELOPE}" = "1" ]; then
      [ "${_HAS_NOTIFICATION}" = "1" ] || exit 0
      [ -f "${_PAYLOAD_PATH}" ] || exit 0
      TURN_OUTPUT="$(cat "${_PAYLOAD_PATH}" 2>/dev/null || true)"
    fi
    ;;
esac

# Notification-free output is the overwhelmingly common path. Keep it free
# from Python and mnemos CLI startup.
case "${TURN_OUTPUT}" in
  *"✻"*"🧠"*) ;;
  *) exit 0 ;;
esac

# Graceful degradation — if mnemos is not installed, skip entirely.
command -v mnemos >/dev/null 2>&1 || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_CREW_HOME="${AGENT_CREW_HOME:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
MEMORY_BIN="${AGENT_CREW_HOME}/bin/memory"

mnemos_id_exists() {
  local id="$1"

  if [ -x "${MEMORY_BIN}" ] && "${MEMORY_BIN}" read "${id}" >/dev/null 2>&1; then
    return 0
  fi

  if MNEMOS_BACKEND="${MNEMOS_BACKEND:-default}" mnemos read "${id}" >/dev/null 2>&1; then
    return 0
  fi

  mnemos read "${id}" >/dev/null 2>&1
}

# Use Python for cross-platform regex extraction (macOS BSD grep lacks -P).
# Extracts:
#   NOTIFICATION_COUNT — number of ✻ 🧠 lines
#   NOTIFICATION_IDS   — newline-separated UUIDs from [id: <uuid>] tokens
#   MISSING_ID_COUNT   — notifications missing a [id: <uuid>]
_PARSED=$(python3 3<<<"${TURN_OUTPUT}" <<'PYEOF'
import re, sys

with open(3, encoding="utf-8", closefd=False) as payload_stream:
    text = payload_stream.read()

notification_re = re.compile(r'✻\s+🧠')
id_re = re.compile(r'✻\s+🧠.*?\[id:\s+([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\]')

notifications = notification_re.findall(text)
ids = id_re.findall(text)

notification_count = len(notifications)
id_count = len(ids)
missing_count = notification_count - id_count

print(notification_count)
print(id_count)
print(missing_count)
for i in ids:
    print(i)
PYEOF
)

NOTIFICATION_COUNT=$(printf '%s\n' "${_PARSED}" | sed -n '1p')
ID_COUNT=$(printf '%s\n' "${_PARSED}" | sed -n '2p')
MISSING_ID_COUNT=$(printf '%s\n' "${_PARSED}" | sed -n '3p')
NOTIFICATION_IDS=$(printf '%s\n' "${_PARSED}" | tail -n +4)

# Warn on notifications missing an [id: <uuid>]
if [ "${MISSING_ID_COUNT:-0}" -gt 0 ] 2>/dev/null; then
  printf '[mnemos-guard] WARNING: %d ✻ 🧠 notification(s) missing [id: <uuid>]\n' \
    "${MISSING_ID_COUNT}" >&2
fi

# Verify each ID exists in mnemos
while IFS= read -r ID; do
  [ -z "${ID}" ] && continue
  if ! mnemos_id_exists "${ID}"; then
    printf '[mnemos-guard] WARNING: notification ID %s not found in mnemos\n' "${ID}" >&2
  fi
done <<< "${NOTIFICATION_IDS}"

exit 0  # Always advisory — never block the turn
