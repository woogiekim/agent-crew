#!/bin/bash
# =============================================================
# AI Agent Crew — Global Installer
# Usage:
#   curl -s https://raw.githubusercontent.com/woogiekim/agent-crew/main/install.sh | bash
# =============================================================

set -e

REPO_URL="https://github.com/woogiekim/agent-crew"
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
AGENT_CREW_DIR="${AGENT_CREW_HOME}"
CLAUDE_DIR="${CLAUDE_DIR:-${HOME}/.claude}"
# AGENT_CREW_MODE: "install" (default) or "update".
# Update mode is intended for `crew:update` — it auto-confirms the
# "Reinstall? [Y/N]" prompt and emits a "MODE: update" marker line so the
# caller can detect non-interactive refresh runs in logs.
AGENT_CREW_MODE="${AGENT_CREW_MODE:-install}"
export AGENT_CREW_MODE

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
log_error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
log_section() { echo -e "\n${GREEN}▶ $1${NC}"; }

# Bootstrap stubs for diff helpers. They are replaced when common.sh is sourced.
_DIFF_LOG=()
diff_copy()         { local src="$1" dest="$2"; mkdir -p "$(dirname "${dest}")"; cp "${src}" "${dest}"; }
diff_install()      { local src="$1" dest="$2"; [ -d "${src}" ] || return 0; mkdir -p "${dest}"; cp -R "${src}/." "${dest}/"; find "${dest}" -name ".DS_Store" -delete 2>/dev/null || true; }
print_diff_summary() { :; }

install_path_crew_cli() {
  local src="${SOURCE_DIR}/bin/crew"
  local dest_dir="${AGENT_CREW_PATH_BIN:-${HOME}/.local/bin}"
  local dest="${dest_dir}/crew"
  [ -f "${src}" ] || return 0

  mkdir -p "${dest_dir}"
  if [ -f "${dest}" ] \
    && ! grep -q "experimental Codex launcher for agent-crew" "${dest}" 2>/dev/null \
    && ! grep -q "deterministic shell entrypoint for agent-crew" "${dest}" 2>/dev/null; then
    log_warn "Skipping PATH crew CLI; unmanaged file exists at ${dest}"
    return 0
  fi

  cp -f "${src}" "${dest}"
  chmod +x "${dest}"
  log_info "Native crew CLI installed → ${dest}"
}

write_install_integrity_manifest() {
  local checksum_script="${SOURCE_ROOT}/core/scripts/generate-release-checksums.py"
  local integrity_dir="${AGENT_CREW_HOME}/state/install-integrity"
  local manifest="${integrity_dir}/install-integrity.json"
  local sums="${integrity_dir}/SHA256SUMS"

  [ "${AGENT_CREW_WRITE_INSTALL_MANIFEST:-1}" = "1" ] || return 0
  [ -f "${checksum_script}" ] || return 0

  mkdir -p "${integrity_dir}"
  python3 "${checksum_script}" \
    --project-root "${SOURCE_ROOT}" \
    --output "${manifest}" \
    --sha256sums "${sums}" \
    install.sh \
    core/bin/crew \
    core/commands/update.md \
    core/scripts/sync-local-install.sh >/dev/null
  log_info "Install integrity manifest written → ${manifest}"
}

# Check for an existing installation.
if [ -d "${AGENT_CREW_DIR}/system/agents" ] || [ -d "${AGENT_CREW_DIR}/agents" ]; then
  if [ "${AGENT_CREW_MODE}" = "update" ]; then
    log_info "MODE: update — refreshing existing install at ${AGENT_CREW_DIR} (auto-confirmed)"
  else
    log_warn "agent-crew is already installed (${AGENT_CREW_DIR})"
    read -p "Reinstall? [Y/N] " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
      echo "Installation cancelled."
      exit 0
    fi
  fi
fi

