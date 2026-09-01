#!/usr/bin/env bash
# update-global-adapters.sh
#
# Phase (a) of the crew:update Step 4 split (P5):
#   Refresh all *global-scope* adapter paths that are installed on this
#   machine, without requiring PROJECT_ROOT context.
#
# This script is deliberately separate from setup-host.sh so that update.md
# can call it unconditionally before any host-specific compatibility pass. It only
# touches paths that are safe to re-copy regardless of the current working
# directory:
#
#   - Claude:  ~/.claude/agent-crew/  (via install_claude_compat)
#   - Codex:   ~/.codex/skills/crew:<intent>/  (native Codex command skills)
#              ~/.codex/agent-crew/skills/     (internal agent-crew guide mirror,
#                                               not the native Codex skill dir)
#
# Generic has no machine-global adapter payload beyond the native `crew`
# command entrypoint and is not handled here.
#
# Usage (from update.md Step 4a):
#   AGENT_CREW_MODE=update SOURCE_ROOT="${SOURCE_ROOT}" \
#     bash "${AGENT_CREW_HOME}/scripts/update-global-adapters.sh"
#
# Environment variables consumed:
#   AGENT_CREW_HOME   — ~/.agent-crew unless overridden
#   AGENT_CREW_MODE   — should be "update" when called from crew:update
#   SOURCE_ROOT       — root of the agent-crew source repo (contains core/ and adapters/)
#   CLAUDE_DIR        — ~/.claude unless overridden
#   CODEX_HOME        — ~/.codex unless overridden

set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
AGENT_CREW_MODE="${AGENT_CREW_MODE:-update}"
export AGENT_CREW_MODE

CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"

# Resolve source root: update.md passes the fresh remote checkout in SOURCE_ROOT.
if [ -z "${SOURCE_ROOT:-}" ]; then
  printf '[update-global-adapters] WARNING: SOURCE_ROOT not set.\n' >&2
  printf '  Skipping global adapter update. crew:update must set SOURCE_ROOT from the remote checkout.\n' >&2
  exit 0
fi

SOURCE_DIR="${SOURCE_ROOT}/core"
ADAPTERS_DIR="${SOURCE_ROOT}/adapters"

if [ ! -d "${SOURCE_DIR}" ] || [ ! -d "${ADAPTERS_DIR}" ]; then
  printf '[update-global-adapters] WARNING: SOURCE_DIR or ADAPTERS_DIR missing under %s.\n' "${SOURCE_ROOT}" >&2
  printf '  Skipping global adapter update.\n' >&2
  exit 0
fi

# Source install.sh helpers so we can reuse install_claude_compat,
# install_codex_bootstrap_skill, merge_global_settings, etc.
# We source rather than call install.sh as a subprocess to avoid re-running
# install_global (which would trigger the "already installed" prompt path).
# shellcheck source=/dev/null
. "${SOURCE_ROOT}/install.sh" 2>/dev/null || {
  # Fallback: if sourcing fails (e.g. install.sh exits early on the
  # "already installed" branch under some shells), define minimal stubs so
  # the Codex global path copy below can still run.
  log_info()  { printf '[✓] %s\n' "$1"; }
  log_warn()  { printf '[!] %s\n' "$1"; }
}

printf '[update-global-adapters] Refreshing global adapter paths (MODE: %s)\n' "${AGENT_CREW_MODE}"

# Refresh globally installed hooks before adapter-specific updates. Hook
# payloads are runtime behavior, so stale ~/.agent-crew/hooks/*.sh can keep
# emitting old routing directives even after source fixes have landed.
if [ -d "${SOURCE_DIR}/hooks" ]; then
  mkdir -p "${AGENT_CREW_HOME}/system/hooks" "${AGENT_CREW_HOME}/hooks"
  cp -f "${SOURCE_DIR}/hooks/"*.sh "${AGENT_CREW_HOME}/system/hooks/" 2>/dev/null || true
  cp -f "${SOURCE_DIR}/hooks/"*.sh "${AGENT_CREW_HOME}/hooks/" 2>/dev/null || true
  chmod +x "${AGENT_CREW_HOME}/system/hooks/"*.sh "${AGENT_CREW_HOME}/hooks/"*.sh 2>/dev/null || true
  printf '[update-global-adapters] Global hooks refreshed → %s/hooks\n' "${AGENT_CREW_HOME}"
fi

