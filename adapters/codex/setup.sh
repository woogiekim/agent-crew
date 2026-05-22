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
            {
                "matcher": "Edit|Write|MultiEdit|apply_patch",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash '{home}/hooks/direct-edit-guard.sh'",
                    }
                ],
            },
        ],
        "PostToolUse": [
            {
                "matcher": "Edit|Write|MultiEdit|apply_patch",
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

install_system_agents_codex() {
  local system_agents_dir="${AGENT_CREW_HOME}/system/agents"
  local dest_dir="${PROJECT_ROOT}/.codex/agents"
  local generator=""

  [ -d "${system_agents_dir}" ] || return 0
  mkdir -p "${dest_dir}"

  for candidate in \
    "${AGENT_CREW_HOME}/scripts/generate-codex-system-agents.py" \
    "${AGENT_CREW_HOME}/system/scripts/generate-codex-system-agents.py" \
    "${SOURCE_ROOT:-}/core/scripts/generate-codex-system-agents.py"; do
    if [ -n "${candidate}" ] && [ -f "${candidate}" ]; then
      generator="${candidate}"
      break
    fi
  done

  if [ -z "${generator}" ]; then
    printf '[install_system_agents_codex] ERROR: generator not found; cannot install system agent TOMLs.\n' >&2
    return 1
  fi

  python3 "${generator}" "${system_agents_dir}" "${dest_dir}"
}

# install_user_agents_codex — convert user agent .md files to Codex TOML stubs.
#
# Each .md file in user/agents/ is expected to have a YAML frontmatter block at
# the top (between --- delimiters) containing at minimum:
#   name:        agent name (used as the TOML filename stem)
#   description: one-line trigger/skip/output description
#
# The generated TOML stub uses the backend.toml shape:
#   description          = "<frontmatter description>"
#   model                = "<frontmatter model, optional>"
#   model_reasoning_effort = "<frontmatter model_reasoning_effort, optional>"
#   sandbox_mode         = "<frontmatter sandbox_mode, optional>"
#   developer_instructions = """<full markdown body after frontmatter>"""
#   name                   = "<agent name>"
#
# Output path: ${PROJECT_ROOT}/.codex/agents/<name>.toml
# Idempotent: existing TOML files are overwritten on each setup/update run so
# user/agents/ changes are always reflected after crew:setup or crew:update.
install_user_agents_codex() {
  local user_agents_dir="${AGENT_CREW_HOME}/user/agents"
  local dest_dir="${PROJECT_ROOT}/.codex/agents"

  [ -d "${user_agents_dir}" ] || return 0
  mkdir -p "${dest_dir}"

  python3 - "${user_agents_dir}" "${dest_dir}" <<'PYEOF'
import os
import re
import sys

user_agents_dir = sys.argv[1]
dest_dir        = sys.argv[2]

def parse_frontmatter(text):
    """Return (frontmatter_dict, body_text). Tolerates missing frontmatter."""
    fm = {}
    body = text
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
    if m:
        fm_text = m.group(1)
        body    = m.group(2)
        # Parse simple key: value pairs (value may be multi-line with >, |)
        for line in fm_text.splitlines():
            kv = re.match(r'^(\w[\w_-]*):\s*(.*)', line)
            if kv:
                key, val = kv.group(1), kv.group(2).strip().strip('"\'')
                # Strip YAML block-scalar indicators
                if val in ('>', '|', '>-', '|-'):
                    val = ''
                fm[key] = val
    return fm, body

def toml_escape(s):
    """Escape a string for use inside TOML triple-quoted basic string."""
    # Escape backslashes first, then any sequence that would close the TOML
    # triple-quoted string.
    s = s.replace('\\', '\\\\')
    # Escape triple-double-quotes by inserting a backslash-escaped char
    s = s.replace('"""', '""\\"')
    return s

converted = 0
skipped   = []

for fname in sorted(os.listdir(user_agents_dir)):
    if not fname.endswith('.md'):
        continue
    if fname.lower() == 'readme.md':
        continue

    md_path = os.path.join(user_agents_dir, fname)
    try:
        text = open(md_path, encoding='utf-8').read()
    except OSError as e:
        skipped.append(f'{fname}: read error ({e})')
        continue

    fm, body = parse_frontmatter(text)

    name = fm.get('name', '') or os.path.splitext(fname)[0]
    description = fm.get('description', '').strip()
    model = fm.get('model', '').strip()
    model_reasoning_effort = fm.get('model_reasoning_effort', '').strip()
    sandbox_mode = fm.get('sandbox_mode', '').strip()
    nickname_candidates = fm.get('nickname_candidates', '').strip()

    if not description:
        description = f'User agent: {name}'

    # Strip multi-line YAML value indicators from description if present
    description = description.lstrip('> ').strip()

    toml_name = re.sub(r'[^\w-]', '-', name.lower()).strip('-') or 'unknown'
    dest_path = os.path.join(dest_dir, toml_name + '.toml')

    body_escaped = toml_escape(body.rstrip())
    # Escape description for single-line TOML string
    desc_escaped = description.replace('\\', '\\\\').replace('"', '\\"')

    lines = [
        f'name = "{toml_name}"',
        f'description = "{desc_escaped}"',
    ]
    # Preserve only official Codex per-agent config keys. `reasoning_tier` is
    # an agent-crew abstraction and is not accepted by Codex TOML agents.
    for key, value in (
        ('model', model),
        ('model_reasoning_effort', model_reasoning_effort),
        ('sandbox_mode', sandbox_mode),
    ):
        if value:
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    if nickname_candidates:
        # Accept either a TOML-ish inline list or a comma-separated shorthand.
        if nickname_candidates.startswith('[') and nickname_candidates.endswith(']'):
            lines.append(f'nickname_candidates = {nickname_candidates}')
        else:
            names = [
                x.strip().strip('"\'')
                for x in nickname_candidates.split(',')
                if x.strip()
            ]
            encoded = ', '.join(
                '"' + n.replace('\\', '\\\\').replace('"', '\\"') + '"'
                for n in names
            )
            lines.append(f'nickname_candidates = [{encoded}]')
    lines.append(f'developer_instructions = """\n{body_escaped}\n"""')
    toml_content = '\n'.join(lines) + '\n'

    try:
        with open(dest_path, 'w', encoding='utf-8') as f:
            f.write(toml_content)
        converted += 1
    except OSError as e:
        skipped.append(f'{fname}: write error ({e})')

print(f'[install_user_agents_codex] {converted} agent(s) converted to TOML in {dest_dir}')
if skipped:
    for s in skipped:
        print(f'[install_user_agents_codex] SKIP: {s}')
PYEOF
}

sync_dir_contents_prune "${AGENT_CREW_HOME}/adapters/codex/template" "${PROJECT_ROOT}/.codex"

# Note: reasoning_tier is an agent-crew abstraction. Codex native custom
# agents honor official per-agent TOML keys such as `model`,
# `model_reasoning_effort`, and `sandbox_mode`; user agents may provide those
# keys in frontmatter and this adapter preserves them. We do not auto-map the
# abstract tier to a concrete model because model availability is operator- and
# profile-specific. See core/rules/capabilities/reasoning-tier.md.

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
install_system_agents_codex
install_user_agents_codex

# Scaffold skill directories (idempotent)
mkdir -p "${AGENT_CREW_HOME}/system/skills"
mkdir -p "${AGENT_CREW_HOME}/user/skills"
mkdir -p "${AGENT_CREW_HOME}/skills"
mkdir -p "${HOME}/.codex/agent-crew/skills"

# Sync system skills from source repo when SOURCE_ROOT is available
if [ -n "${SOURCE_ROOT:-}" ] && [ -d "${SOURCE_ROOT}/core/agents/skills" ]; then
  sync_system_skills \
    "${SOURCE_ROOT}/core/agents/skills" \
    "${AGENT_CREW_HOME}/system/skills"
fi

# Merge system + user skills into unified discovery path
merge_skills_to_discovery \
  "${AGENT_CREW_HOME}/system/skills" \
  "${AGENT_CREW_HOME}/user/skills" \
  "${AGENT_CREW_HOME}/skills"

# Copy unified skills to Codex host discovery path
sync_dir_contents_prune "${AGENT_CREW_HOME}/skills" "${HOME}/.codex/agent-crew/skills"

# Write user/skills README placeholder (idempotent)
if [ ! -f "${AGENT_CREW_HOME}/user/skills/README.md" ]; then
  cat > "${AGENT_CREW_HOME}/user/skills/README.md" << 'UEOF'
# User Skills

Place your custom skill definitions here.
Files in this directory are NEVER overwritten by crew:update.
UEOF
fi

merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${PROJECT_ROOT}/AGENTS.md"
register_local_git_excludes "${PROJECT_ROOT}" ".codex/" "AGENTS.md"

# Write host capability flags so the core pipeline can read them at Phase 0.
# Codex project setup installs native subagent TOMLs and project-local
# `.codex/config.toml`, but the runtime capability flags below describe what
# agent-crew can call directly from its provider-neutral workflow. Tool-backed
# Codex sessions may not expose a callable background subagent or task lifecycle
# surface to agent-crew, so these flags remain false until that surface is
# available in the active adapter.
# Schema documented at core/rules/host-capabilities.md.
# Absence of this file MUST be treated as legacy behavior (all flags false),
# so writing it explicitly here closes the documentation-implementation gap
# described in issue #51.
PROJECT_NAME="$(basename "${PROJECT_ROOT}")"
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
CAPABILITIES_FILE="${STATE_DIR}/capabilities.json"
if [ "${AGENT_CREW_WRITE_CAPABILITIES:-1}" != "0" ]; then
  mkdir -p "${STATE_DIR}"
  cat > "${CAPABILITIES_FILE}" <<'CAPS_EOF'
{
  "host": "codex",
  "agent_background": false,
  "task_tools": false,
  "interactive_question": false,
  "monitor_tool": false,
  "cost_tracking": false,
  "hook_system": false
}
CAPS_EOF
fi

printf 'HOST: codex\n'
printf 'INSTALLED: %s\n' "${PROJECT_ROOT}/.codex"
printf 'CAPABILITIES: %s\n' "${CAPABILITIES_FILE}"
