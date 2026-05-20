#!/usr/bin/env bash
# tests/shell/test_setup_host_fan_out.bash
#
# Verify that core/setup/setup-host.sh fan-out loop uses is_installed()
# filesystem checks rather than detect.sh runtime detection, so all installed
# adapter paths are refreshed from any host environment.
#
# Issue #45: crew:update must refresh all installed adapter paths regardless of
# which host is currently running.

set -u  # do NOT set -e — failed assertions must keep running

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# Build a minimal fake AGENT_CREW_HOME with stub adapters.
#
# Layout:
#   <acHome>/adapters/claude/detect.sh    — exits 1 always (not the current host)
#   <acHome>/adapters/claude/setup.sh     — records invocation in <acHome>/ran
#   <acHome>/adapters/codex/detect.sh     — exits 1 always (not the current host)
#   <acHome>/adapters/codex/setup.sh      — records invocation in <acHome>/ran
#   <acHome>/adapters/generic/detect.sh   — exits 0 (generic always passes)
#   <acHome>/adapters/generic/setup.sh    — records invocation in <acHome>/ran
#
# Both claude and codex are "installed" by creating their installation dirs:
#   <acHome>/claude-inst/agent-crew       — stands in for ~/.claude/agent-crew
#   <acHome>/codex-inst/skills/agent-crew — stands in for ~/.codex/skills/agent-crew
#
# CLAUDE_DIR and CODEX_HOME are exported to point at the fake install roots.

make_acHome() {
  local acHome
  acHome="$(make_tmp)"
  local ran="${acHome}/ran"

  # claude adapter
  mkdir -p "${acHome}/adapters/claude"
  cat >"${acHome}/adapters/claude/detect.sh" <<'SH'
#!/usr/bin/env bash
# Always fail — simulate not running inside Claude Code
exit 1
SH
  chmod +x "${acHome}/adapters/claude/detect.sh"

  cat >"${acHome}/adapters/claude/setup.sh" <<SH
#!/usr/bin/env bash
echo "claude" >> "${ran}"
if [ "\${AGENT_CREW_WRITE_CAPABILITIES:-1}" != "0" ]; then
  echo "claude" > "${acHome}/capabilities-host"
fi
SH
  chmod +x "${acHome}/adapters/claude/setup.sh"

  # codex adapter
  mkdir -p "${acHome}/adapters/codex"
  cat >"${acHome}/adapters/codex/detect.sh" <<'SH'
#!/usr/bin/env bash
# Always fail — simulate not running inside Codex
exit 1
SH
  chmod +x "${acHome}/adapters/codex/detect.sh"

  cat >"${acHome}/adapters/codex/setup.sh" <<SH
#!/usr/bin/env bash
echo "codex" >> "${ran}"
if [ "\${AGENT_CREW_WRITE_CAPABILITIES:-1}" != "0" ]; then
  echo "codex" > "${acHome}/capabilities-host"
fi
SH
  chmod +x "${acHome}/adapters/codex/setup.sh"

  # generic adapter
  mkdir -p "${acHome}/adapters/generic"
  cat >"${acHome}/adapters/generic/detect.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  chmod +x "${acHome}/adapters/generic/detect.sh"

  cat >"${acHome}/adapters/generic/setup.sh" <<SH
#!/usr/bin/env bash
echo "generic" >> "${ran}"
SH
  chmod +x "${acHome}/adapters/generic/setup.sh"

  echo "${acHome}"
}

