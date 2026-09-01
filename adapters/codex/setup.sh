#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
# AGENT_CREW_MODE: "install" (default) or "update". Update mode never prompts
# and never resets state; the copy operations below are idempotent in both
# modes (cp -R overwrites but does not delete extraneous files).
AGENT_CREW_MODE="${AGENT_CREW_MODE:-install}"
AGENT_CREW_PROJECT_LOCAL_ONLY="${AGENT_CREW_PROJECT_LOCAL_ONLY:-0}"

. "${AGENT_CREW_HOME}/setup/common.sh"

if [ -z "${SOURCE_ROOT:-}" ]; then
  _SOURCE_TOPLEVEL="$(git -C "${PROJECT_ROOT}" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "${_SOURCE_TOPLEVEL}" ] \
    && [ -d "${_SOURCE_TOPLEVEL}/core" ] \
    && [ -d "${_SOURCE_TOPLEVEL}/adapters" ]; then
    SOURCE_ROOT="${_SOURCE_TOPLEVEL}"
  fi
fi

if [ "${AGENT_CREW_MODE}" = "update" ]; then
  printf 'MODE: update (host=codex)\n'
fi

run_codex_shell_startup_preflight() {
  local diagnostics="${AGENT_CREW_HOME}/scripts/crew-diagnostics.py"
  local asset_root="${AGENT_CREW_HOME}"

  if [ ! -f "${diagnostics}" ] && [ -n "${SOURCE_ROOT:-}" ]; then
    diagnostics="${SOURCE_ROOT}/core/scripts/crew-diagnostics.py"
    asset_root="${SOURCE_ROOT}/core"
  fi
  [ -f "${diagnostics}" ] || return 0

  python3 "${diagnostics}" \
    --project-root "${PROJECT_ROOT}" \
    --asset-root "${asset_root}" \
    --agent-crew-home "${AGENT_CREW_HOME}" \
    shell-startup --format text || true
}

write_codex_hooks_json() {
  local dest="$1"
  local agent_crew_home="$2"

  python3 - "$dest" "$agent_crew_home" <<'PYEOF'
import json
import shlex
import sys
from pathlib import Path

dest = Path(sys.argv[1])
home = Path(sys.argv[2]).expanduser()
managed_names = {
    "guard-dangerous-commands.sh",
    "tracker-mutation-guard.sh",
    "context-guard.sh",
    "direct-edit-guard.sh",
    "post-tool-use-dispatcher.sh",
    "auto-issue-report.sh",
    "auto-route.sh",
}
managed_paths = {str(home / "hooks" / name) for name in managed_names}


def required_hooks():
    return {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": f"bash '{home}/hooks/guard-dangerous-commands.sh'", "timeout": 10}],
            },
            {
                "matcher": "mcp__plane__create_work_item|mcp__plane__update_work_item|mcp__plane__delete_work_item|mcp__plane__create_intake_work_item|mcp__plane__create_label|mcp__plane__create_work_item_comment|mcp__plane.create_work_item|mcp__plane.update_work_item|mcp__plane.delete_work_item|mcp__plane.create_intake_work_item|mcp__plane.create_label|mcp__plane.create_work_item_comment",
                "hooks": [{"type": "command", "command": f"bash '{home}/hooks/tracker-mutation-guard.sh'", "timeout": 10}],
            },
            {
                "matcher": "Agent",
                "hooks": [{"type": "command", "command": f"bash '{home}/hooks/context-guard.sh'", "timeout": 10}],
            },
            {
                "matcher": "Edit|Write|MultiEdit|apply_patch",
                "hooks": [{"type": "command", "command": f"bash '{home}/hooks/direct-edit-guard.sh'", "timeout": 10}],
            },
        ],
        "PostToolUse": [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": f"bash '{home}/hooks/post-tool-use-dispatcher.sh'", "timeout": 15}],
            },
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {"type": "command", "command": f"bash '{home}/hooks/auto-issue-report.sh'", "timeout": 10},
                    {"type": "command", "command": f"bash '{home}/hooks/auto-route.sh'", "timeout": 15},
                ]
            }
        ],
    }


