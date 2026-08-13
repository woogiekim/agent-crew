#!/usr/bin/env bash
# Shared shell entrypoint for bounded lifecycle-hook stdin reads.

read_agent_crew_hook_input() {
  local agent_crew_home reader hook_dir

  hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)" || return 1
  reader="${hook_dir}/../scripts/hook_input.py"
  agent_crew_home="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
  if [ ! -f "${reader}" ]; then
    reader="${agent_crew_home}/scripts/hook_input.py"
  fi
  [ -f "${reader}" ] || return 1

  python3 -S "${reader}" 2>/dev/null
}
