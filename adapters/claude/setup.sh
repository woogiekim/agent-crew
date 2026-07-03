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
copy_dir_contents "${AGENT_CREW_HOME}/scripts" "${CLAUDE_DIR}/agent-crew/scripts"
copy_dir_contents "${AGENT_CREW_HOME}/setup" "${CLAUDE_DIR}/agent-crew/setup"
copy_dir_contents "${AGENT_CREW_HOME}/adapters/claude" "${CLAUDE_DIR}/agent-crew/adapters/claude"
mkdir -p "${CLAUDE_DIR}/agent-crew"
diff_copy "${AGENT_CREW_HOME}/adapters/claude/invocation.md" "${CLAUDE_DIR}/agent-crew/invocation.md" 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/hooks/"*.sh 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/scripts/"*.sh 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/scripts/"*.py 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/setup/"*.sh 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/adapters/claude/"*.sh 2>/dev/null || true
chmod +x "${CLAUDE_DIR}/agent-crew/adapters/claude/bin/"* 2>/dev/null || true

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
# Scaffold system/ and unified discovery directories for skills
mkdir -p "${AGENT_CREW_HOME}/system/skills"
mkdir -p "${AGENT_CREW_HOME}/skills"
mkdir -p "${CLAUDE_DIR}/agent-crew/skills"

# Sync system/skills/ from source and merge into discovery path.
# Source: core/agents/skills/ → system install: ~/.agent-crew/system/skills/
# Unified discovery: ~/.agent-crew/skills/ (system + user merged, user wins)
# Claude mirror: ~/.claude/agent-crew/skills/ (for reference by agents at runtime)
if [ -n "${SOURCE_ROOT:-}" ] && [ -d "${SOURCE_ROOT}/core/agents/skills" ]; then
  sync_system_skills \
    "${SOURCE_ROOT}/core/agents/skills" \
    "${AGENT_CREW_HOME}/system/skills"
fi

# Merge system/skills/ + user/skills/ → ~/.agent-crew/skills/ (unified discovery)
merge_skills_to_discovery \
  "${AGENT_CREW_HOME}/system/skills" \
  "${AGENT_CREW_HOME}/user/skills" \
  "${AGENT_CREW_HOME}/skills"

# Copy unified skill discovery to Claude mirror path
copy_dir_contents "${AGENT_CREW_HOME}/skills" "${CLAUDE_DIR}/agent-crew/skills"

# Write README placeholders only if not already present
if [ ! -f "${AGENT_CREW_HOME}/user/skills/README.md" ]; then
  cat > "${AGENT_CREW_HOME}/user/skills/README.md" << 'UEOF'
# User Skills

Place your custom skill definitions here.
Files in this directory are NEVER overwritten by crew:update.

User skills take precedence over system skills with the same filename —
your copy wins in the unified discovery path (~/.agent-crew/skills/).

Naming: you may use the same filename as a system skill to override it,
or choose a unique name for an additive skill (e.g. my-skill.md).

crew:update merges these into ~/.agent-crew/skills/ and
~/.claude/agent-crew/skills/ automatically.
UEOF
fi

if [ ! -f "${AGENT_CREW_HOME}/user/agents/README.md" ]; then
  cat > "${AGENT_CREW_HOME}/user/agents/README.md" << 'UEOF'
# User Agents

Place your custom agent definitions here.
Files in this directory are NEVER overwritten by crew:update.

Naming: avoid filenames that match built-in agents (analyst.md, backend.md,
designer.md, devops.md, frontend.md, planner.md, requirements.md, resolver.md,
reviewer.md, supervisor.md, supervisor-bootstrap.md, supervisor-stages.md, supervisor-retry.md, documenter.md, korean-normalizer.md). Use a unique prefix, e.g.
my-agent.md, or an org-prefixed name like acme-deploy.md.

crew:update merges these into ~/.claude/agents/ automatically.
UEOF
fi

