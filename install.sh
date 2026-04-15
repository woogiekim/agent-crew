#!/bin/bash
# =============================================================
# AI Agent Workspace Installer
# Usage:
#   curl -s https://raw.githubusercontent.com/woogiekim/ai-agents/main/install.sh | bash
#   curl -s https://raw.githubusercontent.com/woogiekim/ai-agents/main/install.sh | bash -s -- --submodule
# =============================================================

set -e

REPO_URL="https://github.com/woogiekim/agent-crew"
REPO_RAW="https://raw.githubusercontent.com/woogiekim/agent-crew/main"
AGENT_DIR=".claude"
INSTALL_MODE="copy"  # copy | submodule

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
log_error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
log_section() { echo -e "\n${GREEN}▶ $1${NC}"; }

# 인자 파싱
for arg in "$@"; do
  case $arg in
    --submodule) INSTALL_MODE="submodule" ;;
    --copy)      INSTALL_MODE="copy" ;;
  esac
done

# Git 레포 여부 확인
if [ ! -d ".git" ]; then
  log_error "Git 레포가 아닙니다. 프로젝트 루트에서 실행하세요."
fi

# 이미 설치된 경우 확인
if [ -d "$AGENT_DIR" ]; then
  log_warn ".claude 디렉토리가 이미 존재합니다."
  read -p "덮어쓰시겠습니까? [y/N] " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "설치를 취소합니다."
    exit 0
  fi
  rm -rf "$AGENT_DIR"
fi

# ── Submodule 방식 ──────────────────────────────────────────
install_submodule() {
  log_section "Submodule 방식으로 설치합니다"

  SUBMODULE_PATH=".claude-agents"

  # 기존 submodule 제거
  if git submodule status "$SUBMODULE_PATH" &>/dev/null 2>&1; then
    log_warn "기존 submodule 제거 중..."
    git submodule deinit -f "$SUBMODULE_PATH" 2>/dev/null || true
    git rm -f "$SUBMODULE_PATH" 2>/dev/null || true
    rm -rf ".git/modules/$SUBMODULE_PATH"
  fi

  log_info "Submodule 추가: $REPO_URL"
  git submodule add "$REPO_URL" "$SUBMODULE_PATH"
  git submodule update --init --recursive

  log_info "심볼릭 링크 생성: .claude → .claude-agents/.claude"
  ln -sf ".claude-agents/.claude" ".claude"

  # .gitignore에 .claude 링크 추가
  if ! grep -q "^\.claude$" .gitignore 2>/dev/null; then
    echo ".claude" >> .gitignore
    log_info ".gitignore에 .claude 추가"
  fi

  log_info "Submodule 커밋"
  git add .gitmodules "$SUBMODULE_PATH" .gitignore
  git commit -m "chore: add ai-agents as submodule" --no-verify 2>/dev/null || true
}

# ── Copy 방식 ───────────────────────────────────────────────
install_copy() {
  log_section "Copy 방식으로 설치합니다"

  # curl 또는 git clone으로 다운로드
  if command -v git &>/dev/null; then
    log_info "레포 클론 중..."
    TEMP_DIR=$(mktemp -d)
    git clone --depth 1 "$REPO_URL" "$TEMP_DIR" 2>/dev/null
    cp -r "$TEMP_DIR/.claude" "./"
    rm -rf "$TEMP_DIR"
  else
    log_error "git이 설치되어 있지 않습니다."
  fi

  log_info ".claude 복사 완료"
}

# ── 공통: 초기 상태 파일 생성 ────────────────────────────────
init_state() {
  log_section "초기 상태 초기화"

  mkdir -p ".claude/state/context"

  echo "REQUIREMENTS"  > ".claude/state/phase.txt"
  echo "0"             > ".claude/state/iterations.txt"
  echo "backend"       > ".claude/state/active_agent.txt"

  cat > ".claude/state/context/session_handoff.md" << 'EOF'
# Session Handoff
## 마지막 갱신
(초기 상태)
## 완료된 작업
없음
## 미완료 작업
요구사항 수집 대기 중
## 다음 세션 컨텍스트
- 페이즈: REQUIREMENTS
- 에이전트: backend
- 반복: 0
EOF

  log_info "상태 파일 초기화 완료"
}

# ── 공통: Hook 실행 권한 부여 ─────────────────────────────────
set_permissions() {
  log_section "Hook 권한 설정"
  chmod +x .claude/hooks/*.sh 2>/dev/null || true
  log_info "Hook 실행 권한 부여 완료"
}

# ── 설치 실행 ────────────────────────────────────────────────
case "$INSTALL_MODE" in
  submodule) install_submodule ;;
  copy)      install_copy ;;
esac

init_state
set_permissions

# ── 완료 메시지 ──────────────────────────────────────────────
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  AI Agent Workspace 설치 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  설치 방식 : $INSTALL_MODE"
echo "  에이전트  : backend (기획자/디자이너/프론트엔드 예정)"
echo ""
echo "  사용 방법:"
echo "    claude                # Claude Code 실행"
echo "    /requirements         # 1단계: 요구사항 수집"
echo "    /design               # 2단계: 설계"
echo "    /implement            # 3단계: TDD 구현"
echo "    /verify               # 4단계: 검증"
echo ""
echo "  병렬 실행:"
echo "    claude --worktree agent/backend"
echo "    claude --worktree agent/planner"
echo ""
if [ "$INSTALL_MODE" = "submodule" ]; then
  echo "  에이전트 업데이트:"
  echo "    git submodule update --remote .claude-agents"
  echo ""
fi
echo -e "${GREEN}  README.md 를 참고하세요.${NC}"
echo ""
