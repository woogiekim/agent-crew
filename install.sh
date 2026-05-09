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

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
log_error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
log_section() { echo -e "\n${GREEN}▶ $1${NC}"; }

# Check for an existing installation.
if [ -d "${AGENT_CREW_DIR}/agents" ]; then
  log_warn "agent-crew is already installed (${AGENT_CREW_DIR})"
  read -p "Reinstall? [Y/N] " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Installation cancelled."
    exit 0
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

  mkdir -p "${AGENT_CREW_HOME}/commands"
  cp -r "${SOURCE_DIR}/commands/"* "${AGENT_CREW_HOME}/commands/"
  log_info "Commands installed → ${AGENT_CREW_HOME}/commands/"

  [ -f "${AGENT_CREW_HOME}/commands/agent-maker.md" ] \
    || log_error "agent-maker.md install failed — commands/agent-maker.md not found"
  log_info "agent-maker command verified"

  mkdir -p "${AGENT_CREW_DIR}/agents/skills"
  cp "${SOURCE_DIR}/agents/"*.md "${AGENT_CREW_DIR}/agents/" 2>/dev/null || true
  cp "${SOURCE_DIR}/agents/skills/"*.md "${AGENT_CREW_DIR}/agents/skills/" 2>/dev/null || true
  log_info "Agents installed → ${AGENT_CREW_DIR}/agents/"
  log_info "Skills installed → ${AGENT_CREW_DIR}/agents/skills/"

  mkdir -p "${AGENT_CREW_DIR}/rules"
  cp "${SOURCE_DIR}/rules/"*.md "${AGENT_CREW_DIR}/rules/" 2>/dev/null || true
  log_info "Rules installed → ${AGENT_CREW_DIR}/rules/"

  mkdir -p "${AGENT_CREW_DIR}/hooks"
  cp -r "${SOURCE_DIR}/hooks/"* "${AGENT_CREW_DIR}/hooks/"
  chmod +x "${AGENT_CREW_DIR}/hooks/"*.sh 2>/dev/null || true
  log_info "Hooks installed → ${AGENT_CREW_DIR}/hooks/"

  mkdir -p "${AGENT_CREW_DIR}/setup"
  cp -r "${SOURCE_DIR}/setup/"* "${AGENT_CREW_DIR}/setup/"
  chmod +x "${AGENT_CREW_DIR}/setup/"*.sh 2>/dev/null || true
  log_info "Setup dispatcher installed → ${AGENT_CREW_DIR}/setup/"

  mkdir -p "${AGENT_CREW_DIR}/adapters"
  cp -R "${ADAPTERS_DIR}/." "${AGENT_CREW_DIR}/adapters/"
  chmod +x "${AGENT_CREW_DIR}/adapters/"*/*.sh 2>/dev/null || true
  find "${AGENT_CREW_DIR}" -name ".DS_Store" -delete 2>/dev/null || true
  log_info "Host adapters installed → ${AGENT_CREW_DIR}/adapters/"

  [ -f "${AGENT_CREW_DIR}/hooks/auto-route.sh" ] \
    || log_error "auto-route.sh install failed — hooks/auto-route.sh not found"

  merge_global_settings "${AGENT_CREW_HOME}/settings.json" "${AGENT_CREW_DIR}/hooks/auto-route.sh"
  log_info "Natural-language routing hook registered → ${AGENT_CREW_HOME}/settings.json"

  merge_global_pretooluse "${AGENT_CREW_HOME}/settings.json" "Agent|Task|Delegate" "${AGENT_CREW_DIR}/hooks/context-guard.sh"
  log_info "context-guard hook registered → ${AGENT_CREW_HOME}/settings.json"

  merge_global_pretooluse "${AGENT_CREW_HOME}/settings.json" "Edit|Write" "${AGENT_CREW_DIR}/hooks/direct-edit-guard.sh"
  log_info "direct-edit-guard hook registered → ${AGENT_CREW_HOME}/settings.json"

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

  AGENT_CREW_HOST=claude "${AGENT_CREW_HOME}/setup/setup-host.sh" "$(pwd)" >/dev/null
  merge_global_settings "${CLAUDE_DIR}/settings.json" "${CLAUDE_DIR}/agent-crew/hooks/auto-route.sh"
  merge_global_pretooluse "${CLAUDE_DIR}/settings.json" "Agent" "${CLAUDE_DIR}/agent-crew/hooks/context-guard.sh"
  merge_global_pretooluse "${CLAUDE_DIR}/settings.json" "Edit|Write" "${CLAUDE_DIR}/agent-crew/hooks/direct-edit-guard.sh"
  log_info "Claude compatibility layer installed → ${CLAUDE_DIR}/"
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

# Merge the agent-crew section by marker while preserving existing content.
merge_global_agents() {
  local src="$1" dest="$2"
  local start="<!-- agent-crew-start -->" end="<!-- agent-crew-end -->"
  local new_section
  new_section=$(printf '%s\n%s\n%s' "$start" "$(cat "$src")" "$end")

  if [ ! -f "$dest" ]; then
    printf '%s\n' "$new_section" > "$dest"
    return
  fi

  python3 - "$dest" "$start" "$end" "$new_section" <<'PYEOF'
import sys, re
dest, start, end, new_section = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
content = open(dest).read()
pattern = re.escape(start) + r'.*' + re.escape(end)
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, new_section, content, count=1, flags=re.DOTALL)
else:
    content = content.rstrip('\n') + '\n\n' + new_section + '\n'
open(dest, 'w').write(content)
PYEOF
}

install_global

CMD_COUNT=$(ls "${AGENT_CREW_HOME}/commands/"*.md 2>/dev/null | wc -l | tr -d ' ')
AGENT_COUNT=$(ls "${AGENT_CREW_DIR}/agents/"*.md 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  agent-crew global install complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Install path: ${AGENT_CREW_DIR}"
echo "  Installed commands: ${CMD_COUNT} / agents: ${AGENT_COUNT}"
echo ""
echo "  Provider-neutral usage from any project:"
echo "    crew:setup                       # host adapter install + workspace init"
echo "    crew:run \"request\"              # run one task through task-runner"
echo "    crew:run \"TaskA\" | \"TaskB\"      # run independent tasks in parallel"
echo "    crew:cost                        # show session cost summary"
echo ""
echo "  Agent creation:"
echo "    crew:agent-maker                 # design and create AGENTS.md / Skill / Subagent / Hook files"
echo ""
echo "  Host adapters may expose native aliases such as slash commands."
echo -e "${GREEN}  Start in a project with crew:setup.${NC}"
echo ""