# Merge system/agents/ + user/agents/ → ~/.claude/agents/ (generated output)
merge_agents_to_discovery \
  "${AGENT_CREW_HOME}/system/agents" \
  "${AGENT_CREW_HOME}/user/agents" \
  "${CLAUDE_DIR}/agents"

# Materialize reasoning_tier → concrete Claude model identifier in the
# host's discovery path. The mapping is Claude-specific and lives here;
# core/agents/*.md files keep `model: inherit`. See
# core/rules/capabilities/reasoning-tier.md for the contract.
python3 - "${CLAUDE_DIR}/agents" "${AGENT_CREW_HOME}/system/agents" <<'TIERPY'
import re
import sys
from pathlib import Path

dest = Path(sys.argv[1])
system_src = Path(sys.argv[2])

# Adapter-local tier map. Update here when Claude's model names change.
TIER_TO_MODEL = {
    "xhigh":   "claude-fable-5",
    "deep":     "claude-opus-4-8",
    "balanced": "claude-sonnet-5",
    "light":    "claude-haiku-4-5",
}
DEFAULT_TIER = "balanced"

# Collect system-agent basenames so we only materialize files the system
# layer owns. User agents (and any file not present in system/) are left
# untouched — user owns their model choice.
system_names = {p.name for p in system_src.glob("*.md")} if system_src.exists() else set()

frontmatter_re = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
tier_re = re.compile(r"^reasoning_tier:\s*(\S+)\s*$", re.MULTILINE)
model_re = re.compile(r"^model:\s*\S+\s*$", re.MULTILINE)

applied = []
skipped_no_frontmatter = []
skipped_user = []
warnings = []

for md_path in sorted(dest.glob("*.md")):
    name = md_path.name
    if name == "README.md":
        continue
    if name not in system_names:
        skipped_user.append(name)
        continue

    text = md_path.read_text()
    fm = frontmatter_re.match(text)
    if not fm:
        skipped_no_frontmatter.append(name)
        continue

    fm_block = fm.group(1)
    tier_match = tier_re.search(fm_block)
    if not tier_match:
        tier = DEFAULT_TIER
        warnings.append(f"{name}: no reasoning_tier; defaulted to {tier}")
    else:
        tier = tier_match.group(1)

    model = TIER_TO_MODEL.get(tier)
    if model is None:
        warnings.append(
            f"{name}: unknown reasoning_tier '{tier}'; defaulted to {DEFAULT_TIER}"
        )
        tier = DEFAULT_TIER
        model = TIER_TO_MODEL[DEFAULT_TIER]

    if model_re.search(fm_block):
        new_fm_block = model_re.sub(f"model: {model}", fm_block, count=1)
    else:
        # No existing model line in frontmatter — append one.
        new_fm_block = fm_block.rstrip() + f"\nmodel: {model}"

    new_text = text[:fm.start()] + "---\n" + new_fm_block + "\n---\n" + text[fm.end():]
    if new_text != text:
        md_path.write_text(new_text)
    applied.append(f"{name} → {tier} ({model})")

for line in applied:
    print(f"[agent-crew] tier: {line}")
for w in warnings:
    print(f"[agent-crew] tier WARN: {w}")
if skipped_no_frontmatter:
    print(f"[agent-crew] tier: skipped {len(skipped_no_frontmatter)} file(s) without frontmatter: {', '.join(skipped_no_frontmatter)}")
if skipped_user:
    print(f"[agent-crew] tier: skipped {len(skipped_user)} user-agent file(s) (user owns model choice)")
TIERPY

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
  "host": "claude",
  "task_tools": true,
  "agent_background": true,
  "monitor_tool": true,
  "cost_tracking": true,
  "hook_system": true
}
CAPS_EOF
fi

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

