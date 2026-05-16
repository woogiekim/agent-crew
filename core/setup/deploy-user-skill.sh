#!/usr/bin/env bash
# deploy-user-skill.sh — propagate a newly created user skill guide to all
# installed host adapter discovery paths.
#
# Usage:
#   bash deploy-user-skill.sh <skill-filename>
#   bash deploy-user-skill.sh my-skill.md
#
# Called automatically by crew:agent-maker after writing a new skill to
# ~/.agent-crew/user/skills/<name>.md. Enumerates all installed host adapters
# and copies the skill into each one's discovery path.
#
# Adapters detected by sentinel path:
#   claude  — ~/.claude/agents/ directory exists → deploys to ~/.claude/agent-crew/skills/
#   codex   — ~/.codex/agents/  directory exists → deploys to ~/.codex/skills/
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

DEPLOYED=0

# ── Claude adapter ────────────────────────────────────────────────────────────
# Discovery path: ~/.claude/agent-crew/skills/
CLAUDE_AGENTS="${HOME}/.claude/agents"
if [ -d "${CLAUDE_AGENTS}" ]; then
  CLAUDE_CREW_SKILLS="${HOME}/.claude/agent-crew/skills"
  mkdir -p "${CLAUDE_CREW_SKILLS}"
  printf '[deploy-user-skill] Deploying to Claude: %s\n' "${CLAUDE_CREW_SKILLS}"
  cp "${SKILL_PATH}" "${CLAUDE_CREW_SKILLS}/${SKILL_BASENAME}"
  DEPLOYED=$((DEPLOYED + 1))
fi

# ── Codex adapter ─────────────────────────────────────────────────────────────
# Discovery path: ~/.codex/skills/
CODEX_AGENTS="${HOME}/.codex/agents"
if [ -d "${CODEX_AGENTS}" ]; then
  CODEX_SKILLS="${HOME}/.codex/skills"
  mkdir -p "${CODEX_SKILLS}"
  printf '[deploy-user-skill] Deploying to Codex: %s\n' "${CODEX_SKILLS}"
  cp "${SKILL_PATH}" "${CODEX_SKILLS}/${SKILL_BASENAME}"
  DEPLOYED=$((DEPLOYED + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
if [ "${DEPLOYED}" -eq 0 ]; then
  printf '[deploy-user-skill] No installed host adapters detected — skill saved to user/skills/ only.\n'
  printf '[deploy-user-skill] Run crew:update or crew:setup to install for a specific host.\n'
else
  printf '[deploy-user-skill] Deployed %s to %d host adapter(s).\n' "${SKILL_BASENAME}" "${DEPLOYED}"
fi
