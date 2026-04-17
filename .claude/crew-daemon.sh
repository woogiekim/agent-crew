#!/usr/bin/env bash
# crew-daemon — agent-crew 파이프라인 오케스트레이터 데몬
# events.jsonl을 감시하고 pipeline.json 상태를 원자적으로 갱신한다.
# 에이전트가 직접 상태를 수정하는 레이스 컨디션을 방지한다.
set -euo pipefail

PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}"
EVENTS_FILE="${STATE_DIR}/events.jsonl"
OFFSET_FILE="${STATE_DIR}/events.offset"
PID_FILE="${STATE_DIR}/orchestrator.pid"
SIGNAL_DIR="${STATE_DIR}/agent_signal"
PIPELINE_FILE="${STATE_DIR}/pipeline.json"
PHASE_FILE="${STATE_DIR}/phase.txt"

# ── 시작 ─────────────────────────────────────────────────────────
mkdir -p "$SIGNAL_DIR"
echo $$ > "$PID_FILE"
echo "[crew-daemon] 시작 (PID $$, project: ${PROJECT_NAME})"

cleanup() {
  echo "[crew-daemon] 종료"
  rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

# ── JSON 헬퍼 (jq 우선, python3 fallback) ────────────────────────
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
    print(f"[crew-daemon] 파이프라인 완료 (DONE)")
else:
    next_agent = agents[p['currentIndex']]
    signal_path = os.path.join(signal_dir, f"{next_agent}.ready")
    open(signal_path, 'w').close()
    print(f"[crew-daemon] 다음 에이전트 신호 발행: {next_agent}")

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
print("[crew-daemon] 파이프라인 중단 (FAILED)")
PYEOF
}

# ── 이벤트 처리 ──────────────────────────────────────────────────
process_event() {
  local line="$1"
  local event agent
  event=$(json_get "$line" "event")
  agent=$(json_get "$line" "agent")

  echo "[crew-daemon] 이벤트 수신: event=${event} agent=${agent}"

  case "$event" in
    PHASE_COMPLETE) pipeline_update ;;
    PIPELINE_ABORT) pipeline_abort ;;
    *) echo "[crew-daemon] 알 수 없는 이벤트: ${event}" ;;
  esac
}

# ── 오프셋 복원 ──────────────────────────────────────────────────
OFFSET=0
[ -f "$OFFSET_FILE" ] && OFFSET=$(cat "$OFFSET_FILE")

# ── 메인 루프 ────────────────────────────────────────────────────
while true; do
  if [ -f "$EVENTS_FILE" ]; then
    TOTAL=$(wc -l < "$EVENTS_FILE" | tr -d ' ')
    if [ "$TOTAL" -gt "$OFFSET" ]; then
      while IFS= read -r line; do
        [ -n "$line" ] && process_event "$line"
        OFFSET=$((OFFSET + 1))
        echo "$OFFSET" > "$OFFSET_FILE"
      done < <(tail -n "+$((OFFSET + 1))" "$EVENTS_FILE")
    fi
  fi
  sleep 1
done