# Run setup-host.sh in update mode with a custom AGENT_CREW_HOME.
# CLAUDE_DIR and CODEX_HOME override the installation-presence paths that
# is_installed() checks inside setup-host.sh.
run_setup_host() {
  local acHome="$1"
  local claudeDir="$2"
  local codexHome="$3"

  AGENT_CREW_HOME="${acHome}" \
  CLAUDE_DIR="${claudeDir}" \
  CODEX_HOME="${codexHome}" \
  AGENT_CREW_MODE=update \
    bash "${SETUP_DIR}/setup-host.sh" "$(make_tmp)" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Test: both claude and codex installed — both must be refreshed even when
#       neither detect.sh succeeds (simulates running from a third host).
# ---------------------------------------------------------------------------

TMP=$(make_tmp)
ACHOME=$(make_acHome)
RAN="${ACHOME}/ran"

# Create fake installation directories for claude and codex.
CLAUDE_INST_DIR="${TMP}/claude-inst"
CODEX_INST_DIR="${TMP}/codex-inst"
mkdir -p "${CLAUDE_INST_DIR}/agent-crew"
mkdir -p "${CODEX_INST_DIR}/skills/agent-crew"

run_setup_host "${ACHOME}" "${CLAUDE_INST_DIR}" "${CODEX_INST_DIR}"

it "fan-out runs claude adapter when claude is installed (detect.sh exit=1)"
RAN_CONTENTS=$(cat "${RAN}" 2>/dev/null || echo "")
assert_contains "${RAN_CONTENTS}" "claude"

it "fan-out runs codex adapter when codex is installed (detect.sh exit=1)"
assert_contains "${RAN_CONTENTS}" "codex"

it "fan-out always runs generic adapter"
assert_contains "${RAN_CONTENTS}" "generic"

# ---------------------------------------------------------------------------
# Test: only claude installed — only claude + generic should run.
# ---------------------------------------------------------------------------

TMP2=$(make_tmp)
ACHOME2=$(make_acHome)
RAN2="${ACHOME2}/ran"

CLAUDE_INST2="${TMP2}/claude-inst"
mkdir -p "${CLAUDE_INST2}/agent-crew"
# codex NOT installed (CODEX_HOME points to non-existent dir)
CODEX_INST2="${TMP2}/codex-inst-absent"

run_setup_host "${ACHOME2}" "${CLAUDE_INST2}" "${CODEX_INST2}"

it "fan-out runs claude adapter when only claude is installed"
RAN2_CONTENTS=$(cat "${RAN2}" 2>/dev/null || echo "")
assert_contains "${RAN2_CONTENTS}" "claude"

it "fan-out skips codex adapter when codex is not installed"
assert_not_contains "${RAN2_CONTENTS}" "codex"

it "fan-out always runs generic adapter (only claude installed case)"
assert_contains "${RAN2_CONTENTS}" "generic"

# ---------------------------------------------------------------------------
# Test: only codex installed — only codex + generic should run.
# ---------------------------------------------------------------------------

TMP3=$(make_tmp)
ACHOME3=$(make_acHome)
RAN3="${ACHOME3}/ran"

# claude NOT installed
CLAUDE_INST3="${TMP3}/claude-inst-absent"
CODEX_INST3="${TMP3}/codex-inst"
mkdir -p "${CODEX_INST3}/skills/agent-crew"

run_setup_host "${ACHOME3}" "${CLAUDE_INST3}" "${CODEX_INST3}"

it "fan-out skips claude adapter when claude is not installed"
RAN3_CONTENTS=$(cat "${RAN3}" 2>/dev/null || echo "")
assert_not_contains "${RAN3_CONTENTS}" "claude"

it "fan-out runs codex adapter when only codex is installed"
assert_contains "${RAN3_CONTENTS}" "codex"

it "fan-out always runs generic adapter (only codex installed case)"
assert_contains "${RAN3_CONTENTS}" "generic"

# ---------------------------------------------------------------------------
# Test: neither installed — only generic should run.
# ---------------------------------------------------------------------------

TMP4=$(make_tmp)
ACHOME4=$(make_acHome)
RAN4="${ACHOME4}/ran"

CLAUDE_INST4="${TMP4}/claude-absent"
CODEX_INST4="${TMP4}/codex-absent"

run_setup_host "${ACHOME4}" "${CLAUDE_INST4}" "${CODEX_INST4}"

it "fan-out skips claude when neither adapter is installed"
RAN4_CONTENTS=$(cat "${RAN4}" 2>/dev/null || echo "")
assert_not_contains "${RAN4_CONTENTS}" "claude"

it "fan-out skips codex when neither adapter is installed"
assert_not_contains "${RAN4_CONTENTS}" "codex"

it "fan-out runs generic even when no named adapter is installed"
assert_contains "${RAN4_CONTENTS}" "generic"

# ---------------------------------------------------------------------------
# Test: explicit HOST=auto does not break fan-out (default path).
# ---------------------------------------------------------------------------

TMP5=$(make_tmp)
ACHOME5=$(make_acHome)
RAN5="${ACHOME5}/ran"

CLAUDE_INST5="${TMP5}/claude-inst"
CODEX_INST5="${TMP5}/codex-inst"
mkdir -p "${CLAUDE_INST5}/agent-crew"
mkdir -p "${CODEX_INST5}/skills/agent-crew"

AGENT_CREW_HOME="${ACHOME5}" \
CLAUDE_DIR="${CLAUDE_INST5}" \
CODEX_HOME="${CODEX_INST5}" \
AGENT_CREW_MODE=update \
AGENT_CREW_HOST=auto \
  bash "${SETUP_DIR}/setup-host.sh" "$(make_tmp)" 2>/dev/null

RAN5_CONTENTS=$(cat "${RAN5}" 2>/dev/null || echo "")
it "explicit HOST=auto still refreshes claude adapter"
assert_contains "${RAN5_CONTENTS}" "claude"

it "explicit HOST=auto still refreshes codex adapter"
assert_contains "${RAN5_CONTENTS}" "codex"

it "explicit HOST=auto still refreshes generic adapter"
assert_contains "${RAN5_CONTENTS}" "generic"

# ---------------------------------------------------------------------------
# Test: update fan-out refreshes installed adapters but writes capabilities
#       only from the active host adapter.
# ---------------------------------------------------------------------------

TMP6=$(make_tmp)
ACHOME6=$(make_acHome)
RAN6="${ACHOME6}/ran"

CLAUDE_INST6="${TMP6}/claude-inst"
CODEX_INST6="${TMP6}/codex-inst"
mkdir -p "${CLAUDE_INST6}/agent-crew"
mkdir -p "${CODEX_INST6}/skills/agent-crew"

cat >"${ACHOME6}/adapters/claude/detect.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${ACHOME6}/adapters/claude/detect.sh"

AGENT_CREW_HOME="${ACHOME6}" \
CLAUDE_DIR="${CLAUDE_INST6}" \
CODEX_HOME="${CODEX_INST6}" \
AGENT_CREW_MODE=update \
AGENT_CREW_HOST=auto \
  bash "${SETUP_DIR}/setup-host.sh" "$(make_tmp)" 2>/dev/null

RAN6_CONTENTS=$(cat "${RAN6}" 2>/dev/null || echo "")
it "active-host capability test still refreshes claude"
assert_contains "${RAN6_CONTENTS}" "claude"

it "active-host capability test still refreshes codex"
assert_contains "${RAN6_CONTENTS}" "codex"

it "update fan-out writes capabilities from active claude only"
CAP_HOST=$(cat "${ACHOME6}/capabilities-host" 2>/dev/null || echo "")
assert_eq "claude" "${CAP_HOST}"

end_report