def read_existing():
    if not dest.exists():
        return {}
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except Exception:
        print(
            f"[codex setup] ERROR: Refusing to overwrite non-object or malformed Codex hooks.json: {dest}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not isinstance(data, dict):
        print(
            f"[codex setup] ERROR: Refusing to overwrite non-object or malformed Codex hooks.json: {dest}",
            file=sys.stderr,
        )
        sys.exit(1)

    return data


def refuse_unsupported_schema(detail):
    print(
        f"[codex setup] ERROR: Refusing to overwrite unsupported Codex hooks.json schema: {dest} ({detail})",
        file=sys.stderr,
    )
    sys.exit(1)


def is_managed_hook(hook):
    if not isinstance(hook, dict):
        return False
    command = str(hook.get("command") or "")
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False

    return any(token in managed_paths for token in tokens)


def validate_required_event_schema(data, required):
    hooks = data.get("hooks")
    if hooks is None:
        return
    if not isinstance(hooks, dict):
        refuse_unsupported_schema("hooks must be an object")

    for event in required:
        if event not in hooks:
            continue
        blocks = hooks[event]
        if not isinstance(blocks, list):
            refuse_unsupported_schema(f"hooks.{event} must be a list")
        for block_index, block in enumerate(blocks):
            if not isinstance(block, dict):
                refuse_unsupported_schema(f"hooks.{event}[{block_index}] must be an object")
            block_hooks = block.get("hooks")
            if not isinstance(block_hooks, list):
                refuse_unsupported_schema(f"hooks.{event}[{block_index}].hooks must be a list")
            for hook_index, hook in enumerate(block_hooks):
                if not isinstance(hook, dict):
                    refuse_unsupported_schema(
                        f"hooks.{event}[{block_index}].hooks[{hook_index}] must be an object"
                    )


def prune_managed_hooks(data):
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        if hooks is None:
            data["hooks"] = {}
            return data
        refuse_unsupported_schema("hooks must be an object")

    for event, blocks in list(hooks.items()):
        if not isinstance(blocks, list):
            continue
        retained_blocks = []
        for block in blocks:
            if not isinstance(block, dict):
                retained_blocks.append(block)
                continue
            block_hooks = block.get("hooks")
            if not isinstance(block_hooks, list):
                retained_blocks.append(block)
                continue
            next_hooks = [hook for hook in block_hooks if not is_managed_hook(hook)]
            if next_hooks:
                next_block = dict(block)
                next_block["hooks"] = next_hooks
                retained_blocks.append(next_block)
        hooks[event] = retained_blocks
    return data


required = required_hooks()
settings = read_existing()
validate_required_event_schema(settings, required)
settings = prune_managed_hooks(settings)
hooks = settings.setdefault("hooks", {})
for event, blocks in required.items():
    current = hooks.setdefault(event, [])
    if not isinstance(current, list):
        refuse_unsupported_schema(f"hooks.{event} must be a list")
    current.extend(blocks)
dest.parent.mkdir(parents=True, exist_ok=True)
content = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
if not dest.exists() or dest.read_text(encoding="utf-8") != content:
    dest.write_text(content, encoding="utf-8")
PYEOF
}

merge_codex_config_toml() {
  local src="$1"
  local dest="$2"

  [ -f "${src}" ] || return 0
  mkdir -p "$(dirname "${dest}")"

  python3 - "${src}" "${dest}" <<'PYEOF'
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dest = Path(sys.argv[2])

section_re = re.compile(r"^\s*\[[^\]]+\]\s*(?:#.*)?$")


def split_lines(text: str) -> list[str]:
    return text.splitlines()


def section_bounds(lines: list[str], header: str):
    wanted = f"[{header}]"
    start = None
    for index, line in enumerate(lines):
        if line.strip().split("#", 1)[0].strip() == wanted:
            start = index
            break

    if start is None:
        return None

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if section_re.match(lines[index]):
            end = index
            break

    return start, end


def managed_section(template: str, header: str) -> list[str]:
    lines = split_lines(template)
    bounds = section_bounds(lines, header)
    if bounds is None:
        return []

    start, end = bounds
    return lines[start:end]


def assignment_key(line: str):
    code = line.split("#", 1)[0]
    if "=" not in code:
        return None
    key = code.split("=", 1)[0].strip()
    return key or None


template = src.read_text(encoding="utf-8")
managed_agents = managed_section(template, "agents")
managed_assignments = {}
for line in managed_agents[1:]:
    key = assignment_key(line)
    if key:
        managed_assignments[key] = line

if not dest.exists():
    output = template
else:
    existing = split_lines(dest.read_text(encoding="utf-8", errors="replace"))
    bounds = section_bounds(existing, "agents")
    if bounds is None:
        merged = existing[:]
        if merged and merged[-1].strip():
            merged.append("")
        merged.extend(managed_agents)
    else:
        start, end = bounds
        seen = set()
        section = existing[start:end]
        merged_section = section[:1]
        for line in section[1:]:
            key = assignment_key(line)
            if key in managed_assignments:
                merged_section.append(managed_assignments[key])
                seen.add(key)
            else:
                merged_section.append(line)
        for key, line in managed_assignments.items():
            if key not in seen:
                merged_section.append(line)
        merged = existing[:start] + merged_section + existing[end:]

    output = "\n".join(merged).rstrip("\n") + "\n"

if not dest.exists() or dest.read_text(encoding="utf-8", errors="replace") != output:
    dest.write_text(output, encoding="utf-8")
PYEOF
}