# ── Claude global paths ───────────────────────────────────────────────────────
if [ -d "${CLAUDE_DIR}/agent-crew" ]; then
  printf '[update-global-adapters] Updating Claude global paths → %s/agent-crew/\n' "${CLAUDE_DIR}"
  AGENT_CREW_HOST=claude AGENT_CREW_MODE="${AGENT_CREW_MODE}" SOURCE_ROOT="${SOURCE_ROOT}" \
    bash "${AGENT_CREW_HOME}/setup/setup-host.sh" "$(pwd)" >/dev/null 2>&1 || \
    printf '[update-global-adapters] WARNING: Claude adapter returned non-zero (continuing)\n' >&2
else
  printf '[update-global-adapters] Skipping Claude update — not installed (%s/agent-crew does not exist)\n' "${CLAUDE_DIR}"
fi

# ── Codex global paths ────────────────────────────────────────────────────────
CODEX_NATIVE_SKILLS_DIR="${CODEX_HOME}/skills"
CODEX_CREW_SKILLS_DIR="${CODEX_HOME}/agent-crew/skills"
CODEX_AGENTS_DIR="${CODEX_HOME}/agents"
CODEX_AGENT_GENERATOR="${SOURCE_DIR}/scripts/generate-codex-system-agents.py"
CODEX_USER_AGENT_GENERATOR="${SOURCE_DIR}/scripts/generate-codex-user-agents.py"
CODEX_TEMPLATE_DIR="${ADAPTERS_DIR}/codex/template"

prune_and_copy_dir() {
  local src="$1" dest="$2"
  [ -d "${src}" ] || return 0
  mkdir -p "${dest}"

  while IFS= read -r -d '' dest_file; do
    local rel
    rel="${dest_file#"${dest}/"}"
    if [ ! -e "${src}/${rel}" ]; then
      printf '[update-global-adapters] Removing stale Codex global file: %s/%s\n' "${dest}" "${rel}"
      rm -f "${dest_file}"
    fi
  done < <(find "${dest}" -type f -print0 2>/dev/null)

  cp -R "${src}/." "${dest}/"
}