# Defense-in-depth for supervisor pipeline bypasses: reject stage/completion
# progress emitted before pipeline.json exists, even if the supervisor's own
# log_progress guard is bypassed.
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/supervisor-progress-guard.sh" "*" "PostToolUse" <<'PYEOF'
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
        h["timeout"] = hook_entry["timeout"]
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

# Phase 3.3: cost_tracking capability — cost-tracker.sh writes one JSONL
# line per call to ${STATE_DIR}/cost/${TASK_ID}.jsonl. Schema documented
# at core/rules/capabilities/cost-tracking.md § Required Adapter Surface.
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/cost-tracker.sh" "*" "PostToolUse" <<'PYEOF'
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

# Issue #16: mnemos-capture-guard.sh — validates ✻ 🧠 capture notifications
# against actual mnemos captures. Advisory only: always exits 0.
# mnemos absence = silent no-op (graceful degradation).
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/mnemos-capture-guard.sh" "*" "PostToolUse" <<'PYEOF'
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

# Automatic agent-crew issue reporter. Advisory only: detects explicit
# agent-crew bug/error prompts and crew Bash output with explicit bug/error
# signals, then delegates to `crew report auto` for native local reporting.
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/auto-issue-report.sh" "*" "UserPromptSubmit" <<'PYEOF'
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
        h["timeout"] = hook_entry["timeout"]
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

python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/auto-issue-report.sh" "Bash" "PostToolUse" <<'PYEOF'
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
        h["timeout"] = hook_entry["timeout"]
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

# Issue #17: direct-edit-guard.sh — blocks direct Edit/Write calls to project
# source files when no active crew task is in progress. Enforces the
# "No Direct Implementation" rule. Blocking: exits 2 to cancel the tool call.
# Escape hatch: AGENT_CREW_ALLOW_DIRECT_EDIT=1 or tasks/active marker.
# Contract documented at core/rules/direct-edit-guard.md.
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/direct-edit-guard.sh" "Edit|Write" "PreToolUse" <<'PYEOF'
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

# Issue #180: tracker-mutation-guard.sh blocks direct Plane MCP mutation
# fallback unless generic issuer tracker-adapter validation evidence is present.
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/tracker-mutation-guard.sh" "mcp__plane__create_work_item|mcp__plane__update_work_item|mcp__plane__delete_work_item|mcp__plane__create_intake_work_item|mcp__plane.create_work_item|mcp__plane.update_work_item|mcp__plane.delete_work_item|mcp__plane.create_intake_work_item" "PreToolUse" <<'PYEOF'
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
        h["timeout"] = hook_entry["timeout"]
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

# Phase G6: hook_system capability — forbid-plaintext-approval.sh blocks
# free-text yes/no approval prompts ("Shall I merge?" / "진행할까요?") in
# Agent responses. Validator: core/scripts/check-plaintext-approval.py.
# Contract documented at core/rules/capabilities/hook-system.md.
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/forbid-plaintext-approval.sh" "Agent" "PostToolUse" <<'PYEOF'
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

# Issue #125: route-directive-guard.sh detects Agent responses that ignore
# STOP/ROUTE route locks injected by auto-route.sh and answer inline instead.
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/route-directive-guard.sh" "Agent" "PostToolUse" <<'PYEOF'
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

# Issue #130: normalize-task-guard.sh — PreToolUse[Agent|Task] hook that blocks
# Agent/Task tool calls whose prompt carries raw non-English (Hangul) content
# in TASK:/REQUIREMENTS: slots without a matching NORMALIZED_TASK: provenance
# line. Capability-gated defence-in-depth augmentation for the AI-agnostic
# enforcement in core/rules/normalization-adapter.md and core/rules/korean-input.md.
# Exempts input-normalizer / korean-normalizer agents and the explicit
# AGENT_CREW_ALLOW_RAW_NON_ASCII_TASK=1 escape hatch.
python3 - "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/normalize-task-guard.sh" "Agent|Task" "PreToolUse" <<'PYEOF'
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
