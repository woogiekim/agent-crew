#!/usr/bin/env bash
# Tests for core/scripts/sync-instructions.sh
#
# Verifies:
#   - MNEMOS_BIN missing → exit 1 with helpful error
#   - --dry-run never mutates files (default mode)
#   - --apply with mocked mnemos rewrites host files
#   - Re-run --apply is a no-op (idempotent)
#   - Marker block surrounded by host content: outside-marker content preserved

set -u
source "$(dirname "$0")/_lib.bash"

SCRIPT="${SCRIPTS_DIR}/sync-instructions.sh"

# --------------------------------------------------------------------------- #
# Helper: create a mock mnemos stub that emits a deterministic rule list      #
# --------------------------------------------------------------------------- #

make_mock_mnemos() {
  local tmp="$1"
  local stub="${tmp}/mnemos"
  cat > "${stub}" <<'EOF'
#!/usr/bin/env bash
# Mock mnemos: list returns one rule line; read returns the rule JSON.
case "$1" in
  list)
    echo "[global] rule:test-rule:"
    ;;
  read)
    if [ "$2" = "rule:test-rule" ]; then
      cat <<'INNER'
{"tags":["instruction-rule"],"content":"---\ntitle: Test Rule\nsection: Test Section\napplies_to: [all]\npriority: 50\n---\nThis is a test rule body.\n"}
INNER
    fi
    ;;
  *)
    ;;
esac
EOF
  chmod +x "${stub}"
  printf '%s' "${stub}"
}

# --------------------------------------------------------------------------- #
# MNEMOS_BIN missing → exit 1                                                 #
# --------------------------------------------------------------------------- #

it "exits 1 when MNEMOS_BIN is not executable"
out=$(MNEMOS_BIN=/nonexistent/no-such-mnemos bash "${SCRIPT}" --dry-run 2>&1)
rc=$?
assert_exit 1 "${rc}"

it "stderr mentions mnemos CLI not found"
assert_contains "${out}" "mnemos CLI not found"

# --------------------------------------------------------------------------- #
# Unknown arg → exit 2                                                        #
# --------------------------------------------------------------------------- #

it "unknown arg → exit 2"
out=$(MNEMOS_BIN=/bin/echo bash "${SCRIPT}" --bogus 2>&1)
rc=$?
assert_exit 2 "${rc}"

# --------------------------------------------------------------------------- #
# --apply with mock mnemos writes host file; --dry-run does not               #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")

# Build a fake CLAUDE_HOME / CODEX_HOME / AGENT_CREW_HOME
CLAUDE_HOME_T="${TMP}/claude-home"
CODEX_HOME_T="${TMP}/codex-home"
AGENT_CREW_HOME_T="${TMP}/agent-crew-home"
mkdir -p "${CLAUDE_HOME_T}" "${CODEX_HOME_T}" "${AGENT_CREW_HOME_T}"

# Seed CLAUDE.md with content OUTSIDE the marker block — must be preserved.
cat > "${CLAUDE_HOME_T}/CLAUDE.md" <<'EOF'
# User custom intro
Personal preferences live here.

# Project rules
EOF
cp "${CLAUDE_HOME_T}/CLAUDE.md" "${TMP}/claude-snapshot-before.md"

it "--dry-run does not modify CLAUDE.md"
MNEMOS_BIN="${MNEMOS}" \
  CLAUDE_HOME="${CLAUDE_HOME_T}" \
  CODEX_HOME="${CODEX_HOME_T}" \
  AGENT_CREW_HOME="${AGENT_CREW_HOME_T}" \
  bash "${SCRIPT}" --dry-run --hosts claude >/dev/null 2>&1
# Exit code may be 0 or 3 (informational diffs); we don't assert on rc here.
diff -q "${CLAUDE_HOME_T}/CLAUDE.md" "${TMP}/claude-snapshot-before.md" >/dev/null
assert_true $? "dry-run preserves file byte-for-byte"

it "--apply writes the marker block into CLAUDE.md"
MNEMOS_BIN="${MNEMOS}" \
  CLAUDE_HOME="${CLAUDE_HOME_T}" \
  CODEX_HOME="${CODEX_HOME_T}" \
  AGENT_CREW_HOME="${AGENT_CREW_HOME_T}" \
  bash "${SCRIPT}" --apply --hosts claude >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

it "--apply added agent-crew-start marker"
content=$(cat "${CLAUDE_HOME_T}/CLAUDE.md")
assert_contains "${content}" "agent-crew-start"

it "--apply added rule body"
assert_contains "${content}" "test rule body"

it "--apply preserved outside-marker user content (intro)"
assert_contains "${content}" "User custom intro"

it "--apply preserved outside-marker user content (Project rules header)"
assert_contains "${content}" "Project rules"

# --------------------------------------------------------------------------- #
# Idempotent --apply re-run                                                   #
# --------------------------------------------------------------------------- #

# Save mtime + content for idempotency comparison.
snapshot=$(cat "${CLAUDE_HOME_T}/CLAUDE.md")

it "second --apply re-run exits 0"
MNEMOS_BIN="${MNEMOS}" \
  CLAUDE_HOME="${CLAUDE_HOME_T}" \
  CODEX_HOME="${CODEX_HOME_T}" \
  AGENT_CREW_HOME="${AGENT_CREW_HOME_T}" \
  bash "${SCRIPT}" --apply --hosts claude >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

it "second --apply: file still has exactly one start marker"
n=$(grep -cFx '<!-- agent-crew-start -->' "${CLAUDE_HOME_T}/CLAUDE.md" \
       2>/dev/null | tr -d '[:space:]')
assert_eq 1 "${n}" "marker-start count"

it "second --apply: file still has exactly one end marker"
n=$(grep -cFx '<!-- agent-crew-end -->' "${CLAUDE_HOME_T}/CLAUDE.md" \
       2>/dev/null | tr -d '[:space:]')
assert_eq 1 "${n}" "marker-end count"

# --------------------------------------------------------------------------- #
# mnemos returns empty → exit 1                                               #
# --------------------------------------------------------------------------- #

EMPTY_MNEMOS="${TMP}/empty-mnemos"
cat > "${EMPTY_MNEMOS}" <<'EOF'
#!/usr/bin/env bash
# Returns nothing for `list`
exit 0
EOF
chmod +x "${EMPTY_MNEMOS}"

it "empty mnemos rule list → exit 1"
MNEMOS_BIN="${EMPTY_MNEMOS}" \
  CLAUDE_HOME="${CLAUDE_HOME_T}" \
  CODEX_HOME="${CODEX_HOME_T}" \
  AGENT_CREW_HOME="${AGENT_CREW_HOME_T}" \
  bash "${SCRIPT}" --apply --hosts claude >/dev/null 2>&1
rc=$?
assert_exit 1 "${rc}"

end_report
