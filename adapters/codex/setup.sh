#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

. "${AGENT_CREW_HOME}/setup/common.sh"

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

copy_dir_contents "${AGENT_CREW_HOME}/adapters/codex/template" "${PROJECT_ROOT}/.codex"
rm -rf "${PROJECT_ROOT}/.codex/hooks"
mkdir -p "${PROJECT_ROOT}/.codex/hooks"
copy_dir_contents "${AGENT_CREW_HOME}/hooks" "${PROJECT_ROOT}/.codex/hooks"
chmod +x "${PROJECT_ROOT}/.codex/hooks/"*.sh 2>/dev/null || true
cp "${AGENT_CREW_HOME}/adapters/codex/invocation.md" "${PROJECT_ROOT}/.codex/invocation.md" 2>/dev/null || true
write_codex_hooks_json "${PROJECT_ROOT}/.codex/hooks.json" "${AGENT_CREW_HOME}"
merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${PROJECT_ROOT}/AGENTS.md"
register_local_git_excludes "${PROJECT_ROOT}" ".codex/" "AGENTS.md"

printf 'HOST: codex\n'
printf 'INSTALLED: %s\n' "${PROJECT_ROOT}/.codex"
