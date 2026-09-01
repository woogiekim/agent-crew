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
copy_file_if_changed "${AGENT_CREW_HOME}/adapters/generic/invocation.md" "${PROJECT_ROOT}/.agent-crew/invocation.md"
register_local_git_excludes "${PROJECT_ROOT}" ".agent-crew/"

printf 'HOST: generic\n'
printf 'INSTALLED: %s\n' "${PROJECT_ROOT}/.agent-crew"
