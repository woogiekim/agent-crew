#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
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
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"bash '{home}/hooks/auto-issue-report.sh'",
                        "timeout": 10,
                    }
                ],
            },
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
                        "command": f"bash '{home}/hooks/auto-issue-report.sh'",
                        "timeout": 10,
                    },
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
content = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
if not dest.exists() or dest.read_text(encoding="utf-8") != content:
    dest.write_text(content, encoding="utf-8")
PYEOF
}

sync_codex_template_static() {
  local src="${AGENT_CREW_HOME}/adapters/codex/template"
  local dest="${PROJECT_ROOT}/.codex"
  [ -d "${src}" ] || return 0
  mkdir -p "${dest}"

  copy_file_if_changed "${src}/README.md" "${dest}/README.md"
  copy_file_if_changed "${src}/config.toml" "${dest}/config.toml"
}

install_codex_skills() {
  local codex_home="${CODEX_HOME}"
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

  local tmp_agents
  tmp_agents="$(mktemp -d)"
  python3 "${generator}" "${system_agents_dir}" "${tmp_agents}" >/dev/null
  printf '[generate-codex-system-agents] %s system agent(s) converted to TOML in %s\n' \
    "$(find "${tmp_agents}" -maxdepth 1 -name '*.toml' 2>/dev/null | wc -l | tr -d ' ')" \
    "${dest_dir}"
  python3 - "${tmp_agents}" "${dest_dir}" "${AGENT_CREW_HOME}/user/agents" <<'PYEOF'
import re
import shutil
import sys
from pathlib import Path

tmp_agents = Path(sys.argv[1])
dest_dir = Path(sys.argv[2])
user_agents_dir = Path(sys.argv[3])

def parse_user_toml_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    name = path.stem
    if match:
        for line in match.group(1).splitlines():
            kv = re.match(r'^(\w[\w_-]*):\s*(.*)', line)
            if kv and kv.group(1) == "name":
                name = kv.group(2).strip().strip('"\'') or name
                break
    return re.sub(r'[^\w-]', '-', name.lower()).strip('-') or 'unknown'

dest_dir.mkdir(parents=True, exist_ok=True)
system_names = {path.name for path in tmp_agents.glob("*.toml")}
user_names = set()
if user_agents_dir.is_dir():
    for path in user_agents_dir.glob("*.md"):
        if path.name.lower() == "readme.md":
            continue
        user_names.add(parse_user_toml_name(path) + ".toml")

allowed = system_names | user_names
system_marker = "This is a Codex adapter bootstrap for the agent-crew system agent."
legacy_system_names = {
    "analyst.toml",
    "backend.toml",
    "designer.toml",
    "devops.toml",
    "documenter.toml",
    "frontend.toml",
    "historian.toml",
    "issuer.toml",
    "korean-normalizer.toml",
    "learning-mentor.toml",
    "planner.toml",
    "requirements.toml",
    "resolver.toml",
    "reviewer.toml",
    "supervisor.toml",
    "test-writer.toml",
}
for dest_path in sorted(dest_dir.glob("*.toml")):
    if dest_path.name in allowed:
        continue
    text = dest_path.read_text(encoding="utf-8", errors="replace")
    is_managed_system_agent = system_marker in text or dest_path.name in legacy_system_names
    if is_managed_system_agent:
        print(f"[install_system_agents_codex] Removing stale Codex agent: {dest_path.name}")
        dest_path.unlink()

for src_path in sorted(tmp_agents.glob("*.toml")):
    dest_path = dest_dir / src_path.name
    if dest_path.exists() and dest_path.read_text(encoding="utf-8", errors="replace") == src_path.read_text(encoding="utf-8"):
        continue
    shutil.copyfile(src_path, dest_path)
PYEOF
  rm -rf "${tmp_agents}"
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
        current = ''
        if os.path.exists(dest_path):
            with open(dest_path, encoding='utf-8') as f:
                current = f.read()
        if current != toml_content:
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

sync_codex_template_static

chmod +x "${AGENT_CREW_HOME}/adapters/codex/bin/"* 2>/dev/null || true
chmod +x "${AGENT_CREW_HOME}/system/adapters/codex/bin/"* 2>/dev/null || true

# Note: reasoning_tier is an agent-crew abstraction. Codex system agents map it
# to the official `model_reasoning_effort` key (`xhigh`, `high`, `medium`,
# `low`) while user agents may still provide explicit `model`,
# `model_reasoning_effort`, and `sandbox_mode` keys in frontmatter. We do not
# auto-map the abstract tier to a concrete model because model availability is
# operator- and profile-specific. See core/rules/capabilities/reasoning-tier.md.

sync_dir_contents_prune "${AGENT_CREW_HOME}/hooks" "${PROJECT_ROOT}/.codex/hooks"

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
chmod +x "${PROJECT_ROOT}/.codex/hooks/"*.sh 2>/dev/null || true
copy_file_if_changed "${AGENT_CREW_HOME}/adapters/codex/invocation.md" "${PROJECT_ROOT}/.codex/invocation.md"
write_codex_hooks_json "${PROJECT_ROOT}/.codex/hooks.json" "${AGENT_CREW_HOME}"
install_codex_skills
install_system_agents_codex
install_user_agents_codex

# Scaffold skill directories (idempotent)
mkdir -p "${AGENT_CREW_HOME}/system/skills"
mkdir -p "${AGENT_CREW_HOME}/user/skills"
mkdir -p "${AGENT_CREW_HOME}/skills"
mkdir -p "${CODEX_HOME}/agent-crew/skills"

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
sync_dir_contents_prune "${AGENT_CREW_HOME}/skills" "${CODEX_HOME}/agent-crew/skills"

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
