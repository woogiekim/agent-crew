#!/usr/bin/env bash
# deploy-user-agent.sh — propagate a newly created user agent to all installed
# host adapter discovery paths.
#
# Usage:
#   bash deploy-user-agent.sh <agent-filename>
#   bash deploy-user-agent.sh my-agent.md
#
# Called automatically by crew:agent-maker after writing a new agent to
# ~/.agent-crew/user/agents/<name>.md. Enumerates all installed host adapters
# and installs the agent into each one's discovery path.
#
# Adapters detected by sentinel path:
#   claude  — ~/.claude/agents/ directory exists
#   codex   — ~/.codex/agents/ directory exists
#
# The generic adapter installs into <project>/.agent-crew/agents/, but the
# project root is not known at agent-maker time. It will pick up the new
# agent on the next crew:setup run for that project.
#
# This script is idempotent: safe to run multiple times for the same agent.
# Silent on non-installed adapters — no error if a path does not exist.

set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
AGENT_FILE="${1:-}"

if [ -z "${AGENT_FILE}" ]; then
  printf '[deploy-user-agent] ERROR: no agent filename provided\n' >&2
  printf 'Usage: %s <agent-filename.md>\n' "$0" >&2
  exit 1
fi

# Strip any directory prefix — we only accept a bare filename
AGENT_BASENAME="$(basename "${AGENT_FILE}")"

USER_AGENTS="${AGENT_CREW_HOME}/user/agents"
SYSTEM_AGENTS="${AGENT_CREW_HOME}/system/agents"
AGENT_PATH="${USER_AGENTS}/${AGENT_BASENAME}"

if [ ! -f "${AGENT_PATH}" ]; then
  printf '[deploy-user-agent] ERROR: agent not found: %s\n' "${AGENT_PATH}" >&2
  exit 1
fi

# Load shared helpers (merge_agents_to_discovery, copy_dir_contents)
. "${AGENT_CREW_HOME}/setup/common.sh"

DEPLOYED=0

# ── Claude adapter ────────────────────────────────────────────────────────────
# Discovery path: ~/.claude/agents/
CLAUDE_AGENTS="${HOME}/.claude/agents"
if [ -d "${CLAUDE_AGENTS}" ]; then
  printf '[deploy-user-agent] Deploying to Claude: %s\n' "${CLAUDE_AGENTS}"
  merge_agents_to_discovery "${SYSTEM_AGENTS}" "${USER_AGENTS}" "${CLAUDE_AGENTS}"
  # Also keep the agent-crew mirror path in sync
  CLAUDE_CREW_AGENTS="${HOME}/.claude/agent-crew/agents"
  if [ -d "${CLAUDE_CREW_AGENTS}" ]; then
    copy_dir_contents "${SYSTEM_AGENTS}" "${CLAUDE_CREW_AGENTS}"
    cp "${AGENT_PATH}" "${CLAUDE_CREW_AGENTS}/" 2>/dev/null || true
  fi
  DEPLOYED=$((DEPLOYED + 1))
fi

# ── Codex adapter ─────────────────────────────────────────────────────────────
# Discovery path: ~/.codex/agents/
CODEX_AGENTS="${HOME}/.codex/agents"
if [ -d "${CODEX_AGENTS}" ]; then
  printf '[deploy-user-agent] Deploying to Codex: %s\n' "${CODEX_AGENTS}"
  diff_copy "${AGENT_PATH}" "${CODEX_AGENTS}/${AGENT_BASENAME}"
  DEPLOYED=$((DEPLOYED + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
print_diff_summary

if [ "${DEPLOYED}" -eq 0 ]; then
  printf '[deploy-user-agent] No installed host adapters detected — agent saved to user/agents/ only.\n'
  printf '[deploy-user-agent] Run crew:setup to install for a specific host.\n'
else
  printf '[deploy-user-agent] Deployed %s to %d host adapter(s).\n' "${AGENT_BASENAME}" "${DEPLOYED}"
fi
