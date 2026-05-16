#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
# AGENT_CREW_MODE: "install" (default) or "update". Update mode never prompts
# and never resets state; the copy operations below are idempotent in both
# modes (cp -R overwrites but does not delete extraneous files).
AGENT_CREW_MODE="${AGENT_CREW_MODE:-install}"

. "${AGENT_CREW_HOME}/setup/common.sh"

if [ "${AGENT_CREW_MODE}" = "update" ]; then
  printf 'MODE: update (host=codex)\n'
fi

write_codex_hooks_json() {
  local dest="$1"
  local agent_crew_home="$2"

  python3 - "$dest" "$agent_crew_home" <<'PYEOF'
import json
import sys
from pathlib import Path

dest = Path(sys.argv[1])
home = Path(sys.argv[2]).expanduser()
settings = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash '{home}/hooks/guard-dangerous-commands.sh'",
                    }
                ],
            },
            {
                "matcher": "Agent",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash '{home}/hooks/context-guard.sh'",
                        "timeout": 5,
                    }
                ],
            },
        ],
        "PostToolUse": [
            {
                "matcher": "Edit|Write|MultiEdit",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash '{home}/hooks/verify-rules.sh'",
                    }
                ],
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash '{home}/hooks/auto-route.sh'",
                        "timeout": 5,
                    }
                ]
            }
        ],
    }
}
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
PYEOF
}

install_codex_skills() {
  local codex_home="${HOME}/.codex"
  local skill_root="${AGENT_CREW_HOME}/adapters/codex/skill"
  local skill_src
  local skill_name
  local skill_dest

  [ -d "${skill_root}" ] || return 0
  mkdir -p "${codex_home}/skills"

  for skill_src in "${skill_root}"/*; do
    [ -d "${skill_src}" ] || continue
    skill_name="$(basename "${skill_src}")"
    skill_dest="${codex_home}/skills/${skill_name}"
    rm -rf "${skill_dest}"
    mkdir -p "${skill_dest}"
    copy_dir_contents "${skill_src}" "${skill_dest}"
  done
}

copy_dir_contents "${AGENT_CREW_HOME}/adapters/codex/template" "${PROJECT_ROOT}/.codex"

# Note: reasoning_tier is NOT materialized on the Codex adapter today.
# Codex's current per-agent TOML schema does not honor a `model = "..."`
# field at agent granularity (model selection happens at the Codex
# profile level). The reasoning_tier value in each TOML is declarative
# only — kept for forward compatibility if Codex adds per-agent model
# selection in the future. See core/rules/capabilities/reasoning-tier.md.

rm -rf "${PROJECT_ROOT}/.codex/hooks"
mkdir -p "${PROJECT_ROOT}/.codex/hooks"
copy_dir_contents "${AGENT_CREW_HOME}/hooks" "${PROJECT_ROOT}/.codex/hooks"

# Detect old flat layout and warn
if [ -d "${AGENT_CREW_HOME}/agents" ] && [ ! -L "${AGENT_CREW_HOME}/agents" ]; then
  printf '\n[agent-crew] NOTE: Legacy layout detected at %s/agents/\n' "${AGENT_CREW_HOME}"
  printf 'This directory is no longer used by crew. Files installed by crew have moved to system/.\n'
  printf 'If you have custom agents in %s/agents/, move them to %s/user/agents/\n' "${AGENT_CREW_HOME}" "${AGENT_CREW_HOME}"
  printf 'Then you can safely delete %s/agents/\n\n' "${AGENT_CREW_HOME}"
fi
chmod +x "${PROJECT_ROOT}/.codex/hooks/"*.sh 2>/dev/null || true
cp "${AGENT_CREW_HOME}/adapters/codex/invocation.md" "${PROJECT_ROOT}/.codex/invocation.md" 2>/dev/null || true
write_codex_hooks_json "${PROJECT_ROOT}/.codex/hooks.json" "${AGENT_CREW_HOME}"
install_codex_skills
merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${PROJECT_ROOT}/AGENTS.md"
register_local_git_excludes "${PROJECT_ROOT}" ".codex/" "AGENTS.md"

printf 'HOST: codex\n'
printf 'INSTALLED: %s\n' "${PROJECT_ROOT}/.codex"
