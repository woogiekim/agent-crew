#!/usr/bin/env bash
set -euo pipefail

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"
# AGENT_CREW_MODE: "install" (default) or "update". Update mode never prompts
# and never resets state; the copy operations below are idempotent in both
# modes (cp -R overwrites but does not delete extraneous files).
AGENT_CREW_MODE="${AGENT_CREW_MODE:-install}"

. "${AGENT_CREW_HOME}/setup/common.sh"

if [ "${AGENT_CREW_MODE}" = "update" ]; then
  printf 'MODE: update (host=claude)\n'
fi

copy_dir_contents "${AGENT_CREW_HOME}/commands" "${CLAUDE_DIR}/commands"
copy_dir_contents "${AGENT_CREW_HOME}/hooks" "${CLAUDE_DIR}/agent-crew/hooks"
copy_dir_contents "${AGENT_CREW_HOME}/rules" "${CLAUDE_DIR}/agent-crew/rules"
copy_dir_contents "${AGENT_CREW_HOME}/setup" "${CLAUDE_DIR}/agent-crew/setup"
copy_dir_contents "${AGENT_CREW_HOME}/adapters/claude" "${CLAUDE_DIR}/agent-crew/adapters/claude"
mkdir -p "${CLAUDE_DIR}/agent-crew"
diff_copy "${AGENT_CREW_HOME}/adapters/claude/invocation.md" "${CLAUDE_DIR}/agent-crew/invocation.md" 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/hooks/"*.sh 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/setup/"*.sh 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/adapters/claude/"*.sh 2>/dev/null || true

# Enforce system/agents/ classification before copying to mirror path.
# In update mode: re-sync system/agents/ from the installed system source to
# ensure stale agents (removed from the repo) are pruned, while preserving
# system-exception agents (mcp-manager.md).
# The SOURCE_ROOT environment variable is set by install.sh when this script
# is called from install_claude_compat(); in standalone crew:setup runs it
# falls back to the installed system copy (which is already up-to-date).
if [ -n "${SOURCE_ROOT:-}" ] && [ -d "${SOURCE_ROOT}/core/agents" ]; then
  sync_system_agents \
    "${SOURCE_ROOT}/core/agents" \
    "${AGENT_CREW_HOME}/system/agents" \
    "mcp-manager.md"
fi

# Copy system agents to the agent-crew mirror path
copy_dir_contents "${AGENT_CREW_HOME}/system/agents" "${CLAUDE_DIR}/agent-crew/agents"

# Scaffold user/ directories (idempotent — crew:update must never overwrite these)
mkdir -p "${AGENT_CREW_HOME}/user/agents"
mkdir -p "${AGENT_CREW_HOME}/user/skills"
mkdir -p "${AGENT_CREW_HOME}/user/commands"
mkdir -p "${AGENT_CREW_HOME}/user/rules"
# Write README placeholder only if not already present
if [ ! -f "${AGENT_CREW_HOME}/user/agents/README.md" ]; then
  cat > "${AGENT_CREW_HOME}/user/agents/README.md" << 'UEOF'
# User Agents

Place your custom agent definitions here.
Files in this directory are NEVER overwritten by crew:update.

Naming: avoid filenames that match built-in agents (analyst.md, backend.md,
designer.md, devops.md, frontend.md, planner.md, requirements.md, resolver.md,
reviewer.md, task-runner.md, korean-normalizer.md). Use a unique prefix, e.g.
my-agent.md, or an org-prefixed name like acme-deploy.md.

crew:update merges these into ~/.claude/agents/ automatically.
UEOF
fi

# Merge system/agents/ + user/agents/ → ~/.claude/agents/ (generated output)
merge_agents_to_discovery \
  "${AGENT_CREW_HOME}/system/agents" \
  "${AGENT_CREW_HOME}/user/agents" \
  "${CLAUDE_DIR}/agents"