sync_codex_template_static() {
  local src="${AGENT_CREW_HOME}/adapters/codex/template"
  local dest="${CODEX_HOME}"
  [ -d "${src}" ] || return 0
  mkdir -p "${dest}"

  copy_file_if_changed "${src}/README.md" "${dest}/README.md"
  merge_codex_config_toml "${src}/config.toml" "${dest}/config.toml"
}

install_codex_skills() {
  local codex_home="${CODEX_HOME}"
  local skill_root="${AGENT_CREW_HOME}/adapters/codex/skill"
  local skill_src
  local skill_name
  local skill_dest
  local legacy_name

  if [ -n "${SOURCE_ROOT:-}" ] && [ -d "${SOURCE_ROOT}/adapters/codex/skill" ]; then
    skill_root="${SOURCE_ROOT}/adapters/codex/skill"
  fi

  [ -d "${skill_root}" ] || return 0
  mkdir -p "${codex_home}/skills"

  for legacy_name in \
    crew-agent-maker \
    crew-agent \
    crew-cost \
    crew-interact \
    crew-run \
    crew-sessions \
    crew-setup \
    crew-smm \
    crew-sync-instructions \
    crew-status \
    crew-task \
    crew-telemetry \
    crew-update \
    crew-workflow; do
    rm -rf "${codex_home}/skills/${legacy_name}"
  done

  rm -rf "${codex_home}/skills/agent-crew"

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
  local dest_dir="${CODEX_HOME}/agents"
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
legacy_system_marker = "Agent-crew system agent:"
for dest_path in sorted(dest_dir.glob("*.toml")):
    if dest_path.name in allowed:
        continue
    text = dest_path.read_text(encoding="utf-8", errors="replace")
    is_managed_system_agent = system_marker in text or legacy_system_marker in text
    if is_managed_system_agent:
        print(f"[install_system_agents_codex] Removing stale Codex agent: {dest_path.name}")
        dest_path.unlink()

for src_path in sorted(tmp_agents.glob("*.toml")):
    dest_path = dest_dir / src_path.name
    src_text = src_path.read_text(encoding="utf-8", errors="replace")
    if dest_path.exists():
        dest_text = dest_path.read_text(encoding="utf-8", errors="replace")
        if dest_text == src_text:
            continue
        is_managed_bootstrap = system_marker in dest_text or "Agent-crew system agent:" in dest_text
        if not is_managed_bootstrap:
            print(
                f"[install_system_agents_codex] WARNING: {dest_path.name} exists in global Codex agents and generated system agents; not auto-selected.",
                file=sys.stderr,
            )
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
#   model                = "<frontmatter model, optional; omit literal inherit>"
#   model_reasoning_effort = "<frontmatter model_reasoning_effort, optional>"
#   sandbox_mode         = "<frontmatter sandbox_mode, optional>"
#   developer_instructions = """<full markdown body after frontmatter>"""
#   name                   = "<agent name>"
#
# Output path: ${CODEX_HOME}/agents/<name>.toml
# Idempotent for generated TOML: managed user-agent TOMLs are refreshed on each
# setup/update run, and legacy generated TOMLs are upgraded to managed format.
# Project-owned same-name TOMLs are preserved and reported as skipped instead
# of being silently overwritten.
install_user_agents_codex() {
  local user_agents_dir="${AGENT_CREW_HOME}/user/agents"
  local dest_dir="${CODEX_HOME}/agents"

  [ -d "${user_agents_dir}" ] || return 0
  mkdir -p "${dest_dir}"

  python3 - "${user_agents_dir}" "${dest_dir}" "${AGENT_CREW_HOME}/system/agents" <<'PYEOF'
import os
import re
import sys

user_agents_dir = sys.argv[1]
dest_dir        = sys.argv[2]
system_agents_dir = sys.argv[3]

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

def parse_agent_name(path):
    try:
        text = open(path, encoding='utf-8').read()
    except OSError:
        return os.path.splitext(os.path.basename(path))[0]
    fm, _body = parse_frontmatter(text)
    return fm.get('name', '') or os.path.splitext(os.path.basename(path))[0]

def codex_agent_name(name):
    return re.sub(r'[^\w-]', '-', name.lower()).strip('-') or 'unknown'

def is_managed_user_toml(current, managed_marker, legacy_content):
    return current.startswith(managed_marker + '\n') or current == legacy_content

converted = 0
skipped   = []
system_names = set()
managed_user_marker = "# This is a Codex adapter bootstrap for an agent-crew user agent."

if os.path.isdir(system_agents_dir):
    for system_fname in sorted(os.listdir(system_agents_dir)):
        if not system_fname.endswith('.md') or system_fname.lower() == 'readme.md':
            continue
        system_names.add(codex_agent_name(parse_agent_name(os.path.join(system_agents_dir, system_fname))))

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
    if model.lower() == 'inherit':
        model = ''

    if not description:
        description = f'User agent: {name}'

    # Strip multi-line YAML value indicators from description if present
    description = description.lstrip('> ').strip()

    toml_name = codex_agent_name(name)
    if toml_name in system_names:
        skipped.append(f'{fname}: name conflicts with system agent; use crew agent --agent-layer user or --save-agent-layer user')
        continue
    dest_path = os.path.join(dest_dir, toml_name + '.toml')

    body_escaped = toml_escape(body.rstrip())
    # Escape description for single-line TOML string
    desc_escaped = description.replace('\\', '\\\\').replace('"', '\\"')

    lines = [
        managed_user_marker,
        f'name = "{toml_name}"',
        f'description = "{desc_escaped}"',
    ]
    # Preserve only official Codex per-agent config keys. `reasoning_tier` is
    # an agent-crew abstraction and is not accepted by Codex TOML agents.
    # `model: inherit` is a source-level host-default sentinel; Codex ChatGPT
    # accounts reject a literal `model = "inherit"` TOML value, so omit it.
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
    legacy_toml_content = '\n'.join(lines[1:]) + '\n'

    try:
        current = ''
        if os.path.exists(dest_path):
            with open(dest_path, encoding='utf-8') as f:
                current = f.read()
        if current != toml_content:
            if current and not is_managed_user_toml(current, managed_user_marker, legacy_toml_content):
                skipped.append(f'{fname}: {toml_name}.toml exists in global Codex agents and generated user agents; not auto-selected')
                continue
            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(toml_content)
        converted += 1
    except OSError as e:
        skipped.append(f'{fname}: write error ({e})')

print(f'[install_user_agents_codex] {converted} agent(s) converted to TOML in {dest_dir}')
if skipped:
    for s in skipped:
        print(f'[install_user_agents_codex] SKIP: {s}', file=sys.stderr)
PYEOF
}

if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ]; then
  sync_codex_template_static