prune_legacy_codex_dash_skills() {
  local dest="$1"
  local legacy_name
  [ -d "${dest}" ] || return 0

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
    rm -rf "${dest}/${legacy_name}"
  done

  rm -rf "${dest}/agent-crew"
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
            f"[update-global-adapters] ERROR: Refusing to overwrite non-object or malformed Codex hooks.json: {dest}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not isinstance(data, dict):
        print(
            f"[update-global-adapters] ERROR: Refusing to overwrite non-object or malformed Codex hooks.json: {dest}",
            file=sys.stderr,
        )
        sys.exit(1)

    return data


def refuse_unsupported_schema(detail):
    print(
        f"[update-global-adapters] ERROR: Refusing to overwrite unsupported Codex hooks.json schema: {dest} ({detail})",
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

sync_codex_managed_agents() {
  local src="$1" dest="$2"
  [ -d "${src}" ] || return 0
  mkdir -p "${dest}"

  python3 - "${src}" "${dest}" <<'PYEOF'
import shutil
import sys
from pathlib import Path

src = Path(sys.argv[1])
dest = Path(sys.argv[2])

system_marker = "This is a Codex adapter bootstrap for the agent-crew system agent."
legacy_marker = "Agent-crew system agent:"
user_marker = "# This is a Codex adapter bootstrap for an agent-crew user agent."
src_names = {path.name for path in src.glob("*.toml")}

for dest_path in sorted(dest.glob("*.toml")):
    if dest_path.name in src_names:
        continue
    text = dest_path.read_text(encoding="utf-8", errors="replace")
    managed = system_marker in text or legacy_marker in text
    if managed:
        print(f"[update-global-adapters] Removing stale Codex global agent: {dest_path.name}")
        dest_path.unlink()

for src_path in sorted(src.glob("*.toml")):
    dest_path = dest / src_path.name
    src_text = src_path.read_text(encoding="utf-8")
    if dest_path.exists():
        dest_text = dest_path.read_text(encoding="utf-8", errors="replace")
        if dest_text == src_text:
            continue
        agent_crew_owned = (
            system_marker in dest_text
            or legacy_marker in dest_text
            or dest_text.startswith(user_marker + "\n")
        )
        if not agent_crew_owned:
            print(
                f"[update-global-adapters] WARNING: {dest_path.name} exists in global Codex agents and generated system agents; not auto-selected.",
                file=sys.stderr,
            )
            continue
    shutil.copyfile(src_path, dest_path)
PYEOF
}

mkdir -p "${CODEX_NATIVE_SKILLS_DIR}"
printf '[update-global-adapters] Updating Codex native command skills → %s\n' "${CODEX_NATIVE_SKILLS_DIR}"
prune_legacy_codex_dash_skills "${CODEX_NATIVE_SKILLS_DIR}"
if [ -d "${ADAPTERS_DIR}/codex/skill" ]; then
  for skill_src in "${ADAPTERS_DIR}/codex/skill"/*; do
    [ -d "${skill_src}" ] || continue
    skill_name="$(basename "${skill_src}")"
    prune_and_copy_dir "${skill_src}" "${CODEX_NATIVE_SKILLS_DIR}/${skill_name}"
  done
  printf '[update-global-adapters] Codex native command skills refreshed → %s\n' "${CODEX_NATIVE_SKILLS_DIR}"
fi

mkdir -p "${CODEX_HOME}/agent-crew"
if [ -d "${CODEX_TEMPLATE_DIR}" ]; then
  cp -f "${CODEX_TEMPLATE_DIR}/README.md" "${CODEX_HOME}/README.md" 2>/dev/null || true
  merge_codex_config_toml "${CODEX_TEMPLATE_DIR}/config.toml" "${CODEX_HOME}/config.toml"
fi
cp -f "${ADAPTERS_DIR}/codex/invocation.md" "${CODEX_HOME}/agent-crew/invocation.md" 2>/dev/null || true
write_codex_hooks_json "${CODEX_HOME}/hooks.json" "${AGENT_CREW_HOME}"
printf '[update-global-adapters] Codex global hooks/config refreshed → %s\n' "${CODEX_HOME}"

mkdir -p "${CODEX_CREW_SKILLS_DIR}"
printf '[update-global-adapters] Updating Codex crew-skills mirror → %s\n' "${CODEX_CREW_SKILLS_DIR}"
if [ -d "${AGENT_CREW_HOME}/skills" ]; then
  prune_and_copy_dir "${AGENT_CREW_HOME}/skills" "${CODEX_CREW_SKILLS_DIR}"
  printf '[update-global-adapters] Codex crew-skills mirror refreshed → %s\n' "${CODEX_CREW_SKILLS_DIR}"
fi

if [ -d "${ADAPTERS_DIR}/codex/template/agents" ]; then
  printf '[update-global-adapters] Updating Codex global agents → %s\n' "${CODEX_AGENTS_DIR}"
  if [ -f "${CODEX_AGENT_GENERATOR}" ]; then
    tmp_agents="$(mktemp -d)"
    python3 "${CODEX_AGENT_GENERATOR}" \
      "${SOURCE_DIR}/agents" \
      "${tmp_agents}" \
      --source-ref-root "${AGENT_CREW_HOME}/system/agents" >/dev/null
    sync_codex_managed_agents "${tmp_agents}" "${CODEX_AGENTS_DIR}"
    rm -rf "${tmp_agents}"
  else
    printf '[update-global-adapters] WARNING: Codex agent generator not found at %s; falling back to static templates.\n' "${CODEX_AGENT_GENERATOR}" >&2
    sync_codex_managed_agents "${ADAPTERS_DIR}/codex/template/agents" "${CODEX_AGENTS_DIR}"
  fi
  if [ -f "${CODEX_USER_AGENT_GENERATOR}" ] && [ -d "${AGENT_CREW_HOME}/user/agents" ]; then
    python3 "${CODEX_USER_AGENT_GENERATOR}" \
      "${AGENT_CREW_HOME}/user/agents" \
      "${CODEX_AGENTS_DIR}" \
      --system-agents-dir "${AGENT_CREW_HOME}/system/agents"
  else
    printf '[update-global-adapters] WARNING: Codex user-agent generator or user agent source not found; skipping user agents.\n' >&2
  fi
  printf '[update-global-adapters] Codex global agents refreshed → %s\n' "${CODEX_AGENTS_DIR}"
else
  printf '[update-global-adapters] Skipping Codex global agents — source not found at %s/codex/template/agents\n' "${ADAPTERS_DIR}" >&2
fi

printf '[update-global-adapters] Global adapter refresh complete.\n'
