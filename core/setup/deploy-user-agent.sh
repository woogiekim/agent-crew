#!/usr/bin/env bash
# deploy-user-agent.sh — propagate a newly created user agent to all installed
# host adapter discovery paths.
#
# Usage:
#   bash deploy-user-agent.sh <agent-filename>
#   bash deploy-user-agent.sh my-agent.md
#
# Called automatically by crew:agent-maker after writing a new agent to
# ~/.agent-crew/user/agents/<name>.md. Enumerates all installed host adapters
# and installs the agent into each one's discovery path.
#
# Adapters detected by sentinel path:
#   claude  — ~/.claude/agents/ directory exists
#   codex   — ~/.codex/agents/ directory exists
#
# The generic adapter installs into <project>/.agent-crew/agents/, but the
# project root is not known at agent-maker time. It will pick up the new
# agent on the next crew:setup run for that project.
#
# This script is idempotent: safe to run multiple times for the same agent.
# Silent on non-installed adapters — no error if a path does not exist.

set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
AGENT_FILE="${1:-}"

if [ -z "${AGENT_FILE}" ]; then
  printf '[deploy-user-agent] ERROR: no agent filename provided\n' >&2
  printf 'Usage: %s <agent-filename.md>\n' "$0" >&2
  exit 1
fi

# Strip any directory prefix — we only accept a bare filename
AGENT_BASENAME="$(basename "${AGENT_FILE}")"

USER_AGENTS="${AGENT_CREW_HOME}/user/agents"
SYSTEM_AGENTS="${AGENT_CREW_HOME}/system/agents"
AGENT_PATH="${USER_AGENTS}/${AGENT_BASENAME}"

if [ ! -f "${AGENT_PATH}" ]; then
  printf '[deploy-user-agent] ERROR: agent not found: %s\n' "${AGENT_PATH}" >&2
  exit 1
fi

# Load shared helpers (merge_agents_to_discovery, copy_dir_contents)
. "${AGENT_CREW_HOME}/setup/common.sh"

DEPLOYED=0

# ── Claude adapter ────────────────────────────────────────────────────────────
# Discovery path: ~/.claude/agents/
CLAUDE_AGENTS="${HOME}/.claude/agents"
if [ -d "${CLAUDE_AGENTS}" ]; then
  printf '[deploy-user-agent] Deploying to Claude: %s\n' "${CLAUDE_AGENTS}"
  merge_agents_to_discovery "${SYSTEM_AGENTS}" "${USER_AGENTS}" "${CLAUDE_AGENTS}"
  # Also keep the agent-crew mirror path in sync
  CLAUDE_CREW_AGENTS="${HOME}/.claude/agent-crew/agents"
  if [ -d "${CLAUDE_CREW_AGENTS}" ]; then
    copy_dir_contents "${SYSTEM_AGENTS}" "${CLAUDE_CREW_AGENTS}"
    cp "${AGENT_PATH}" "${CLAUDE_CREW_AGENTS}/" 2>/dev/null || true
  fi
  DEPLOYED=$((DEPLOYED + 1))
fi

# ── Codex adapter ─────────────────────────────────────────────────────────────
# Discovery path: PROJECT_ROOT/.codex/agents/ (project-local TOML stubs).
# The Codex adapter uses TOML format for subagent definitions, so the .md file
# must be converted. We detect any initialised Codex project under common roots:
#   1. The current git working tree (git rev-parse --show-toplevel)
#   2. The current directory ($PWD)
# If neither has a .codex/agents/ directory the adapter is not installed here
# and we fall through silently — the next crew:setup will pick it up.
_CODEX_PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "${PWD}")"
CODEX_PROJECT_AGENTS="${_CODEX_PROJECT_ROOT}/.codex/agents"
if [ -d "${CODEX_PROJECT_AGENTS}" ]; then
  printf '[deploy-user-agent] Deploying to Codex (TOML): %s\n' "${CODEX_PROJECT_AGENTS}"
  python3 - "${AGENT_PATH}" "${CODEX_PROJECT_AGENTS}" <<'PYEOF'
import os, re, sys

md_path  = sys.argv[1]
dest_dir = sys.argv[2]

def parse_frontmatter(text):
    fm = {}
    body = text
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
    if m:
        fm_text = m.group(1)
        body    = m.group(2)
        for line in fm_text.splitlines():
            kv = re.match(r'^(\w[\w_-]*):\s*(.*)', line)
            if kv:
                key, val = kv.group(1), kv.group(2).strip().strip('"\'')
                if val in ('>', '|', '>-', '|-'):
                    val = ''
                fm[key] = val
    return fm, body

def toml_escape(s):
    s = s.replace('\\', '\\\\')
    s = s.replace('"""', '""\\"')
    return s

try:
    text = open(md_path, encoding='utf-8').read()
except OSError as e:
    print(f'[deploy-user-agent] ERROR reading {md_path}: {e}', file=sys.stderr)
    sys.exit(1)

fm, body = parse_frontmatter(text)

basename = os.path.basename(md_path)
stem     = os.path.splitext(basename)[0]
name     = fm.get('name', '').strip() or stem
description    = fm.get('description', '').strip().lstrip('> ').strip()
model = fm.get('model', '').strip()
model_reasoning_effort = fm.get('model_reasoning_effort', '').strip()
sandbox_mode = fm.get('sandbox_mode', '').strip()
nickname_candidates = fm.get('nickname_candidates', '').strip()

if not description:
    description = f'User agent: {name}'

toml_name   = re.sub(r'[^\w-]', '-', name.lower()).strip('-') or 'unknown'
dest_path   = os.path.join(dest_dir, toml_name + '.toml')
body_esc    = toml_escape(body.rstrip())
desc_esc    = description.replace('\\', '\\\\').replace('"', '\\"')

lines = [
    f'name = "{toml_name}"',
    f'description = "{desc_esc}"',
]
# Preserve only official Codex per-agent config keys. `reasoning_tier` is an
# agent-crew abstraction and is not accepted by Codex TOML agents.
for key, value in (
    ('model', model),
    ('model_reasoning_effort', model_reasoning_effort),
    ('sandbox_mode', sandbox_mode),
):
    if value:
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        lines.append(f'{key} = "{escaped}"')
if nickname_candidates:
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
lines.append(f'developer_instructions = """\n{body_esc}\n"""')
toml_content = '\n'.join(lines) + '\n'

with open(dest_path, 'w', encoding='utf-8') as f:
    f.write(toml_content)
print(f'[deploy-user-agent] Written: {dest_path}')
PYEOF
  DEPLOYED=$((DEPLOYED + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
if [ "${DEPLOYED}" -eq 0 ]; then
  printf '[deploy-user-agent] No installed host adapters detected — agent saved to user/agents/ only.\n'
  printf '[deploy-user-agent] Run crew:setup to install for a specific host.\n'
else
  printf '[deploy-user-agent] Deployed %s to %d host adapter(s).\n' "${AGENT_BASENAME}" "${DEPLOYED}"
fi
