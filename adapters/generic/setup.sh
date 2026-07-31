#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
# AGENT_CREW_MODE: "install" (default) or "update". Update mode never prompts
# and never resets state; cp -R overwrites but does not delete extraneous
# files, so the copy operations below are idempotent in both modes.
AGENT_CREW_MODE="${AGENT_CREW_MODE:-install}"
AGENT_CREW_PROJECT_LOCAL_ONLY="${AGENT_CREW_PROJECT_LOCAL_ONLY:-0}"

. "${AGENT_CREW_HOME}/setup/common.sh"

if [ "${AGENT_CREW_MODE}" = "update" ]; then
  printf 'MODE: update (host=generic)\n'
fi

mkdir -p "${PROJECT_ROOT}/.agent-crew"
mkdir -p \
  "${PROJECT_ROOT}/.agent-crew/project/commands" \
  "${PROJECT_ROOT}/.agent-crew/project/agents" \
  "${PROJECT_ROOT}/.agent-crew/project/skills" \
  "${PROJECT_ROOT}/.agent-crew/links"
link_or_copy_shared_dir "${AGENT_CREW_HOME}/hooks" "${PROJECT_ROOT}/.agent-crew/hooks" "generic-hooks"
link_or_copy_shared_dir "${AGENT_CREW_HOME}/user/commands" "${PROJECT_ROOT}/.agent-crew/links/user-commands" "generic-user-commands"
link_or_copy_shared_dir "${AGENT_CREW_HOME}/system/commands" "${PROJECT_ROOT}/.agent-crew/links/system-commands" "generic-system-commands"
link_or_copy_shared_dir "${AGENT_CREW_HOME}/commands" "${PROJECT_ROOT}/.agent-crew/commands" "generic-commands"

# Merge system agents + user agents into the project discovery path.
# System agents are always included. User agents are layered on top with
# conflict detection: a same-name system agent remains authoritative. Skill
# layers below use a different policy: user skills override same-name system
# skill defaults.
merge_agents_to_discovery \
  "${AGENT_CREW_HOME}/system/agents" \
  "${AGENT_CREW_HOME}/user/agents" \
  "${PROJECT_ROOT}/.agent-crew/agents"
if [ -d "${PROJECT_ROOT}/.agent-crew/project/agents" ]; then
  mkdir -p "${PROJECT_ROOT}/.agent-crew/agents"
  while IFS= read -r -d '' project_agent; do
    basename_file="$(basename "${project_agent}")"
    [ "${basename_file}" = "README.md" ] && continue
    if [ -f "${PROJECT_ROOT}/.agent-crew/agents/${basename_file}" ]; then
      printf '[agent-crew] WARNING: %s exists in project/agents and an earlier agent layer; not auto-selected. Use crew agent --agent-layer project or --save-agent-layer project.\n' "${basename_file}" >&2
      continue
    fi
    diff_copy "${project_agent}" "${PROJECT_ROOT}/.agent-crew/agents/${basename_file}"
  done < <(find "${PROJECT_ROOT}/.agent-crew/project/agents" -maxdepth 1 -name "*.md" -print0 2>/dev/null)
fi

# Note: reasoning_tier is not materialized on the generic adapter.
# Generic targets single-model environments; the abstract tier is
# advisory only. See core/rules/capabilities/reasoning-tier.md.

# Detect old flat layout and safely clean managed duplicates.
if [ -d "${AGENT_CREW_HOME}/agents" ] && [ ! -L "${AGENT_CREW_HOME}/agents" ]; then
  _LEGACY_SOURCE_AGENTS="${AGENT_CREW_HOME}/system/agents"
  if [ -n "${SOURCE_ROOT:-}" ] && [ -d "${SOURCE_ROOT}/core/agents" ]; then
    _LEGACY_SOURCE_AGENTS="${SOURCE_ROOT}/core/agents"
  fi
  migrate_legacy_agents \
    "${AGENT_CREW_HOME}/agents" \
    "${_LEGACY_SOURCE_AGENTS}" \
    "${AGENT_CREW_HOME}/system/agents" \
    "${AGENT_CREW_HOME}/user/agents" \
    "mcp-manager.md"
fi
# Scaffold skill directories and populate unified discovery
if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ]; then
  mkdir -p "${AGENT_CREW_HOME}/system/skills"
  mkdir -p "${AGENT_CREW_HOME}/user/skills"
  mkdir -p "${AGENT_CREW_HOME}/skills"
fi

if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ] && [ ! -f "${AGENT_CREW_HOME}/user/skills/README.md" ]; then
  cat > "${AGENT_CREW_HOME}/user/skills/README.md" << 'UEOF'
# User Skills

Place your custom skill definitions here.
Files in this directory are NEVER overwritten by crew:update.
UEOF
fi

# Sync system skills from source repo when SOURCE_ROOT is available
if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ] && [ -n "${SOURCE_ROOT:-}" ] && [ -d "${SOURCE_ROOT}/core/agents/skills" ]; then
  sync_system_skills \
    "${SOURCE_ROOT}/core/agents/skills" \
    "${AGENT_CREW_HOME}/system/skills"
fi

# Merge system + user skills into unified discovery path
if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ]; then
  merge_skills_to_discovery \
    "${AGENT_CREW_HOME}/system/skills" \
    "${AGENT_CREW_HOME}/user/skills" \
    "${AGENT_CREW_HOME}/skills"
fi

# Refresh skills in the project-local discovery path.
link_or_copy_shared_dir "${AGENT_CREW_HOME}/user/skills" "${PROJECT_ROOT}/.agent-crew/links/user-skills" "generic-user-skills"
link_or_copy_shared_dir "${AGENT_CREW_HOME}/system/skills" "${PROJECT_ROOT}/.agent-crew/links/system-skills" "generic-system-skills"
link_or_copy_shared_dir "${AGENT_CREW_HOME}/skills" "${PROJECT_ROOT}/.agent-crew/skills" "generic-skills"

cp "${AGENT_CREW_HOME}/adapters/generic/invocation.md" "${PROJECT_ROOT}/.agent-crew/invocation.md" 2>/dev/null || true
chmod +x "${PROJECT_ROOT}/.agent-crew/hooks/"*.sh 2>/dev/null || true
merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${PROJECT_ROOT}/AGENTS.md"
register_local_git_excludes "${PROJECT_ROOT}" ".agent-crew/" "AGENTS.md" ".agent-crew/settings.local.json" ".agent-crew/AGENTS.local.md"

printf 'HOST: generic\n'
printf 'INSTALLED: %s\n' "${PROJECT_ROOT}/.agent-crew"
