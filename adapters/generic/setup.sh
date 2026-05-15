#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
# AGENT_CREW_MODE: "install" (default) or "update". Update mode never prompts
# and never resets state; cp -R overwrites but does not delete extraneous
# files, so the copy operations below are idempotent in both modes.
AGENT_CREW_MODE="${AGENT_CREW_MODE:-install}"

. "${AGENT_CREW_HOME}/setup/common.sh"

if [ "${AGENT_CREW_MODE}" = "update" ]; then
  printf 'MODE: update (host=generic)\n'
fi

mkdir -p "${PROJECT_ROOT}/.agent-crew"
copy_dir_contents "${AGENT_CREW_HOME}/commands" "${PROJECT_ROOT}/.agent-crew/commands"
copy_dir_contents "${AGENT_CREW_HOME}/system/agents" "${PROJECT_ROOT}/.agent-crew/agents"
copy_dir_contents "${AGENT_CREW_HOME}/hooks" "${PROJECT_ROOT}/.agent-crew/hooks"

# Detect old flat layout and warn
if [ -d "${AGENT_CREW_HOME}/agents" ] && [ ! -L "${AGENT_CREW_HOME}/agents" ]; then
  printf '\n[agent-crew] NOTE: Legacy layout detected at %s/agents/\n' "${AGENT_CREW_HOME}"
  printf 'This directory is no longer used by crew. Files installed by crew have moved to system/.\n'
  printf 'If you have custom agents in %s/agents/, move them to %s/user/agents/\n' "${AGENT_CREW_HOME}" "${AGENT_CREW_HOME}"
  printf 'Then you can safely delete %s/agents/\n\n' "${AGENT_CREW_HOME}"
fi
cp "${AGENT_CREW_HOME}/adapters/generic/invocation.md" "${PROJECT_ROOT}/.agent-crew/invocation.md" 2>/dev/null || true
chmod +x "${PROJECT_ROOT}/.agent-crew/hooks/"*.sh 2>/dev/null || true
merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${PROJECT_ROOT}/AGENTS.md"
register_local_git_excludes "${PROJECT_ROOT}" ".agent-crew/" "AGENTS.md" ".agent-crew/settings.local.json" ".agent-crew/AGENTS.local.md"

printf 'HOST: generic\n'
printf 'INSTALLED: %s\n' "${PROJECT_ROOT}/.agent-crew"
