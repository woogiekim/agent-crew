#!/usr/bin/env bash
# crew-status — agent-crew 상태 패널 출력
# Usage:
#   bash crew-status.sh              — 현재 상태 1회 출력
#   watch -n 2 bash crew-status.sh   — 2초마다 실시간 갱신

PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}"

# ── 컬러 ────────────────────────────────────────────────────────
RESET='\033[0m'
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
DIM='\033[2m'

# ── 상태 읽기 ────────────────────────────────────────────────────
read_file() { [ -f "$1" ] && cat "$1" || echo "${2:--}"; }

PHASE=$(read_file "${STATE_DIR}/phase.txt")
ACTIVE_AGENT=$(read_file "${STATE_DIR}/active_agent.txt")
ITERATIONS=$(read_file "${STATE_DIR}/iterations.txt" "0")
EVENTS_COUNT=0
[ -f "${STATE_DIR}/events.jsonl" ] && EVENTS_COUNT=$(wc -l < "${STATE_DIR}/events.jsonl" | tr -d ' ')

# pipeline.json 파싱
TASK="-"
AGENTS_LIST=""
CURRENT_INDEX=0
PIPELINE_STATUS="PENDING"
if [ -f "${STATE_DIR}/pipeline.json" ]; then
  TASK=$(python3 -c "import json; p=json.load(open('${STATE_DIR}/pipeline.json')); print(p.get('task','')[:50] or '-')" 2>/dev/null || echo "-")
  CURRENT_INDEX=$(python3 -c "import json; p=json.load(open('${STATE_DIR}/pipeline.json')); print(p.get('currentIndex',0))" 2>/dev/null || echo "0")
  PIPELINE_STATUS=$(python3 -c "import json; p=json.load(open('${STATE_DIR}/pipeline.json')); print(p.get('status','PENDING'))" 2>/dev/null || echo "PENDING")
  AGENTS_LIST=$(python3 -c "
import json
p = json.load(open('${STATE_DIR}/pipeline.json'))
agents = p.get('agents', [])
idx = p.get('currentIndex', 0)
parts = []
for i, a in enumerate(agents):
    if i < idx:
        parts.append(f'✓ {a}')
    elif i == idx:
        parts.append(f'▶ {a}')
    else:
        parts.append(f'○ {a}')
print('  →  '.join(parts) if parts else '-')
" 2>/dev/null || echo "-")
fi

# 데몬 상태
DAEMON_STATUS="${RED}● STOPPED${RESET}"
DAEMON_PID="-"
if [ -f "${STATE_DIR}/orchestrator.pid" ]; then
  PID=$(cat "${STATE_DIR}/orchestrator.pid")
  if kill -0 "$PID" 2>/dev/null; then
    DAEMON_STATUS="${GREEN}● RUNNING${RESET}"
    DAEMON_PID="$PID"
  else
    DAEMON_STATUS="${YELLOW}● STALE${RESET}  (stale pid)"
  fi
fi

# 파이프라인 상태 컬러
case "$PIPELINE_STATUS" in
  DONE)        STATUS_COLOR="${GREEN}" ;;
  FAILED)      STATUS_COLOR="${RED}" ;;
  IN_PROGRESS) STATUS_COLOR="${CYAN}" ;;
  *)           STATUS_COLOR="${DIM}" ;;
esac

# 페이즈 컬러
case "$PHASE" in
  DONE)           PHASE_COLOR="${GREEN}" ;;
  IMPLEMENTATION) PHASE_COLOR="${CYAN}" ;;
  VERIFICATION)   PHASE_COLOR="${YELLOW}" ;;
  DESIGN)         PHASE_COLOR="${CYAN}" ;;
  REQUIREMENTS)   PHASE_COLOR="${DIM}" ;;
  *)              PHASE_COLOR="${DIM}" ;;
esac

W=52  # 패널 너비

# ── 렌더 ────────────────────────────────────────────────────────
line() { printf "║ %-${W}s ║\n" "$1"; }
divider() { printf "╠%s╣\n" "$(printf '═%.0s' $(seq 1 $((W+2))))"; }
top()     { printf "╔%s╗\n" "$(printf '═%.0s' $(seq 1 $((W+2))))"; }
bottom()  { printf "╚%s╝\n" "$(printf '═%.0s' $(seq 1 $((W+2))))"; }

echo ""
top
printf "║ ${BOLD}${CYAN}agent-crew${RESET}  %-$((W-10))s ║\n" "project: ${PROJECT_NAME}"
divider
printf "║ ${BOLD}Task   ${RESET} %-$((W-7))s ║\n" "${TASK}"
printf "║ ${BOLD}Status ${RESET} ${STATUS_COLOR}%-$((W-7))s${RESET} ║\n" "${PIPELINE_STATUS}"
printf "║ ${BOLD}Phase  ${RESET} ${PHASE_COLOR}%-$((W-7))s${RESET} ║\n" "${PHASE}"
printf "║ ${BOLD}Agent  ${RESET} %-$((W-7))s ║\n" "${ACTIVE_AGENT}"
divider
printf "║ ${DIM}Pipeline Progress${RESET}%-$((W-17))s ║\n" ""
printf "║   %-${W}s ║\n" "${AGENTS_LIST}"
divider
printf "║ ${BOLD}Daemon ${RESET} $(echo -e ${DAEMON_STATUS})%-$((W-18))s ║\n" "  PID: ${DAEMON_PID}"
printf "║ ${BOLD}Events ${RESET} %-$((W-7))s ║\n" "${EVENTS_COUNT} processed  |  iterations: ${ITERATIONS}"
bottom
echo ""
printf "${DIM}  Live: watch -n 2 bash ~/.claude/agent-crew/crew-status.sh${RESET}\n"
echo ""