install_global() {
  log_section "Starting global installation"

  TEMP_DIR=""
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd 2>/dev/null || pwd)"

  if [ -n "${AGENT_CREW_SOURCE_DIR:-}" ]; then
    SOURCE_ROOT="${AGENT_CREW_SOURCE_DIR}"
    log_info "Using source directory from AGENT_CREW_SOURCE_DIR → ${SOURCE_ROOT}"
  elif [ -d "${SCRIPT_DIR}/core" ] && [ -d "${SCRIPT_DIR}/adapters" ]; then
    SOURCE_ROOT="${SCRIPT_DIR}"
    log_info "Using local source directory → ${SOURCE_ROOT}"
  elif [ -d "$(pwd)/core" ] && [ -d "$(pwd)/adapters" ]; then
    SOURCE_ROOT="$(pwd)"
    log_info "Using current working tree as source → ${SOURCE_ROOT}"
  elif command -v git &>/dev/null; then
    TEMP_DIR=$(mktemp -d)
    log_info "Cloning repository..."
    git clone --depth 1 "$REPO_URL" "$TEMP_DIR" 2>/dev/null
    SOURCE_ROOT="${TEMP_DIR}"
  else
    log_error "git is not installed."
  fi

  SOURCE_DIR="${SOURCE_ROOT}/core"
  ADAPTERS_DIR="${SOURCE_ROOT}/adapters"

  [ -d "${SOURCE_DIR}" ] \
    || log_error "core source directory not found — expected ${SOURCE_DIR}"
  [ -d "${ADAPTERS_DIR}" ] \
    || log_error "adapter directory not found — expected ${ADAPTERS_DIR}"

  # Load shared functions (sync_system_agents, migrate_legacy_agents,
  # merge_agents_to_discovery, diff_copy, diff_install, print_diff_summary).
  # Source as early as possible so all copy operations below emit diff output.
  # Falls back gracefully when common.sh is unavailable (very first bootstrap).
  if [ -f "${SOURCE_DIR}/setup/common.sh" ]; then
    . "${SOURCE_DIR}/setup/common.sh"
  fi

  mkdir -p "${AGENT_CREW_HOME}/system/commands"
  diff_install "${SOURCE_DIR}/commands" "${AGENT_CREW_HOME}/system/commands"
  log_info "Commands installed → ${AGENT_CREW_HOME}/system/commands/"

  [ -f "${AGENT_CREW_HOME}/system/commands/agent-maker.md" ] \
    || log_error "agent-maker.md install failed — system/commands/agent-maker.md not found"
  log_info "agent-maker command verified"

  # Enforce agent classification: sync source → system/agents/, pruning stale files
  # but preserving system-exception agents (mcp-manager.md).
  if type sync_system_agents &>/dev/null 2>&1; then
    sync_system_agents \
      "${SOURCE_DIR}/agents" \
      "${AGENT_CREW_DIR}/system/agents" \
      "mcp-manager.md"
  else
    mkdir -p "${AGENT_CREW_DIR}/system/agents/skills"
    cp "${SOURCE_DIR}/agents/"*.md "${AGENT_CREW_DIR}/system/agents/" 2>/dev/null || true
    cp "${SOURCE_DIR}/agents/skills/"*.md "${AGENT_CREW_DIR}/system/agents/skills/" 2>/dev/null || true
  fi
  log_info "Agents installed → ${AGENT_CREW_DIR}/system/agents/"
  log_info "Skills installed → ${AGENT_CREW_DIR}/system/agents/skills/"

  # Channel B — adapter skill templates (Wave A, issue #131).
  # Templates ship with the framework but seed into the user layer
  # (~/.agent-crew/user/skills/) via crew:setup / crew:update — never
  # auto-merged. See core/rules/agent-tool-dispatch.md § Channel B.
  if [ -d "${SOURCE_DIR}/agents/skills/templates" ]; then
    mkdir -p "${AGENT_CREW_DIR}/system/agents/skills/templates"
    cp -f "${SOURCE_DIR}/agents/skills/templates/"*.md \
      "${AGENT_CREW_DIR}/system/agents/skills/templates/" 2>/dev/null || true
    log_info "Adapter skill templates installed → ${AGENT_CREW_DIR}/system/agents/skills/templates/"
  fi

  [ -f "${AGENT_CREW_DIR}/system/agents/reviewer.md" ] \
    || log_error "reviewer.md install failed — system/agents/reviewer.md not found"
  log_info "reviewer agent verified"

  [ -f "${AGENT_CREW_DIR}/system/agents/supervisor.md" ] \
    || log_error "supervisor.md install failed — system/agents/supervisor.md not found"
  log_info "supervisor agent verified"

  # Phase C2: supervisor sub-modules. supervisor.md is the index/entry file
  # (the only agent the host registers); the three sub-modules below are
  # content fragments the supervisor Reads on demand at phase transitions.
  for sub in bootstrap stages retry; do
    [ -f "${AGENT_CREW_DIR}/system/agents/supervisor-${sub}.md" ] \
      || log_error "supervisor-${sub}.md install failed — system/agents/supervisor-${sub}.md not found"
    log_info "supervisor sub-module verified: supervisor-${sub}.md"
  done

  [ -f "${AGENT_CREW_DIR}/system/agents/planner.md" ] \
    || log_error "planner.md install failed — system/agents/planner.md not found"
  log_info "planner agent verified"

  [ -f "${AGENT_CREW_DIR}/system/agents/documenter.md" ] \
    || log_error "documenter.md install failed — system/agents/documenter.md not found"
  log_info "documenter agent verified"

  mkdir -p "${AGENT_CREW_DIR}/system/rules"
  diff_install "${SOURCE_DIR}/rules" "${AGENT_CREW_DIR}/system/rules"
  log_info "Rules installed → ${AGENT_CREW_DIR}/system/rules/"

  [ -f "${AGENT_CREW_DIR}/system/rules/quality-loop.md" ] \
    || log_error "quality-loop.md install failed — system/rules/quality-loop.md not found"

  [ -d "${AGENT_CREW_DIR}/system/rules/capabilities" ] \
    || log_error "rules/capabilities/ install failed — directory not found"

  mkdir -p "${AGENT_CREW_DIR}/system/scripts"
  if [ -d "${SOURCE_DIR}/scripts" ]; then
    cp -r "${SOURCE_DIR}/scripts/"* "${AGENT_CREW_DIR}/system/scripts/" 2>/dev/null || true
    chmod +x "${AGENT_CREW_DIR}/system/scripts/"*.sh 2>/dev/null || true
    chmod +x "${AGENT_CREW_DIR}/system/scripts/"*.py 2>/dev/null || true
    log_info "Scripts installed → ${AGENT_CREW_DIR}/system/scripts/"
  fi

  mkdir -p "${AGENT_CREW_DIR}/system/evaluations"
  if [ -d "${SOURCE_DIR}/evaluations" ]; then
    cp -r "${SOURCE_DIR}/evaluations/"* "${AGENT_CREW_DIR}/system/evaluations/" 2>/dev/null || true
    log_info "Evaluation fixtures installed → ${AGENT_CREW_DIR}/system/evaluations/"
  fi

  mkdir -p "${AGENT_CREW_DIR}/system/schemas"
  if [ -d "${SOURCE_DIR}/schemas" ]; then
    cp -r "${SOURCE_DIR}/schemas/"* "${AGENT_CREW_DIR}/system/schemas/" 2>/dev/null || true
    log_info "Schemas installed → ${AGENT_CREW_DIR}/system/schemas/"
  fi

  # Memory backend wrapper — thin shim that delegates to mnemos when installed,
  # degrades silently when absent. Sub-agents call `memory capture` (not
  # `mnemos capture` directly) so pipelines work without a memory backend.
  # See: https://github.com/woogiekim/agent-crew/issues/15
  if [ -f "${SOURCE_DIR}/bin/memory" ]; then
    mkdir -p "${AGENT_CREW_DIR}/bin"
    cp "${SOURCE_DIR}/bin/memory" "${AGENT_CREW_DIR}/bin/memory"
    chmod +x "${AGENT_CREW_DIR}/bin/memory"
    log_info "Memory wrapper installed → ${AGENT_CREW_DIR}/bin/memory"
  fi

  if [ -f "${SOURCE_DIR}/bin/crew" ]; then
    mkdir -p "${AGENT_CREW_DIR}/bin"
    cp "${SOURCE_DIR}/bin/crew" "${AGENT_CREW_DIR}/bin/crew"
    chmod +x "${AGENT_CREW_DIR}/bin/crew"
    log_info "crew CLI installed → ${AGENT_CREW_DIR}/bin/crew"
    install_path_crew_cli
  fi

  [ -f "${AGENT_CREW_DIR}/system/schemas/register.schema.json" ] \
    || log_error "register.schema.json install failed — system/schemas/register.schema.json not found"

  mkdir -p "${AGENT_CREW_DIR}/system/hooks"
  diff_install "${SOURCE_DIR}/hooks" "${AGENT_CREW_DIR}/system/hooks"
  chmod +x "${AGENT_CREW_DIR}/system/hooks/"*.sh 2>/dev/null || true
  log_info "Hooks installed → ${AGENT_CREW_DIR}/system/hooks/"

  [ -f "${AGENT_CREW_DIR}/system/hooks/direct-edit-guard.sh" ] \
    || log_error "direct-edit-guard.sh install failed — system/hooks/direct-edit-guard.sh not found"

  mkdir -p "${AGENT_CREW_DIR}/system/setup"
  diff_install "${SOURCE_DIR}/setup" "${AGENT_CREW_DIR}/system/setup"
  chmod +x "${AGENT_CREW_DIR}/system/setup/"*.sh 2>/dev/null || true
  log_info "Setup dispatcher installed → ${AGENT_CREW_DIR}/system/setup/"

  mkdir -p "${AGENT_CREW_DIR}/system/adapters"
  diff_install "${ADAPTERS_DIR}" "${AGENT_CREW_DIR}/system/adapters"
  chmod +x "${AGENT_CREW_DIR}/system/adapters/"*/*.sh 2>/dev/null || true
  chmod +x "${AGENT_CREW_DIR}/system/adapters/"*/bin/* 2>/dev/null || true
  find "${AGENT_CREW_DIR}/system" -name ".DS_Store" -delete 2>/dev/null || true
  log_info "Host adapters installed → ${AGENT_CREW_DIR}/system/adapters/"

  [ -f "${AGENT_CREW_DIR}/system/hooks/auto-route.sh" ] \
    || log_error "auto-route.sh install failed — system/hooks/auto-route.sh not found"

  # Keep top-level symlink-free aliases for backward compatibility with existing
  # hooks that reference ${AGENT_CREW_HOME}/hooks/ directly.
  # We write real copies here so existing hook registrations still resolve.
  mkdir -p "${AGENT_CREW_DIR}/hooks"
  diff_install "${SOURCE_DIR}/hooks" "${AGENT_CREW_DIR}/hooks"
  chmod +x "${AGENT_CREW_DIR}/hooks/"*.sh 2>/dev/null || true

  mkdir -p "${AGENT_CREW_DIR}/setup"
  diff_install "${SOURCE_DIR}/setup" "${AGENT_CREW_DIR}/setup"
  chmod +x "${AGENT_CREW_DIR}/setup/"*.sh 2>/dev/null || true

  mkdir -p "${AGENT_CREW_DIR}/adapters"
  diff_install "${ADAPTERS_DIR}" "${AGENT_CREW_DIR}/adapters"
  chmod +x "${AGENT_CREW_DIR}/adapters/"*/*.sh 2>/dev/null || true
  chmod +x "${AGENT_CREW_DIR}/adapters/"*/bin/* 2>/dev/null || true

  mkdir -p "${AGENT_CREW_DIR}/commands"
  diff_install "${SOURCE_DIR}/commands" "${AGENT_CREW_DIR}/commands"

  mkdir -p "${AGENT_CREW_DIR}/rules"
  diff_install "${SOURCE_DIR}/rules" "${AGENT_CREW_DIR}/rules"

  mkdir -p "${AGENT_CREW_DIR}/scripts"
  if [ -d "${SOURCE_DIR}/scripts" ]; then
    cp -r "${SOURCE_DIR}/scripts/"* "${AGENT_CREW_DIR}/scripts/" 2>/dev/null || true
    chmod +x "${AGENT_CREW_DIR}/scripts/"*.sh 2>/dev/null || true
    chmod +x "${AGENT_CREW_DIR}/scripts/"*.py 2>/dev/null || true
  fi

  mkdir -p "${AGENT_CREW_DIR}/evaluations"
  if [ -d "${SOURCE_DIR}/evaluations" ]; then
    cp -r "${SOURCE_DIR}/evaluations/"* "${AGENT_CREW_DIR}/evaluations/" 2>/dev/null || true
  fi

  mkdir -p "${AGENT_CREW_DIR}/schemas"
  if [ -d "${SOURCE_DIR}/schemas" ]; then
    cp -r "${SOURCE_DIR}/schemas/"* "${AGENT_CREW_DIR}/schemas/" 2>/dev/null || true
  fi

  write_install_integrity_manifest

  # Auto-migrate legacy flat layout (pre-system/ era):
  # - Non-repo, non-exception agents → user/agents/
  # - Repo agents and system-exception agents → already in system/agents/ (skip)
  # - Remove the legacy directory when fully classified
  if [ -d "${AGENT_CREW_HOME}/agents" ] && [ ! -L "${AGENT_CREW_HOME}/agents" ]; then
    printf '\n[agent-crew] Legacy layout detected at %s/agents/ — migrating...\n' "${AGENT_CREW_HOME}"
    mkdir -p "${AGENT_CREW_HOME}/user/agents"
    if type migrate_legacy_agents &>/dev/null 2>&1; then
      migrate_legacy_agents \
        "${AGENT_CREW_HOME}/agents" \
        "${SOURCE_DIR}/agents" \
        "${AGENT_CREW_HOME}/system/agents" \
        "${AGENT_CREW_HOME}/user/agents" \
        "mcp-manager.md"
    else
      # common.sh not loaded — warn and skip auto-migration
      printf '[agent-crew] NOTE: common.sh not available; skipping auto-migration.\n'
      printf 'If you have custom agents in %s/agents/, move them to %s/user/agents/\n' "${AGENT_CREW_HOME}" "${AGENT_CREW_HOME}"
      printf 'Then you can safely delete %s/agents/\n\n' "${AGENT_CREW_HOME}"
    fi
  fi

  install_codex_bootstrap_skill "${ADAPTERS_DIR}/codex/skill/agent-crew"

  merge_global_settings "${AGENT_CREW_HOME}/settings.json" "${AGENT_CREW_DIR}/hooks/auto-route.sh"
  log_info "Natural-language routing hook registered → ${AGENT_CREW_HOME}/settings.json"

  merge_global_pretooluse "${AGENT_CREW_HOME}/settings.json" "Agent|Task|Delegate" "${AGENT_CREW_DIR}/hooks/context-guard.sh"
  log_info "context-guard hook registered → ${AGENT_CREW_HOME}/settings.json"

  merge_global_pretooluse "${AGENT_CREW_HOME}/settings.json" "Edit|Write" "${AGENT_CREW_DIR}/hooks/direct-edit-guard.sh"
  log_info "direct-edit-guard hook registered → ${AGENT_CREW_HOME}/settings.json"

  # Issue #130: normalize-task-guard.sh — capability-gated defence-in-depth for the
  # AI-agnostic input normalization contract. See core/rules/normalization-adapter.md.
  merge_global_pretooluse "${AGENT_CREW_HOME}/settings.json" "Agent|Task" "${AGENT_CREW_DIR}/hooks/normalize-task-guard.sh"
  log_info "normalize-task-guard hook registered → ${AGENT_CREW_HOME}/settings.json"

  merge_global_pretooluse  "${AGENT_CREW_HOME}/settings.json" "Agent" "${AGENT_CREW_DIR}/hooks/agent-diff-pre.sh"
  merge_global_posttooluse "${AGENT_CREW_HOME}/settings.json" "Agent" "${AGENT_CREW_DIR}/hooks/agent-diff-post.sh"
  merge_global_posttooluse "${AGENT_CREW_HOME}/settings.json" "*"     "${AGENT_CREW_DIR}/hooks/cost-tracker.sh"
  merge_global_posttooluse "${AGENT_CREW_HOME}/settings.json" "*"     "${AGENT_CREW_DIR}/hooks/mnemos-capture-guard.sh"
  log_info "Agent diff + cost-tracker + mnemos-capture-guard hooks registered → ${AGENT_CREW_HOME}/settings.json"

  merge_global_agents "${SOURCE_DIR}/global-agents.md" "${AGENT_CREW_HOME}/AGENTS.md"
  log_info "Global agent guidance applied → ${AGENT_CREW_HOME}/AGENTS.md"

  install_claude_compat

  if [ -n "${TEMP_DIR}" ]; then
    rm -rf "$TEMP_DIR"
  fi
}

install_claude_compat() {
  if [ "${AGENT_CREW_INSTALL_CLAUDE_COMPAT:-1}" = "0" ]; then
    log_info "Skipping Claude compatibility install"
    return
  fi

  # Installation-presence guard (P2): only run the Claude adapter when it has
  # been previously set up on this machine.  During a fresh install the Claude
  # adapter is always installed, so we check the mode first.
  if [ "${AGENT_CREW_MODE}" = "update" ] && [ ! -d "${CLAUDE_DIR}/agent-crew" ]; then
    log_info "Skipping Claude adapter update — not installed on this machine"
    return
  fi

  # Export SOURCE_ROOT so adapters/claude/setup.sh can use sync_system_agents
  # with the correct source reference during install/update runs.
  AGENT_CREW_HOST=claude AGENT_CREW_MODE="${AGENT_CREW_MODE}" \
    AGENT_CREW_WRITE_CAPABILITIES=0 SOURCE_ROOT="${SOURCE_ROOT}" \
    "${AGENT_CREW_HOME}/setup/setup-host.sh" "$(pwd)" >/dev/null
  merge_global_settings "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/auto-route.sh"
  merge_global_pretooluse "${CLAUDE_DIR}/settings.json" "Agent|Task|Delegate" "${CLAUDE_DIR}/agent-crew/hooks/context-guard.sh"
  merge_global_pretooluse "${CLAUDE_DIR}/settings.json" "Edit|Write" "${CLAUDE_DIR}/agent-crew/hooks/direct-edit-guard.sh"
  # Issue #130: AI-agnostic input normalization enforcement.
  merge_global_pretooluse "${CLAUDE_DIR}/settings.json" "Agent|Task" "${CLAUDE_DIR}/agent-crew/hooks/normalize-task-guard.sh"
  merge_global_pretooluse  "${CLAUDE_DIR}/settings.json" "Agent" "${CLAUDE_DIR}/agent-crew/hooks/agent-diff-pre.sh"
  merge_global_posttooluse "${CLAUDE_DIR}/settings.json" "Agent" "${CLAUDE_DIR}/agent-crew/hooks/agent-diff-post.sh"
  merge_global_posttooluse "${CLAUDE_DIR}/settings.json" "*"     "${CLAUDE_DIR}/agent-crew/hooks/cost-tracker.sh"
  merge_global_posttooluse "${CLAUDE_DIR}/settings.json" "*"     "${CLAUDE_DIR}/agent-crew/hooks/mnemos-capture-guard.sh"
  log_info "Agent diff + cost-tracker + mnemos-capture-guard hooks registered → ${CLAUDE_DIR}/settings.json"
  log_info "Claude compatibility layer installed → ${CLAUDE_DIR}/"
}

install_codex_bootstrap_skill() {
  local source_skill_dir="$1"
  local codex_home="${CODEX_HOME:-${HOME}/.codex}"
  local dest_skill_dir="${codex_home}/skills/agent-crew"

  if [ ! -d "${source_skill_dir}" ]; then
    log_warn "Skipping Codex bootstrap skill — source not found (${source_skill_dir})"
    return
  fi

  # Installation-presence guard (P2): in update mode, only refresh the Codex
  # bootstrap skill when Codex has been previously installed on this machine.
  if [ "${AGENT_CREW_MODE}" = "update" ] && [ ! -d "${dest_skill_dir}" ]; then
    log_info "Skipping Codex bootstrap skill update — not installed on this machine"
    return
  fi

  mkdir -p "${dest_skill_dir}"
  diff_install "${source_skill_dir}" "${dest_skill_dir}"
  log_info "Codex bootstrap skill installed → ${dest_skill_dir}"
}

# Safely merge UserPromptSubmit hook into a settings.json file.
merge_global_settings() {
  local dest="$1" hook_path="$2"

  python3 - "$dest" "$hook_path" <<'PYEOF'
import sys, json, os

dest, hook_path = sys.argv[1], sys.argv[2]

hook_entry = {
  "type": "command",
  "command": f"bash {hook_path}",
  "timeout": 5
}
hook_block = {"hooks": [hook_entry]}

if os.path.exists(dest):
  with open(dest) as f:
    try:
      settings = json.load(f)
    except json.JSONDecodeError:
      settings = {}
else:
  settings = {}

hooks = settings.setdefault("hooks", {})
user_prompt_hooks = hooks.setdefault("UserPromptSubmit", [])

# Update an existing auto-route hook, or add it when missing.
for block in user_prompt_hooks:
  for h in block.get("hooks", []):
    if "auto-route" in h.get("command", ""):
      h["command"] = hook_entry["command"]
      break
  else:
    continue
  break
else:
  user_prompt_hooks.append(hook_block)

with open(dest, "w") as f:
  json.dump(settings, f, indent=2, ensure_ascii=False)
  f.write("\n")
PYEOF
}

# Safely merge PreToolUse hook into a settings.json file.
merge_global_pretooluse() {
  local dest="$1" matcher="$2" hook_path="$3"

  python3 - "$dest" "$matcher" "$hook_path" <<'PYEOF'
import sys, json, os

dest, matcher, hook_path = sys.argv[1], sys.argv[2], sys.argv[3]

hook_entry = {
  "type": "command",
  "command": f"bash {hook_path}",
  "timeout": 5
}

if os.path.exists(dest):
  with open(dest) as f:
    try:
      settings = json.load(f)
    except json.JSONDecodeError:
      settings = {}
else:
  settings = {}

hooks = settings.setdefault("hooks", {})
pretooluse_hooks = hooks.setdefault("PreToolUse", [])

# Update an existing matcher + hook path, or append it when missing.
hook_path_base = os.path.basename(hook_path)
for block in pretooluse_hooks:
  if block.get("matcher") == matcher:
    for h in block.get("hooks", []):
      if hook_path_base in h.get("command", ""):
        h["command"] = hook_entry["command"]
        break
    else:
      block.setdefault("hooks", []).append(hook_entry)
    break
else:
  pretooluse_hooks.append({"matcher": matcher, "hooks": [hook_entry]})

with open(dest, "w") as f:
  json.dump(settings, f, indent=2, ensure_ascii=False)
  f.write("\n")
PYEOF
}

# Safely merge PostToolUse hook into a settings.json file.
merge_global_posttooluse() {
  local dest="$1" matcher="$2" hook_path="$3"

  python3 - "$dest" "$matcher" "$hook_path" <<'PYEOF'
import sys, json, os

dest, matcher, hook_path = sys.argv[1], sys.argv[2], sys.argv[3]

hook_entry = {
  "type": "command",
  "command": f"bash {hook_path}",
  "timeout": 10
}

if os.path.exists(dest):
  with open(dest) as f:
    try:
      settings = json.load(f)
    except json.JSONDecodeError:
      settings = {}
else:
  settings = {}

hooks = settings.setdefault("hooks", {})
posttooluse_hooks = hooks.setdefault("PostToolUse", [])

hook_path_base = os.path.basename(hook_path)
for block in posttooluse_hooks:
  if block.get("matcher") == matcher:
    for h in block.get("hooks", []):
      if hook_path_base in h.get("command", ""):
        h["command"] = hook_entry["command"]
        break
    else:
      block.setdefault("hooks", []).append(hook_entry)
    break
else:
  posttooluse_hooks.append({"matcher": matcher, "hooks": [hook_entry]})

with open(dest, "w") as f:
  json.dump(settings, f, indent=2, ensure_ascii=False)
  f.write("\n")
PYEOF
}

# Install canonical global agent guidance.
#
# ~/.agent-crew/AGENTS.md is owned by agent-crew and is later embedded into
# host/project AGENTS files by adapters. Do not marker-merge this file: if an
# older install left stale guidance outside the marker block, preserving that
# prefix causes Codex to read contradictory command rules before the current
# section.
merge_global_agents() {
  local src="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  diff_copy "$src" "$dest"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  install_global
  print_diff_summary

  CMD_COUNT=$(ls "${AGENT_CREW_HOME}/system/commands/"*.md 2>/dev/null | wc -l | tr -d ' ')
  AGENT_COUNT=$(ls "${AGENT_CREW_DIR}/system/agents/"*.md 2>/dev/null | wc -l | tr -d ' ')

  echo ""
  echo -e "${GREEN}========================================${NC}"
  echo -e "${GREEN}  agent-crew global install complete!${NC}"
  echo -e "${GREEN}========================================${NC}"
  echo ""
  echo "  Install path: ${AGENT_CREW_DIR}"
  echo "  Installed commands: ${CMD_COUNT} / agents: ${AGENT_COUNT}"
  echo ""
  echo "  Native shell entrypoint:"
  echo "    crew setup                       # host adapter install + workspace init"
  echo "    crew status                      # deterministic local state snapshot"
  echo "    crew update --local [SOURCE]     # refresh install from a checkout"
  echo ""
  echo "  Guided host-runtime commands:"
  echo "    crew:run \"request\"              # run one task through supervisor"
  echo "    crew:run \"TaskA\" | \"TaskB\"      # run independent tasks in parallel"
  echo "    crew:cost                        # show session cost summary"
  echo ""
  echo "  Agent creation:"
  echo "    crew:agent-maker                 # design and create AGENTS.md / Skill / Subagent / Hook files"
  echo "  Agent layers:"
  echo "    ~/.agent-crew/system/agents/  # crew-managed built-in agents (updated by crew:update)"
  echo "    ~/.agent-crew/user/agents/    # user-managed custom agents (never overwritten)"
  echo "    ~/.claude/agents/             # generated merge destination (do not edit directly)"
  echo ""
  echo "  Codex is currently guided prompt mode for crew:run/crew:agent."
  echo -e "${GREEN}  Start in a project with crew setup.${NC}"
  echo ""
fi