# Auto-migrate legacy flat layout (pre-system/ era):
# - Non-repo, non-exception agents → user/agents/
# - Repo agents and system-exception agents → already in system/agents/ (skip)
# - Remove the legacy directory when fully classified
if [ -d "${AGENT_CREW_HOME}/agents" ] && [ ! -L "${AGENT_CREW_HOME}/agents" ]; then
  printf '\n[agent-crew] Legacy layout detected at %s/agents/ — migrating...\n' "${AGENT_CREW_HOME}"
  mkdir -p "${AGENT_CREW_HOME}/user/agents"
  # Determine source for repo membership check: prefer SOURCE_ROOT if set
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

merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${CLAUDE_DIR}/CLAUDE.md"
register_local_git_excludes "${PROJECT_ROOT}" ".claude/" "CLAUDE.md" ".claude/settings.local.json" ".claude/CLAUDE.local.md"

# Write host capability flags so the core pipeline can opt into Claude Code's
# richer task-tracking surface (TaskCreate / TaskList / TaskUpdate / Monitor).
# Schema documented at core/rules/host-capabilities.md.
# Absence of this file MUST be treated as legacy behavior (all flags false).
PROJECT_NAME="$(basename "${PROJECT_ROOT}")"
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
CAPABILITIES_FILE="${STATE_DIR}/capabilities.json"
mkdir -p "${STATE_DIR}"
cat > "${CAPABILITIES_FILE}" <<'CAPS_EOF'
{
  "host": "claude",
  "task_tools": true,
  "agent_background": true,
  "monitor_tool": true
}
CAPS_EOF

# Register Agent diff PreToolUse/PostToolUse hooks into Claude settings.json
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/agent-diff-pre.sh" "Agent" "PreToolUse" <<'PYEOF'
import sys, json, os
dest, hook_path, matcher, hook_type = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
hook_entry = {"type": "command", "command": f"bash {hook_path}", "timeout": 5}
if os.path.exists(dest):
  with open(dest) as f:
    try: settings = json.load(f)
    except json.JSONDecodeError: settings = {}
else:
  settings = {}
hooks = settings.setdefault("hooks", {})
hook_list = hooks.setdefault(hook_type, [])
hook_path_base = os.path.basename(hook_path)
for block in hook_list:
  if block.get("matcher") == matcher:
    for h in block.get("hooks", []):
      if hook_path_base in h.get("command", ""):
        h["command"] = hook_entry["command"]
        break
    else:
      block.setdefault("hooks", []).append(hook_entry)
    break
else:
  hook_list.append({"matcher": matcher, "hooks": [hook_entry]})
with open(dest, "w") as f:
  json.dump(settings, f, indent=2, ensure_ascii=False)
  f.write("\n")
PYEOF

python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/agent-diff-post.sh" "Agent" "PostToolUse" <<'PYEOF'
import sys, json, os
dest, hook_path, matcher, hook_type = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
hook_entry = {"type": "command", "command": f"bash {hook_path}", "timeout": 10}
if os.path.exists(dest):
  with open(dest) as f:
    try: settings = json.load(f)
    except json.JSONDecodeError: settings = {}
else:
  settings = {}
hooks = settings.setdefault("hooks", {})
hook_list = hooks.setdefault(hook_type, [])
hook_path_base = os.path.basename(hook_path)
for block in hook_list:
  if block.get("matcher") == matcher:
    for h in block.get("hooks", []):
      if hook_path_base in h.get("command", ""):
        h["command"] = hook_entry["command"]
        break
    else:
      block.setdefault("hooks", []).append(hook_entry)
    break
else:
  hook_list.append({"matcher": matcher, "hooks": [hook_entry]})
with open(dest, "w") as f:
  json.dump(settings, f, indent=2, ensure_ascii=False)
  f.write("\n")
PYEOF

print_diff_summary

printf 'HOST: claude\n'
printf 'PROJECT_ROOT: %s\n' "${PROJECT_ROOT}"
printf 'INSTALLED: %s\n' "${CLAUDE_DIR}"
printf 'CAPABILITIES: %s\n' "${CAPABILITIES_FILE}"
