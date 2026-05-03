#!/bin/bash
# =============================================================
# AI Agent Crew — Global Installer
# Usage:
#   curl -s https://raw.githubusercontent.com/woogiekim/agent-crew/main/install.sh | bash
# =============================================================

set -e

REPO_URL="https://github.com/woogiekim/agent-crew"
GLOBAL_DIR="${HOME}/.claude"
AGENT_CREW_DIR="${GLOBAL_DIR}/agent-crew"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
log_error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
log_section() { echo -e "\n${GREEN}▶ $1${NC}"; }

# 이미 설치된 경우 확인
if [ -d "${AGENT_CREW_DIR}/agents" ]; then
  log_warn "agent-crew가 이미 설치되어 있습니다 (${AGENT_CREW_DIR})"
  read -p "재설치할까요? [y/N] " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "설치를 취소합니다."
    exit 0
  fi
fi

# ── 글로벌 설치 ──────────────────────────────────────────────
install_global() {
  log_section "글로벌 설치를 시작합니다"

  TEMP_DIR=$(mktemp -d)

  if command -v git &>/dev/null; then
    log_info "레포 클론 중..."
    git clone --depth 1 "$REPO_URL" "$TEMP_DIR" 2>/dev/null
  else
    log_error "git이 설치되어 있지 않습니다."
  fi

  # ~/.claude/commands/ 에 명령어 설치 (글로벌)
  mkdir -p "${GLOBAL_DIR}/commands"
  cp -r "$TEMP_DIR/.claude/commands/"* "${GLOBAL_DIR}/commands/"
  log_info "명령어 설치 완료 → ${GLOBAL_DIR}/commands/"

  # ~/.claude/agent-crew/agents/ 에 에이전트 정의 설치 (flat .md 구조)
  mkdir -p "${AGENT_CREW_DIR}/agents/skills"
  cp "$TEMP_DIR/.claude/agents/"*.md "${AGENT_CREW_DIR}/agents/" 2>/dev/null || true
  cp "$TEMP_DIR/.claude/agents/skills/"*.md "${AGENT_CREW_DIR}/agents/skills/" 2>/dev/null || true
  log_info "에이전트 설치 완료 → ${AGENT_CREW_DIR}/agents/"
  log_info "스킬 설치 완료 → ${AGENT_CREW_DIR}/agents/skills/"

  # hooks 설치
  mkdir -p "${AGENT_CREW_DIR}/hooks"
  cp -r "$TEMP_DIR/.claude/hooks/"* "${AGENT_CREW_DIR}/hooks/"
  chmod +x "${AGENT_CREW_DIR}/hooks/"*.sh 2>/dev/null || true
  log_info "훅 설치 완료 → ${AGENT_CREW_DIR}/hooks/"

  # ~/.claude/settings.json 에 UserPromptSubmit 훅 등록 (모든 프로젝트에서 동작)
  merge_global_settings "${GLOBAL_DIR}/settings.json" "${AGENT_CREW_DIR}/hooks/auto-route.sh"
  log_info "글로벌 훅 등록 완료 → ${GLOBAL_DIR}/settings.json"

  # ~/.claude/CLAUDE.md 에 전역 Claude 규칙 병합
  merge_global_claude "$TEMP_DIR/.claude/global-claude.md" "${GLOBAL_DIR}/CLAUDE.md"
  log_info "전역 Claude 규칙 적용 완료 → ${GLOBAL_DIR}/CLAUDE.md"

  rm -rf "$TEMP_DIR"
}

# ~/.claude/settings.json 에 UserPromptSubmit 훅을 안전하게 병합
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

# 이미 등록된 경우 업데이트, 없으면 추가
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

# agent-crew 섹션을 마커 기반으로 병합 (기존 내용 유지)
merge_global_claude() {
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
pattern = re.escape(start) + r'.*?' + re.escape(end)
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, new_section, content, flags=re.DOTALL)
else:
    content = content.rstrip('\n') + '\n\n' + new_section + '\n'
open(dest, 'w').write(content)
PYEOF
}

install_global

# ── 완료 메시지 ──────────────────────────────────────────────
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  agent-crew 글로벌 설치 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  설치 위치: ${AGENT_CREW_DIR}"
echo ""
echo "  사용 방법 (모든 프로젝트에서 사용 가능):"
echo "    /setup               # 현재 프로젝트 워크스페이스 초기화"
echo "    /ship \"요청 내용\"    # 전체 파이프라인 자동 실행"
echo ""
echo -e "${GREEN}  새 프로젝트에서 /setup 으로 시작하세요.${NC}"
echo ""
