#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

. "${AGENT_CREW_HOME}/setup/common.sh"

mkdir -p "${PROJECT_ROOT}/.agent-crew"
copy_dir_contents "${AGENT_CREW_HOME}/commands" "${PROJECT_ROOT}/.agent-crew/commands"
copy_dir_contents "${AGENT_CREW_HOME}/agents" "${PROJECT_ROOT}/.agent-crew/agents"
copy_dir_contents "${AGENT_CREW_HOME}/hooks" "${PROJECT_ROOT}/.agent-crew/hooks"
cp "${AGENT_CREW_HOME}/adapters/generic/invocation.md" "${PROJECT_ROOT}/.agent-crew/invocation.md" 2>/dev/null || true
chmod +x "${PROJECT_ROOT}/.agent-crew/hooks/"*.sh 2>/dev/null || true
merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${PROJECT_ROOT}/AGENTS.md"
register_local_git_excludes "${PROJECT_ROOT}" ".agent-crew/" "AGENTS.md" ".agent-crew/settings.local.json" ".agent-crew/AGENTS.local.md"

printf 'HOST: generic\n'
printf 'INSTALLED: %s\n' "${PROJECT_ROOT}/.agent-crew"
