#!/usr/bin/env bash
# update-global-adapters.sh
#
# Phase (a) of the crew:update Step 4 split (P5):
#   Refresh all *global-scope* adapter paths that are installed on this
#   machine, without requiring PROJECT_ROOT context.
#
# This script is deliberately separate from setup-host.sh so that update.md
# can call it unconditionally before the project-local adapter run.  It only
# touches paths that are safe to re-copy regardless of the current working
# directory:
#
#   - Claude:  ~/.claude/agent-crew/  (via install_claude_compat)
#   - Codex:   ~/.codex/skills/agent-crew/  (via install_codex_bootstrap_skill)
#              ~/.codex/agent-crew/skills/
#
# Generic has no global scope (all paths are project-local), so it is not
# handled here — setup-host.sh covers it for the current PROJECT_ROOT.
#
# Usage (from update.md Step 4a):
#   AGENT_CREW_MODE=update SOURCE_ROOT="${SOURCE_ROOT}" \
#     bash "${AGENT_CREW_HOME}/scripts/update-global-adapters.sh"
#
# Environment variables consumed:
#   AGENT_CREW_HOME   — ~/.agent-crew unless overridden
#   AGENT_CREW_MODE   — should be "update" when called from crew:update
#   SOURCE_ROOT       — root of the agent-crew source repo (contains core/ and adapters/)
#   CLAUDE_DIR        — ~/.claude unless overridden
#   CODEX_HOME        — ~/.codex unless overridden

set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
AGENT_CREW_MODE="${AGENT_CREW_MODE:-update}"
export AGENT_CREW_MODE

CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"

# Resolve source root: prefer the explicit env var, then look for the
# canonical source.path pointer written by crew:update Step 5.
if [ -z "${SOURCE_ROOT:-}" ]; then
  if [ -f "${AGENT_CREW_HOME}/source.path" ]; then
    SOURCE_ROOT="$(cat "${AGENT_CREW_HOME}/source.path")"
  else
    printf '[update-global-adapters] WARNING: SOURCE_ROOT not set and source.path not found.\n' >&2
    printf '  Skipping global adapter update. Run crew:update from the agent-crew source tree.\n' >&2
    exit 0
  fi
fi

SOURCE_DIR="${SOURCE_ROOT}/core"
ADAPTERS_DIR="${SOURCE_ROOT}/adapters"

if [ ! -d "${SOURCE_DIR}" ] || [ ! -d "${ADAPTERS_DIR}" ]; then
  printf '[update-global-adapters] WARNING: SOURCE_DIR or ADAPTERS_DIR missing under %s.\n' "${SOURCE_ROOT}" >&2
  printf '  Skipping global adapter update.\n' >&2
  exit 0
fi

# Source install.sh helpers so we can reuse install_claude_compat,
# install_codex_bootstrap_skill, merge_global_settings, etc.
# We source rather than call install.sh as a subprocess to avoid re-running
# install_global (which would trigger the "already installed" prompt path).
# shellcheck source=/dev/null
. "${SOURCE_ROOT}/install.sh" 2>/dev/null || {
  # Fallback: if sourcing fails (e.g. install.sh exits early on the
  # "already installed" branch under some shells), define minimal stubs so
  # the Codex global path copy below can still run.
  log_info()  { printf '[✓] %s\n' "$1"; }
  log_warn()  { printf '[!] %s\n' "$1"; }
}

printf '[update-global-adapters] Refreshing global adapter paths (MODE: %s)\n' "${AGENT_CREW_MODE}"

# ── Claude global paths ───────────────────────────────────────────────────────
if [ -d "${CLAUDE_DIR}/agent-crew" ]; then
  printf '[update-global-adapters] Updating Claude global paths → %s/agent-crew/\n' "${CLAUDE_DIR}"
  AGENT_CREW_HOST=claude AGENT_CREW_MODE="${AGENT_CREW_MODE}" SOURCE_ROOT="${SOURCE_ROOT}" \
    bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "$(pwd)" >/dev/null 2>&1 || \
    printf '[update-global-adapters] WARNING: Claude adapter returned non-zero (continuing)\n' >&2
else
  printf '[update-global-adapters] Skipping Claude update — not installed (%s/agent-crew does not exist)\n' "${CLAUDE_DIR}"
fi

# ── Codex global paths ────────────────────────────────────────────────────────
CODEX_SKILL_DIR="${CODEX_HOME}/skills/agent-crew"
CODEX_CREW_SKILLS_DIR="${CODEX_HOME}/agent-crew/skills"

if [ -d "${CODEX_SKILL_DIR}" ]; then
  printf '[update-global-adapters] Updating Codex bootstrap skill → %s\n' "${CODEX_SKILL_DIR}"
  if [ -d "${ADAPTERS_DIR}/codex/skill/agent-crew" ]; then
    cp -R "${ADAPTERS_DIR}/codex/skill/agent-crew/." "${CODEX_SKILL_DIR}/"
    printf '[update-global-adapters] Codex bootstrap skill refreshed → %s\n' "${CODEX_SKILL_DIR}"
  else
    printf '[update-global-adapters] WARNING: Codex skill source not found at %s/codex/skill/agent-crew\n' "${ADAPTERS_DIR}" >&2
  fi
else
  printf '[update-global-adapters] Skipping Codex bootstrap skill — not installed (%s does not exist)\n' "${CODEX_SKILL_DIR}"
fi

if [ -d "${CODEX_CREW_SKILLS_DIR}" ]; then
  printf '[update-global-adapters] Updating Codex crew-skills mirror → %s\n' "${CODEX_CREW_SKILLS_DIR}"
  if [ -d "${AGENT_CREW_HOME}/system/agents/skills" ]; then
    mkdir -p "${CODEX_CREW_SKILLS_DIR}"
    cp -r "${AGENT_CREW_HOME}/system/agents/skills/." "${CODEX_CREW_SKILLS_DIR}/" 2>/dev/null || true
    printf '[update-global-adapters] Codex crew-skills mirror refreshed → %s\n' "${CODEX_CREW_SKILLS_DIR}"
  fi
else
  printf '[update-global-adapters] Skipping Codex crew-skills mirror — directory not present (%s)\n' "${CODEX_CREW_SKILLS_DIR}"
fi

printf '[update-global-adapters] Global adapter refresh complete.\n'
