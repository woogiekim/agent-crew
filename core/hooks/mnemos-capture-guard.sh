#!/usr/bin/env bash
# PostToolUse hook — validates ✻ 🧠 notifications against actual mnemos captures.
# Advisory only: always exits 0. mnemos absence = silent no-op.
#
# Capability: hook_system (advertised by adapters/claude/setup.sh).
# Related: core/rules/memory.md — capture notification convention.
# See also: GitHub issue #16.

# Graceful degradation — if mnemos is not installed, skip entirely.
command -v mnemos >/dev/null 2>&1 || exit 0

TURN_OUTPUT="${1:-}"
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
_PARSED=$(python3 - <<PYEOF
import re, sys

text = """${TURN_OUTPUT}"""

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
