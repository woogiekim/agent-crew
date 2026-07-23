#!/usr/bin/env bash
# Tests for core/hooks/mnemos-capture-guard.sh
# Covers all 7 acceptance criteria from GitHub issue #16.

set -u  # do NOT set -e — failed assertions must keep running

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

HOOK="${HOOKS_DIR}/mnemos-capture-guard.sh"

# --------------------------------------------------------------------------- #
# Helper: run hook with given stdin-style argument, capture stderr            #
# --------------------------------------------------------------------------- #

run_hook() {
  local input="$1"
  bash "${HOOK}" "${input}" 2>&1
}

run_hook_rc() {
  local input="$1"
  bash "${HOOK}" "${input}" >/dev/null 2>&1
  echo $?
}

# --------------------------------------------------------------------------- #
# AC1: Notification-free input exits before dependency startup                #
# --------------------------------------------------------------------------- #

it "AC1: hook has a notification fast-reject before command -v mnemos"
FAST_REJECT_LINE=$(grep -n '^[[:space:]]*\*"✻"\*"🧠"\*)' "${HOOK}" | cut -d: -f1 | head -n 1)
MNEMOS_GUARD_LINE=$(grep -n '^[[:space:]]*command -v mnemos' "${HOOK}" | cut -d: -f1 | head -n 1)
if [ -n "${FAST_REJECT_LINE}" ] && [ -n "${MNEMOS_GUARD_LINE}" ] \
  && [ "${FAST_REJECT_LINE}" -lt "${MNEMOS_GUARD_LINE}" ]; then
  _pass
else
  _fail "notification fast-reject must precede mnemos lookup"
fi

# --------------------------------------------------------------------------- #
# AC2: Hook always exits 0 (never blocking)                                   #
# --------------------------------------------------------------------------- #

it "AC2: hook exits 0 with empty turn output"
rc=$(run_hook_rc "")
assert_exit 0 "${rc}" "empty input exit"

it "AC2: hook exits 0 with notification missing id"
rc=$(run_hook_rc "✻ 🧠 some capture (session)")
assert_exit 0 "${rc}" "missing-id notification exit"

it "AC2: hook exits 0 with valid notification"
rc=$(run_hook_rc "✻ 🧠 some capture [id: 00000000-0000-0000-0000-000000000000]")
assert_exit 0 "${rc}" "valid-id notification exit"

it "AC2: hook exits 0 with no notifications at all"
rc=$(run_hook_rc "Normal response with no memory captures")
assert_exit 0 "${rc}" "no notification exit"

# --------------------------------------------------------------------------- #
# AC3: ✻ 🧠 line without [id: <uuid>] triggers a stderr warning              #
# --------------------------------------------------------------------------- #

it "AC3: notification without id triggers WARNING on stderr"
output=$(run_hook "✻ 🧠 a capture without id (session)")
assert_contains "${output}" "WARNING" "missing-id warning"
assert_contains "${output}" "missing [id: <uuid>]" "missing-id warning text"

it "AC3: PostToolUse stdin payload is inspected"
output=$(printf '%s' '✻ 🧠 stdin capture without id' | bash "${HOOK}" 2>&1)
assert_contains "${output}" "WARNING" "stdin missing-id warning"

it "AC3: warning counts missing notifications correctly (2 missing)"
output=$(run_hook "$(printf '✻ 🧠 first (session)\n✻ 🧠 second (session)')")
assert_contains "${output}" "2 ✻ 🧠 notification(s) missing [id: <uuid>]" "count=2 missing-id warning"

# --------------------------------------------------------------------------- #
# AC4: UUID not found in mnemos triggers a stderr warning                     #
# --------------------------------------------------------------------------- #

it "AC4: notification with non-existent UUID triggers WARNING"
FAKE_UUID="00000000-0000-0000-0000-000000000000"
# Only run if mnemos is available
if command -v mnemos >/dev/null 2>&1; then
  output=$(run_hook "✻ 🧠 test [id: ${FAKE_UUID}]")
  assert_contains "${output}" "WARNING" "non-existent-id warning"
  assert_contains "${output}" "${FAKE_UUID}" "uuid in warning"
