#!/usr/bin/env bash
# tests/shell/test_setup_host_fan_out.bash
#
# Verify that core/setup/setup-host.sh selects one host adapter for the current
# project and does not run the generic project-local mirror path when a native
# adapter is available.

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

  mkdir -p "${acHome}/system/scripts"
  cat >"${acHome}/system/scripts/project-local-asset-migration.py" <<PY
#!/usr/bin/env python3
import pathlib
import sys

pathlib.Path(r"""${acHome}""", "migration-ran").write_text(
    "\n".join(sys.argv[1:]) + "\n",
    encoding="utf-8",
)
PY
  printf '{"version":1,"paths":{}}\n' \
    >"${acHome}/system/scripts/project-local-asset-fingerprints.json"

  echo "${acHome}"
}

run_setup_host() {
  local acHome="$1"
  local claudeDir="$2"
  local codexHome="$3"
  local projectRoot="${4:-$(make_tmp)}"

  AGENT_CREW_HOME="${acHome}" \
  CLAUDE_DIR="${claudeDir}" \
  CODEX_HOME="${codexHome}" \
  AGENT_CREW_MODE=install \
    bash "${SETUP_DIR}/setup-host.sh" "${projectRoot}" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Test: native claude detected — run claude only, not codex or generic.
# ---------------------------------------------------------------------------

TMP=$(make_tmp)
ACHOME=$(make_acHome)
RAN="${ACHOME}/ran"

# Create fake installation directories for claude and codex.
CLAUDE_INST_DIR="${TMP}/claude-inst"
CODEX_INST_DIR="${TMP}/codex-inst"
mkdir -p "${CLAUDE_INST_DIR}/agent-crew"
mkdir -p "${CODEX_INST_DIR}/skills/crew:run"

cat >"${ACHOME}/adapters/claude/detect.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${ACHOME}/adapters/claude/detect.sh"

run_setup_host "${ACHOME}" "${CLAUDE_INST_DIR}" "${CODEX_INST_DIR}"

it "native dispatch runs detected claude adapter"
RAN_CONTENTS=$(cat "${RAN}" 2>/dev/null || echo "")
assert_contains "${RAN_CONTENTS}" "claude"

it "native dispatch skips codex when claude was selected"
assert_not_contains "${RAN_CONTENTS}" "codex"

it "native dispatch does not run generic after claude"
assert_not_contains "${RAN_CONTENTS}" "generic"

# ---------------------------------------------------------------------------
# Test: native codex detected — run codex only, not generic.
# ---------------------------------------------------------------------------

TMP2=$(make_tmp)
ACHOME2=$(make_acHome)
RAN2="${ACHOME2}/ran"

CLAUDE_INST2="${TMP2}/claude-inst-absent"
CODEX_INST2="${TMP2}/codex-inst"
mkdir -p "${CODEX_INST2}/skills/crew:run"

cat >"${ACHOME2}/adapters/codex/detect.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${ACHOME2}/adapters/codex/detect.sh"

run_setup_host "${ACHOME2}" "${CLAUDE_INST2}" "${CODEX_INST2}"

it "native dispatch skips claude when codex was selected"
RAN2_CONTENTS=$(cat "${RAN2}" 2>/dev/null || echo "")
assert_not_contains "${RAN2_CONTENTS}" "claude"

it "native dispatch runs detected codex adapter"
assert_contains "${RAN2_CONTENTS}" "codex"

it "native dispatch does not run generic after codex"
assert_not_contains "${RAN2_CONTENTS}" "generic"

# ---------------------------------------------------------------------------
# Test: no native adapter detected — generic remains fallback.
# ---------------------------------------------------------------------------

TMP3=$(make_tmp)
ACHOME3=$(make_acHome)
RAN3="${ACHOME3}/ran"

CLAUDE_INST3="${TMP3}/claude-inst-absent"
CODEX_INST3="${TMP3}/codex-inst-absent"

run_setup_host "${ACHOME3}" "${CLAUDE_INST3}" "${CODEX_INST3}"

it "fallback dispatch skips claude when no native adapter is detected"
RAN3_CONTENTS=$(cat "${RAN3}" 2>/dev/null || echo "")
assert_not_contains "${RAN3_CONTENTS}" "claude"

it "fallback dispatch skips codex when no native adapter is detected"
assert_not_contains "${RAN3_CONTENTS}" "codex"

it "fallback dispatch runs generic when no native adapter is detected"
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

it "explicit HOST=generic runs generic only"
RAN4_CONTENTS=$(cat "${RAN4}" 2>/dev/null || echo "")
assert_not_contains "${RAN4_CONTENTS}" "claude"
assert_not_contains "${RAN4_CONTENTS}" "codex"
assert_contains "${RAN4_CONTENTS}" "generic"

# ---------------------------------------------------------------------------
# Test: setup invokes the internal project-local asset migration after adapter.
# ---------------------------------------------------------------------------

TMP5=$(make_tmp)
ACHOME5=$(make_acHome)
PROJECT5="${TMP5}/project"
mkdir -p "${PROJECT5}"
git -C "${PROJECT5}" init -q

run_setup_host \
  "${ACHOME5}" \
  "${TMP5}/claude-inst-absent" \
  "${TMP5}/codex-inst-absent" \
  "${PROJECT5}"

it "setup invokes internal project asset migration"
assert_file_exists "${ACHOME5}/migration-ran"

MIGRATION_ARGS=$(cat "${ACHOME5}/migration-ran" 2>/dev/null || echo "")

it "setup migration is bound to the current project"
assert_contains "${MIGRATION_ARGS}" "${PROJECT5}"

it "setup migration records setup mode"
assert_contains "${MIGRATION_ARGS}" "setup"

end_report
