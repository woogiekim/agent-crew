#!/usr/bin/env bash
# crew-daemon — agent-crew 파이프라인 오케스트레이터 데몬
# Usage:
#   crew-daemon.sh          — start (default)
#   crew-daemon.sh start    — start
#   crew-daemon.sh stop     — stop running instance
#   crew-daemon.sh status   — check if running
set -euo pipefail

PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}"
EVENTS_FILE="${STATE_DIR}/events.jsonl"
OFFSET_FILE="${STATE_DIR}/events.offset"
PID_FILE="${STATE_DIR}/orchestrator.pid"
SIGNAL_DIR="${STATE_DIR}/agent_signal"
PIPELINE_FILE="${STATE_DIR}/pipeline.json"
PHASE_FILE="${STATE_DIR}/phase.txt"

# 이벤트 없을 때 자동 종료까지의 최대 유휴 시간 (초)
IDLE_TIMEOUT=1800  # 30분

# ── stop / status ────────────────────────────────────────────────
CMD="${1:-start}"

case "$CMD" in
  stop)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        echo "[crew-daemon] 종료 요청 (PID $PID)"
      else
        echo "[crew-daemon] 이미 종료된 프로세스 (PID $PID)"
        rm -f "$PID_FILE"
      fi
    else
      echo "[crew-daemon] 실행 중인 데몬 없음"
    fi
    exit 0
    ;;
  status)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      if kill -0 "$PID" 2>/dev/null; then
        echo "[crew-daemon] 실행 중 (PID $PID, project: ${PROJECT_NAME})"
      else
        echo "[crew-daemon] 종료됨 (stale PID file)"
        rm -f "$PID_FILE"
      fi
    else
      echo "[crew-daemon] 실행 중인 데몬 없음"
    fi
    exit 0
    ;;
  start) ;;
  *) echo "Usage: $0 [start|stop|status]"; exit 1 ;;
esac

# ── 중복 실행 방지 ───────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
  EXISTING_PID=$(cat "$PID_FILE")
  if kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "[crew-daemon] 이미 실행 중 (PID $EXISTING_PID). 종료합니다."
    exit 0
  fi
  rm -f "$PID_FILE"
fi

# ── 시작 ─────────────────────────────────────────────────────────
mkdir -p "$SIGNAL_DIR"
echo $$ > "$PID_FILE"
echo "[crew-daemon] 시작 (PID $$, project: ${PROJECT_NAME}, idle_timeout: ${IDLE_TIMEOUT}s)"

cleanup() {
  echo "[crew-daemon] 종료"
  rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

# ── JSON 헬퍼 ────────────────────────────────────────────────────
json_get() {
  local json="$1" key="$2"
  if command -v jq &>/dev/null; then
    echo "$json" | jq -r ".$key // empty"
  else
    python3 -c "import sys,json; d=json.loads(sys.argv[1]); print(d.get('$key',''))" "$json"
  fi
}

pipeline_update() {
  python3 - "$PIPELINE_FILE" "$PHASE_FILE" "$SIGNAL_DIR" <<'PYEOF'
import sys, json, os

pipeline_file, phase_file, signal_dir = sys.argv[1], sys.argv[2], sys.argv[3]

with open(pipeline_file) as f:
    p = json.load(f)

p['currentIndex'] = p.get('currentIndex', 0) + 1
agents = p.get('agents', [])

if p['currentIndex'] >= len(agents):
    p['status'] = 'DONE'
    with open(phase_file, 'w') as f:
        f.write('DONE')
    print("PIPELINE_DONE")
else:
    next_agent = agents[p['currentIndex']]
    signal_path = os.path.join(signal_dir, f"{next_agent}.ready")
    open(signal_path, 'w').close()
    with open(os.path.join(os.path.dirname(pipeline_file), 'active_agent.txt'), 'w') as f:
        f.write(next_agent)
    print(f"NEXT_AGENT:{next_agent}")

tmp = pipeline_file + '.tmp'
with open(tmp, 'w') as f:
    json.dump(p, f, indent=2, ensure_ascii=False)
os.replace(tmp, pipeline_file)
PYEOF
}

pipeline_abort() {
  python3 - "$PIPELINE_FILE" <<'PYEOF'
import sys, json, os
f = sys.argv[1]
with open(f) as fp:
    p = json.load(fp)
p['status'] = 'FAILED'
tmp = f + '.tmp'
with open(tmp, 'w') as fp:
    json.dump(p, fp, indent=2, ensure_ascii=False)
os.replace(tmp, f)
print("PIPELINE_FAILED")
PYEOF
}

pipeline_is_done() {
  [ -f "$PIPELINE_FILE" ] || return 1
  local status
  status=$(python3 -c "import json; print(json.load(open('$PIPELINE_FILE')).get('status',''))" 2>/dev/null || echo "")
  [[ "$status" == "DONE" || "$status" == "FAILED" ]]
}

# ── 이벤트 처리 ──────────────────────────────────────────────────
process_event() {
  local line="$1"
  local event agent
  event=$(json_get "$line" "event")
  agent=$(json_get "$line" "agent")

  echo "[crew-daemon] 이벤트: event=${event} agent=${agent}"

  local result
  case "$event" in
    PHASE_COMPLETE)
      result=$(pipeline_update)
      echo "[crew-daemon] $result"
      if [[ "$result" == "PIPELINE_DONE" ]]; then
        echo "[crew-daemon] 파이프라인 완료 — 데몬 종료"
        exit 0
      fi
      ;;
    PIPELINE_ABORT)
      result=$(pipeline_abort)
      echo "[crew-daemon] $result — 데몬 종료"
      exit 0
      ;;
    *)
      echo "[crew-daemon] 알 수 없는 이벤트: ${event}"
      ;;
  esac
}

# ── 오프셋 복원 ──────────────────────────────────────────────────
OFFSET=0
[ -f "$OFFSET_FILE" ] && OFFSET=$(cat "$OFFSET_FILE")

LAST_EVENT_TIME=$(date +%s)

# ── 메인 루프 ────────────────────────────────────────────────────
while true; do
  # 파이프라인 완료 여부 주기적 확인 (이벤트 유실 대비 안전망)
  if pipeline_is_done; then
    echo "[crew-daemon] 파이프라인 이미 완료 — 데몬 종료"
    exit 0
  fi

  # 유휴 타임아웃 확인
  NOW=$(date +%s)
  IDLE=$((NOW - LAST_EVENT_TIME))
  if [ "$IDLE" -ge "$IDLE_TIMEOUT" ]; then
    echo "[crew-daemon] ${IDLE_TIMEOUT}s 동안 이벤트 없음 — 유휴 타임아웃으로 종료"
    exit 0
  fi

  # 새 이벤트 처리
  if [ -f "$EVENTS_FILE" ]; then
    TOTAL=$(wc -l < "$EVENTS_FILE" | tr -d ' ')
    if [ "$TOTAL" -gt "$OFFSET" ]; then
      while IFS= read -r line; do
        [ -n "$line" ] && process_event "$line"
        OFFSET=$((OFFSET + 1))
        echo "$OFFSET" > "$OFFSET_FILE"
        LAST_EVENT_TIME=$(date +%s)
      done < <(tail -n "+$((OFFSET + 1))" "$EVENTS_FILE")
    fi
  fi

  sleep 1
done