fi

if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ]; then
  chmod +x "${AGENT_CREW_HOME}/adapters/codex/bin/"* 2>/dev/null || true
  chmod +x "${AGENT_CREW_HOME}/system/adapters/codex/bin/"* 2>/dev/null || true
fi

# Note: reasoning_tier is an agent-crew abstraction. Codex system agents map it
# to official per-agent `model` and `model_reasoning_effort` keys while user
# agents may still provide explicit `model`, `model_reasoning_effort`, and
# `sandbox_mode` keys in frontmatter. See core/rules/capabilities/reasoning-tier.md.

if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ] && [ -n "${SOURCE_ROOT:-}" ] && [ -d "${SOURCE_ROOT}/core/hooks" ]; then
  diff_install "${SOURCE_ROOT}/core/hooks" "${AGENT_CREW_HOME}/system/hooks"
  diff_install "${SOURCE_ROOT}/core/hooks" "${AGENT_CREW_HOME}/hooks"
  chmod +x "${AGENT_CREW_HOME}/system/hooks/"*.sh "${AGENT_CREW_HOME}/hooks/"*.sh 2>/dev/null || true
fi
if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ] && [ -n "${SOURCE_ROOT:-}" ] && [ -d "${SOURCE_ROOT}/core/scripts" ]; then
  diff_install "${SOURCE_ROOT}/core/scripts" "${AGENT_CREW_HOME}/system/scripts"
  diff_install "${SOURCE_ROOT}/core/scripts" "${AGENT_CREW_HOME}/scripts"
  chmod +x "${AGENT_CREW_HOME}/system/scripts/"*.sh "${AGENT_CREW_HOME}/system/scripts/"*.py 2>/dev/null || true
  chmod +x "${AGENT_CREW_HOME}/scripts/"*.sh "${AGENT_CREW_HOME}/scripts/"*.py 2>/dev/null || true
