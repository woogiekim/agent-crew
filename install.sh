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

  # ~/.claude/agent-crew/agents/ 에 에이전트 설치
  mkdir -p "${AGENT_CREW_DIR}/agents"
  cp -r "$TEMP_DIR/.claude/agents/"* "${AGENT_CREW_DIR}/agents/"
  log_info "에이전트 설치 완료 → ${AGENT_CREW_DIR}/agents/"

  # hooks 설치
  mkdir -p "${AGENT_CREW_DIR}/hooks"
  cp -r "$TEMP_DIR/.claude/hooks/"* "${AGENT_CREW_DIR}/hooks/"
  chmod +x "${AGENT_CREW_DIR}/hooks/"*.sh 2>/dev/null || true
  log_info "훅 설치 완료 → ${AGENT_CREW_DIR}/hooks/"

  # crew-daemon, crew-status, lib 설치
  cp "$TEMP_DIR/.claude/crew-daemon.sh" "${AGENT_CREW_DIR}/crew-daemon.sh"
  cp "$TEMP_DIR/.claude/crew-status.sh" "${AGENT_CREW_DIR}/crew-status.sh"
  chmod +x "${AGENT_CREW_DIR}/crew-daemon.sh" "${AGENT_CREW_DIR}/crew-status.sh"
  mkdir -p "${AGENT_CREW_DIR}/lib"
  cp -r "$TEMP_DIR/.claude/lib/"* "${AGENT_CREW_DIR}/lib/"
  log_info "crew-daemon 설치 완료 → ${AGENT_CREW_DIR}/crew-daemon.sh"
  log_info "crew-status 설치 완료 → ${AGENT_CREW_DIR}/crew-status.sh"
  log_info "lib 설치 완료 → ${AGENT_CREW_DIR}/lib/"

  # ~/.local/bin 에 PATH 명령어로 설치
  BIN_DIR="${HOME}/.local/bin"
  mkdir -p "$BIN_DIR"
  ln -sf "${AGENT_CREW_DIR}/crew-status.sh" "${BIN_DIR}/crew-status"
  ln -sf "${AGENT_CREW_DIR}/crew-daemon.sh" "${BIN_DIR}/crew-daemon"
  chmod +x "${BIN_DIR}/crew-status" "${BIN_DIR}/crew-daemon"
  log_info "명령어 설치 완료 → ${BIN_DIR}/crew-status, crew-daemon"

  # PATH에 없으면 셸 설정에 추가
  if ! echo "$PATH" | grep -q "${BIN_DIR}"; then
    SHELL_RC="${HOME}/.zshrc"
    [[ "$SHELL" == *bash* ]] && SHELL_RC="${HOME}/.bashrc"
    echo "export PATH=\"${BIN_DIR}:\$PATH\"" >> "$SHELL_RC"
    log_warn "PATH 추가됨 → ${SHELL_RC}  (새 터미널 또는 source ${SHELL_RC} 필요)"
  fi

  rm -rf "$TEMP_DIR"
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
echo "    /requirements        # 요구사항 단계"
echo "    /design              # 설계 단계"
echo "    /implement           # 구현 단계"
echo "    /verify              # 검증 단계"
echo ""
echo -e "${GREEN}  새 프로젝트에서 /setup 으로 시작하세요.${NC}"
echo ""