else
  # mnemos absent — hook exits silently (tested in AC6)
  _pass
fi

# --------------------------------------------------------------------------- #
# AC5: Valid UUID that exists in mnemos passes silently                       #
# --------------------------------------------------------------------------- #

it "AC5: notification with valid existing UUID produces no warning"
if command -v mnemos >/dev/null 2>&1; then
  # Capture a real item to get a valid UUID
  CAPTURE_OUT=$(MNEMOS_BACKEND=default mnemos capture --content "mnemos-capture-guard test item" --layer ephemeral 2>&1)
  # Use Python for cross-platform UUID extraction (macOS grep lacks -P)
  REAL_UUID=$(printf '%s' "${CAPTURE_OUT}" | python3 -c "
import re, sys
text = sys.stdin.read()
m = re.search(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', text)
print(m.group(0) if m else '')
" 2>/dev/null || echo "")
  if [ -n "${REAL_UUID}" ]; then
    output=$(run_hook "✻ 🧠 test capture [id: ${REAL_UUID}]")
    assert_not_contains "${output}" "WARNING" "valid uuid no warning"
    # Clean up the test capture
    MNEMOS_BACKEND=default mnemos archive "${REAL_UUID}" >/dev/null 2>&1 || true
  else
    # Could not extract UUID from capture output — skip AC5 (advisory test)
    it "AC5: skipped — could not extract UUID from mnemos capture output"
    _pass
  fi
else
  # mnemos absent — skip AC5
  _pass
fi

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "read" ] && [ "${MNEMOS_BACKEND:-}" = "default" ] \
  && [ "${2:-}" = "11111111-1111-1111-1111-111111111111" ]; then
  echo "found"
  exit 0
fi
exit 1
SH
chmod +x "${TMP}/mnemos"

it "AC5: guard validates capture IDs through the default support backend"
output=$(PATH="${TMP}:${PATH}" MNEMOS_BIN="${TMP}/mnemos" \
  bash "${HOOK}" "✻ 🧠 test capture [id: 11111111-1111-1111-1111-111111111111]" 2>&1)
assert_not_contains "${output}" "WARNING" "default backend read no warning"

# --------------------------------------------------------------------------- #
# AC6: With mnemos absent — hook produces no output and exits 0               #
# --------------------------------------------------------------------------- #

it "AC6: with mnemos absent, hook exits 0 and produces no output"
# Override mnemos to be absent: use a minimal PATH that excludes all real mnemos locations.
# We build a clean PATH containing only standard system bins (no ~/.local/bin, no user bins).
CLEAN_PATH="/usr/bin:/bin:/usr/sbin:/sbin"
FAKE_OUTPUT=$(PATH="${CLEAN_PATH}" bash "${HOOK}" "✻ 🧠 test [id: 12345678-1234-1234-1234-123456789abc]" 2>&1)
FAKE_RC=$(PATH="${CLEAN_PATH}" bash "${HOOK}" "✻ 🧠 test [id: 12345678-1234-1234-1234-123456789abc]" >/dev/null 2>&1; echo $?)
assert_exit 0 "${FAKE_RC}" "mnemos-absent exit"
assert_eq "" "${FAKE_OUTPUT}" "mnemos-absent no output"

# --------------------------------------------------------------------------- #
# AC7: Hook is registered in ~/.claude/settings.json under hooks.PostToolUse  #
# --------------------------------------------------------------------------- #

it "AC7: hook registered in adapters/claude/setup.sh"
SETUP_CONTENT=$(cat "${REPO_ROOT}/adapters/claude/setup.sh")
assert_contains "${SETUP_CONTENT}" "mnemos-capture-guard.sh" "setup.sh registers guard"
assert_contains "${SETUP_CONTENT}" "PostToolUse" "setup.sh uses PostToolUse"

it "AC7: hook registered in install.sh"
INSTALL_CONTENT=$(cat "${REPO_ROOT}/install.sh")
assert_contains "${INSTALL_CONTENT}" "mnemos-capture-guard.sh" "install.sh registers guard"

# --------------------------------------------------------------------------- #
# Summary                                                                     #
# --------------------------------------------------------------------------- #

end_report