fi

# Detect old flat layout and safely clean managed duplicates.
if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ] && [ -d "${AGENT_CREW_HOME}/agents" ] && [ ! -L "${AGENT_CREW_HOME}/agents" ]; then
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
if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ]; then
  mkdir -p "${CODEX_HOME}"
  copy_file_if_changed "${AGENT_CREW_HOME}/adapters/codex/invocation.md" "${CODEX_HOME}/agent-crew/invocation.md"
  write_codex_hooks_json "${CODEX_HOME}/hooks.json" "${AGENT_CREW_HOME}"
  install_codex_skills
fi
install_system_agents_codex
install_user_agents_codex

# Scaffold skill directories (idempotent)
if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ]; then
  mkdir -p "${AGENT_CREW_HOME}/system/skills"
  mkdir -p "${AGENT_CREW_HOME}/user/skills"
  mkdir -p "${AGENT_CREW_HOME}/skills"
  mkdir -p "${CODEX_HOME}/agent-crew/skills"
fi

# Write user/skills README placeholder before merging/copying so generated
# discovery mirrors are stable within the same setup/update run.
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

# Copy unified skills to Codex host discovery path
if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ]; then
  sync_dir_contents_prune "${AGENT_CREW_HOME}/skills" "${CODEX_HOME}/agent-crew/skills"
fi

# Write host capability flags so the core pipeline can read them at Phase 0.
# Codex setup installs native command skills, agents, hooks, and config in the
# Codex global home. The runtime capability flags below describe what
# agent-crew can call directly from its provider-neutral workflow. Tool-backed
# Codex sessions may not expose a callable background subagent or task lifecycle
# surface to agent-crew, so these flags remain false until that surface is
# available in the active adapter.
# Schema documented at core/rules/host-capabilities.md.
# Absence of this file MUST be treated as legacy behavior (all flags false),
# so writing it explicitly here closes the documentation-implementation gap
# described in issue #51.
if declare -F project_state_load >/dev/null 2>&1; then
  project_state_load \
    --agent-crew-home "${AGENT_CREW_HOME}" \
    --project-root "${PROJECT_ROOT}" \
    --ensure \
    --migrate-legacy
else
  PROJECT_NAME="$(basename "${PROJECT_ROOT}")"
  PROJECT_STATE_KEY="${PROJECT_NAME}"
  STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
fi
CAPABILITIES_FILE="${STATE_DIR}/capabilities.json"
if [ "${AGENT_CREW_WRITE_CAPABILITIES:-1}" != "0" ]; then
  mkdir -p "${STATE_DIR}"
  cat > "${CAPABILITIES_FILE}" <<'CAPS_EOF'
{
  "host": "codex",
  "agent_background": false,
  "task_tools": false,
  "interactive_question": false,
  "interactive_question_mode": "codex_plan_mode_conditional",
  "interactive_question_surface": "request_user_input",
  "interactive_question_fallback": "structured_markdown",
  "monitor_tool": false,
  "cost_tracking": false,
  "hook_system": false
}
CAPS_EOF
fi

printf 'HOST: codex\n'
printf 'INSTALLED: %s\n' "${CODEX_HOME}"
printf 'CAPABILITIES: %s\n' "${CAPABILITIES_FILE}"
run_codex_shell_startup_preflight
