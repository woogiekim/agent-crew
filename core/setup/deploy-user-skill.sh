#!/usr/bin/env bash
# deploy-user-skill.sh — propagate a newly created user skill guide to all
# installed agent-crew skill mirror paths.
#
# Usage:
#   bash deploy-user-skill.sh <skill-filename>
#   bash deploy-user-skill.sh my-skill.md
#
# Called automatically by crew:agent-maker after writing a new skill to
# ~/.agent-crew/user/skills/<name>.md. Enumerates all installed host adapters
# and copies the skill into each one's agent-crew mirror path.
#
# Adapters detected by sentinel path:
#   claude  — ~/.claude/agents/ directory exists → deploys to ~/.claude/agent-crew/skills/
#   codex   — ~/.codex/agents/  directory exists → deploys to ~/.codex/agent-crew/skills/
#
# The generic adapter installs into <project>/.agent-crew/skills/, but the
# project root is not known at agent-maker time. It will pick up the new
# skill on the next crew:update or crew:setup run for that project.
#
# This script is idempotent: safe to run multiple times for the same skill.
# Silent on non-installed adapters — no error if a path does not exist.

set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
SKILL_FILE="${1:-}"

if [ -z "${SKILL_FILE}" ]; then
  printf '[deploy-user-skill] ERROR: no skill filename provided\n' >&2
  printf 'Usage: %s <skill-filename.md>\n' "$0" >&2
  exit 1
fi

# Strip any directory prefix — we only accept a bare filename
SKILL_BASENAME="$(basename "${SKILL_FILE}")"

USER_SKILLS="${AGENT_CREW_HOME}/user/skills"
SKILL_PATH="${USER_SKILLS}/${SKILL_BASENAME}"

if [ ! -f "${SKILL_PATH}" ]; then
  printf '[deploy-user-skill] ERROR: skill not found: %s\n' "${SKILL_PATH}" >&2
  exit 1
fi

# Load shared helpers
. "${AGENT_CREW_HOME}/setup/common.sh"

SYSTEM_SKILLS="${AGENT_CREW_HOME}/system/skills"
UNIFIED_SKILLS="${AGENT_CREW_HOME}/skills"

# Refresh the provider-neutral discovery view first. This preserves the
# system/user layer contract and ensures user skills override same-name system
# defaults before any host mirror receives the file.
merge_skills_to_discovery "${SYSTEM_SKILLS}" "${USER_SKILLS}" "${UNIFIED_SKILLS}"
UNIFIED_SKILL_PATH="${UNIFIED_SKILLS}/${SKILL_BASENAME}"

DEPLOYED=0

# ── Claude adapter ────────────────────────────────────────────────────────────
# Agent-crew mirror path: ~/.claude/agent-crew/skills/
CLAUDE_AGENTS="${HOME}/.claude/agents"
if [ -d "${CLAUDE_AGENTS}" ]; then
  CLAUDE_CREW_SKILLS="${HOME}/.claude/agent-crew/skills"
  mkdir -p "${CLAUDE_CREW_SKILLS}"
  printf '[deploy-user-skill] Deploying to Claude: %s\n' "${CLAUDE_CREW_SKILLS}"
  cp "${UNIFIED_SKILL_PATH}" "${CLAUDE_CREW_SKILLS}/${SKILL_BASENAME}"
  DEPLOYED=$((DEPLOYED + 1))
fi

# ── Codex adapter ─────────────────────────────────────────────────────────────
# Agent-crew mirror path: ~/.codex/agent-crew/skills/
CODEX_AGENTS="${HOME}/.codex/agents"
if [ -d "${CODEX_AGENTS}" ]; then
  CODEX_CREW_SKILLS="${HOME}/.codex/agent-crew/skills"
  mkdir -p "${CODEX_CREW_SKILLS}"
  printf '[deploy-user-skill] Deploying to Codex: %s\n' "${CODEX_CREW_SKILLS}"
  cp "${UNIFIED_SKILL_PATH}" "${CODEX_CREW_SKILLS}/${SKILL_BASENAME}"
  DEPLOYED=$((DEPLOYED + 1))
fi

# ── Generic adapter (best-effort) ────────────────────────────────────────────
# Deploy to the current project's .agent-crew/skills/ when present.
# Covers generic-adapter projects. The project root is not known at agent-maker
# time, so CWD is used as the best-effort anchor.
if [ -d "${PWD}/.agent-crew" ]; then
  GENERIC_SKILLS="${PWD}/.agent-crew/skills"
  mkdir -p "${GENERIC_SKILLS}"
  printf '[deploy-user-skill] Deploying to generic project: %s\n' "${GENERIC_SKILLS}"
  cp "${UNIFIED_SKILL_PATH}" "${GENERIC_SKILLS}/${SKILL_BASENAME}"
  DEPLOYED=$((DEPLOYED + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
if [ "${DEPLOYED}" -eq 0 ]; then
  printf '[deploy-user-skill] No installed host adapters detected — skill saved to user/skills/ only.\n'
  printf '[deploy-user-skill] Run crew:update or crew:setup to install for a specific host.\n'
else
  printf '[deploy-user-skill] Deployed %s to %d host adapter(s).\n' "${SKILL_BASENAME}" "${DEPLOYED}"
fi
