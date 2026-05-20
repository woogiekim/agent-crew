#!/usr/bin/env bash
# sync-local-install.sh - refresh installed agent-crew assets from a local checkout.
#
# This is the deterministic local-source counterpart to crew:update's remote
# fresh-clone flow. Use it after making local changes that should immediately
# affect the installed ~/.agent-crew, Claude, Codex, and project-local adapter
# paths without waiting for those changes to exist on origin/main.

set -euo pipefail

usage() {
  cat <<'EOF'
usage: sync-local-install.sh [SOURCE_ROOT] [PROJECT_ROOT]

Refresh installed agent-crew assets from a local source checkout.

Arguments:
  SOURCE_ROOT   agent-crew source checkout; defaults to current git root
  PROJECT_ROOT  project to refresh host adapter files for; defaults to SOURCE_ROOT

Environment:
  AGENT_CREW_HOME  install root; defaults to ~/.agent-crew
  CLAUDE_DIR       Claude config root; defaults to ~/.claude
  CODEX_HOME       Codex config root; defaults to ~/.codex

EOF
}

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

SOURCE_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
PROJECT_ROOT="${2:-${SOURCE_ROOT}}"
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"

SOURCE_ROOT="$(cd "${SOURCE_ROOT}" && pwd)"
PROJECT_ROOT="$(cd "${PROJECT_ROOT}" && pwd)"

if [ ! -d "${SOURCE_ROOT}/core" ] || [ ! -d "${SOURCE_ROOT}/adapters" ]; then
  printf 'sync-local-install: SOURCE_ROOT is not an agent-crew checkout: %s\n' "${SOURCE_ROOT}" >&2
  exit 2
fi

mkdir -p \
  "${AGENT_CREW_HOME}/system/commands" "${AGENT_CREW_HOME}/commands" \
  "${AGENT_CREW_HOME}/system/rules" "${AGENT_CREW_HOME}/rules" \
  "${AGENT_CREW_HOME}/system/hooks" "${AGENT_CREW_HOME}/hooks" \
  "${AGENT_CREW_HOME}/system/scripts" "${AGENT_CREW_HOME}/scripts" \
  "${AGENT_CREW_HOME}/system/schemas" "${AGENT_CREW_HOME}/schemas" \
  "${AGENT_CREW_HOME}/system/setup" "${AGENT_CREW_HOME}/setup" \
  "${AGENT_CREW_HOME}/system/adapters" "${AGENT_CREW_HOME}/adapters" \
  "${AGENT_CREW_HOME}/system/agents" "${AGENT_CREW_HOME}/system/skills" \
  "${AGENT_CREW_HOME}/skills" "${AGENT_CREW_HOME}/bin"

copy_flat() {
  local src="$1" dest="$2" pattern="$3"
  [ -d "${src}" ] || return 0
  # shellcheck disable=SC2086
  cp -f "${src}"/${pattern} "${dest}/" 2>/dev/null || true
}

copy_tree() {
  local src="$1" dest="$2"
  [ -d "${src}" ] || return 0
  cp -rf "${src}/." "${dest}/"
}

copy_flat "${SOURCE_ROOT}/core/commands" "${AGENT_CREW_HOME}/system/commands" "*.md"
copy_flat "${SOURCE_ROOT}/core/commands" "${AGENT_CREW_HOME}/commands" "*.md"
copy_tree "${SOURCE_ROOT}/core/rules" "${AGENT_CREW_HOME}/system/rules"
copy_tree "${SOURCE_ROOT}/core/rules" "${AGENT_CREW_HOME}/rules"
copy_flat "${SOURCE_ROOT}/core/hooks" "${AGENT_CREW_HOME}/system/hooks" "*.sh"
copy_flat "${SOURCE_ROOT}/core/hooks" "${AGENT_CREW_HOME}/hooks" "*.sh"
copy_tree "${SOURCE_ROOT}/core/scripts" "${AGENT_CREW_HOME}/system/scripts"
copy_tree "${SOURCE_ROOT}/core/scripts" "${AGENT_CREW_HOME}/scripts"
copy_flat "${SOURCE_ROOT}/core/schemas" "${AGENT_CREW_HOME}/system/schemas" "*.json"
copy_flat "${SOURCE_ROOT}/core/schemas" "${AGENT_CREW_HOME}/schemas" "*.json"
copy_flat "${SOURCE_ROOT}/core/setup" "${AGENT_CREW_HOME}/system/setup" "*.sh"
copy_flat "${SOURCE_ROOT}/core/setup" "${AGENT_CREW_HOME}/setup" "*.sh"
copy_tree "${SOURCE_ROOT}/adapters" "${AGENT_CREW_HOME}/system/adapters"
copy_tree "${SOURCE_ROOT}/adapters" "${AGENT_CREW_HOME}/adapters"
copy_tree "${SOURCE_ROOT}/core/agents" "${AGENT_CREW_HOME}/system/agents"
copy_tree "${SOURCE_ROOT}/core/agents/skills" "${AGENT_CREW_HOME}/system/skills"
copy_flat "${SOURCE_ROOT}/core/bin" "${AGENT_CREW_HOME}/bin" "*"

chmod +x \
  "${AGENT_CREW_HOME}/system/hooks/"*.sh "${AGENT_CREW_HOME}/hooks/"*.sh \
  "${AGENT_CREW_HOME}/system/scripts/"*.sh "${AGENT_CREW_HOME}/scripts/"*.sh \
  "${AGENT_CREW_HOME}/system/scripts/"*.py "${AGENT_CREW_HOME}/scripts/"*.py \
  "${AGENT_CREW_HOME}/system/setup/"*.sh "${AGENT_CREW_HOME}/setup/"*.sh \
  "${AGENT_CREW_HOME}/bin/"* \
  2>/dev/null || true

# shellcheck source=/dev/null
. "${AGENT_CREW_HOME}/system/setup/common.sh"

sync_system_agents \
  "${SOURCE_ROOT}/core/agents" \
  "${AGENT_CREW_HOME}/system/agents" \
  "mcp-manager.md"

merge_agents_to_discovery \
  "${AGENT_CREW_HOME}/system/agents" \
  "${AGENT_CREW_HOME}/user/agents" \
  "${CLAUDE_DIR}/agents"

sync_system_skills \
  "${SOURCE_ROOT}/core/agents/skills" \
  "${AGENT_CREW_HOME}/system/skills"

merge_skills_to_discovery \
  "${AGENT_CREW_HOME}/system/skills" \
  "${AGENT_CREW_HOME}/user/skills" \
  "${AGENT_CREW_HOME}/skills"

SOURCE_ROOT="${SOURCE_ROOT}" AGENT_CREW_MODE=update \
  bash "${AGENT_CREW_HOME}/system/scripts/update-global-adapters.sh"

SOURCE_ROOT="${SOURCE_ROOT}" AGENT_CREW_MODE=update \
  bash "${AGENT_CREW_HOME}/system/setup/setup-host.sh" "${PROJECT_ROOT}"

printf 'sync-local-install: refreshed installed assets from %s\n' "${SOURCE_ROOT}"
