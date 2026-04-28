#!/usr/bin/env bash
# crew-status — agent-crew 전체 상태 패널 출력
# Usage:
#   crew-status              — 활성(IN_PROGRESS) 프로젝트만 출력
#   crew-status --all        — 모든 프로젝트 출력
#   crew-status --live       — 2초마다 실시간 갱신 (q:종료 r:즉시갱신 Ctrl+C 종료)
#   crew-status --live 5     — 5초마다 실시간 갱신

AGENT_CREW_DIR="${HOME}/.claude/agent-crew"
CURRENT_PROJECT=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")

if [[ "${1:-}" == "--live" ]]; then
  INTERVAL="${2:-2}"
  tput smcup 2>/dev/null
  tput civis 2>/dev/null
  _restore() { stty "$_STTY_SAVE" 2>/dev/null; tput rmcup 2>/dev/null; tput cnorm 2>/dev/null; }
  _STTY_SAVE=$(stty -g 2>/dev/null)
  trap '_restore; exit 0' INT TERM EXIT
  stty -echo -icanon min 0 time 0 2>/dev/null
  while true; do
    tput cup 0 0 2>/dev/null
    bash "$0" "${@:3}"
    tput ed 2>/dev/null
    key=""
    IFS= read -r -t "$INTERVAL" -n 1 key 2>/dev/null || true
    # drain leftover bytes from multi-byte sequences (e.g. arrow keys: ESC [ A)
    while IFS= read -r -t 0.05 -n 1 2>/dev/null; do :; done
    case "$key" in
      q|Q) exit 0 ;;
      r|R) continue ;;
    esac
  done
  exit 0
fi

EXTRA_FLAGS=""
[[ "${1:-}" == "--all" ]] && EXTRA_FLAGS="--all"

python3 "${AGENT_CREW_DIR}/lib/crew-status.py" "$AGENT_CREW_DIR" "$CURRENT_PROJECT" $EXTRA_FLAGS
