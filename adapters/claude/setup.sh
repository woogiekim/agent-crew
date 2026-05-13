#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"

. "${AGENT_CREW_HOME}/setup/common.sh"

copy_dir_contents "${AGENT_CREW_HOME}/commands" "${CLAUDE_DIR}/commands"
copy_dir_contents "${AGENT_CREW_HOME}/agents" "${CLAUDE_DIR}/agent-crew/agents"
copy_dir_contents "${AGENT_CREW_HOME}/hooks" "${CLAUDE_DIR}/agent-crew/hooks"
copy_dir_contents "${AGENT_CREW_HOME}/rules" "${CLAUDE_DIR}/agent-crew/rules"
copy_dir_contents "${AGENT_CREW_HOME}/setup" "${CLAUDE_DIR}/agent-crew/setup"
copy_dir_contents "${AGENT_CREW_HOME}/adapters/claude" "${CLAUDE_DIR}/agent-crew/adapters/claude"
mkdir -p "${CLAUDE_DIR}/agent-crew"
cp "${AGENT_CREW_HOME}/adapters/claude/invocation.md" "${CLAUDE_DIR}/agent-crew/invocation.md" 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/hooks/"*.sh 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/setup/"*.sh 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/adapters/claude/"*.sh 2>/dev/null || true
merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${CLAUDE_DIR}/CLAUDE.md"
register_local_git_excludes "${PROJECT_ROOT}" ".claude/" "CLAUDE.md" ".claude/settings.local.json" ".claude/CLAUDE.local.md"

# Write host capability flags so the core pipeline can opt into Claude Code's
# richer task-tracking surface (TaskCreate / TaskList / TaskUpdate / Monitor).
# Schema documented at core/rules/host-capabilities.md.
# Absence of this file MUST be treated as legacy behavior (all flags false).
PROJECT_NAME="$(basename "${PROJECT_ROOT}")"
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
CAPABILITIES_FILE="${STATE_DIR}/capabilities.json"
mkdir -p "${STATE_DIR}"
cat > "${CAPABILITIES_FILE}" <<'CAPS_EOF'
{
  "host": "claude",
  "task_tools": true,
  "agent_background": true,
  "monitor_tool": true
}
CAPS_EOF

printf 'HOST: claude\n'
printf 'PROJECT_ROOT: %s\n' "${PROJECT_ROOT}"
printf 'INSTALLED: %s\n' "${CLAUDE_DIR}"
printf 'CAPABILITIES: %s\n' "${CAPABILITIES_FILE}"
