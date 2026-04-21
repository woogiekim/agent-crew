#!/usr/bin/env bash
# crew-status — agent-crew 전체 상태 패널 출력
# Usage:
#   crew-status              — 모든 프로젝트 상태 1회 출력
#   crew-status --live       — 2초마다 실시간 갱신 (Ctrl+C 종료)
#   crew-status --live 5     — 5초마다 실시간 갱신

AGENT_CREW_DIR="${HOME}/.claude/agent-crew"
CURRENT_PROJECT=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")

if [[ "${1:-}" == "--live" ]]; then
  INTERVAL="${2:-2}"
  tput smcup 2>/dev/null
  tput civis 2>/dev/null
  trap 'tput rmcup 2>/dev/null; tput cnorm 2>/dev/null; exit 0' INT TERM
  while true; do
    tput cup 0 0
    bash "$0"
    sleep "$INTERVAL"
  done
  exit 0
fi

python3 "${AGENT_CREW_DIR}/lib/crew-status.py" "$AGENT_CREW_DIR" "$CURRENT_PROJECT"
