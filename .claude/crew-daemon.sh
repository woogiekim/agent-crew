#!/usr/bin/env bash
# crew-daemon — multi-task pipeline orchestrator
# Usage:
#   crew-daemon.sh          — start (default)
#   crew-daemon.sh start    — start
#   crew-daemon.sh stop     — stop running instance
#   crew-daemon.sh status   — check if RUNNING / STOPPED
set -euo pipefail

PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}"
AGENT_CREW_DIR="${HOME}/.claude/agent-crew"
TASKS_DIR="${STATE_DIR}/tasks"
PID_FILE="${STATE_DIR}/orchestrator.pid"

IDLE_TIMEOUT=1800   # 프로젝트 전체 유휴 종료 (초)
ZOMBIE_TIMEOUT=600  # task당 이벤트 없으면 zombie 판정 (초)
MAX_RETRIES=5

# ── stop / status ────────────────────────────────────────────────
CMD="${1:-start}"

case "$CMD" in
  stop)
    # PID 파일의 프로세스 + pgrep으로 동명 프로세스 모두 종료 (다중 기동 방어)
    STOPPED=0
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && STOPPED=$((STOPPED + 1))
        echo "[crew-daemon] 종료 요청 (PID $PID)"
      fi
      rm -f "$PID_FILE"
    fi
    # 동일 스크립트로 기동된 좀비 프로세스 추가 정리
    EXTRA=$(pgrep -f "crew-daemon.sh start" 2>/dev/null | grep -v "^$$" || true)
    for ZPID in $EXTRA; do
      kill "$ZPID" 2>/dev/null && STOPPED=$((STOPPED + 1)) && echo "[crew-daemon] 추가 프로세스 종료 (PID $ZPID)"
    done
    # grace period 후 SIGKILL
    sleep 2
    STILL=$(pgrep -f "crew-daemon.sh start" 2>/dev/null | grep -v "^$$" || true)
    for ZPID in $STILL; do
      kill -9 "$ZPID" 2>/dev/null && echo "[crew-daemon] 강제 종료 (PID $ZPID)"
    done
    [ "$STOPPED" -eq 0 ] && echo "[crew-daemon] 실행 중인 데몬 없음"
    exit 0
    ;;
  status)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      if kill -0 "$PID" 2>/dev/null; then
        echo "RUNNING (PID $PID, project: ${PROJECT_NAME})"
      else
        echo "STOPPED (stale PID)"
        rm -f "$PID_FILE"
      fi
    else
      echo "STOPPED"
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
mkdir -p "$TASKS_DIR"
echo $$ > "$PID_FILE"
echo "[crew-daemon] 시작 (PID $$, project: ${PROJECT_NAME})"

cleanup() {
  echo "[crew-daemon] 종료"
  rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

# ── 헬퍼 ─────────────────────────────────────────────────────────

task_status() {
  local pipeline="$1/pipeline.json"
  [ -f "$pipeline" ] || { echo "PENDING"; return; }
  python3 -c "import json; print(json.load(open('$pipeline')).get('status','PENDING'))" 2>/dev/null || echo "PENDING"
}

task_pipeline_start() {
  local task_dir="$1"
  python3 "${AGENT_CREW_DIR}/lib/pipeline_update.py" start \
    "${task_dir}/pipeline.json" \
    "${task_dir}/phase.txt" \
    "${task_dir}/agent_signal" || echo "START_ERROR"
}

task_pipeline_advance() {
  local task_dir="$1"
  python3 "${AGENT_CREW_DIR}/lib/pipeline_update.py" advance \
    "${task_dir}/pipeline.json" \
    "${task_dir}/phase.txt" \
    "${task_dir}/agent_signal" || echo "ADVANCE_ERROR"
}

task_pipeline_abort() {
  local task_dir="$1" reason="$2"
  python3 "${AGENT_CREW_DIR}/lib/pipeline_update.py" abort "${task_dir}/pipeline.json" || true
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ABORT: $reason" >> "${task_dir}/error.log"
}

merge_task_branch() {
  local task_dir="$1"
  local branch worktree_path
  branch=$(cat "${task_dir}/branch.txt" 2>/dev/null || echo "")
  worktree_path=$(cat "${task_dir}/worktree_path.txt" 2>/dev/null || echo "")

  [ -z "$branch" ] && { echo "NO_BRANCH"; return; }

  # feature/main 으로 merge 시도
  git -C "$PROJECT_ROOT" checkout feature/main 2>/dev/null || true
  if git -C "$PROJECT_ROOT" merge --no-ff "$branch" -m "merge: $branch into feature/main" 2>/dev/null; then
    # 성공: worktree 및 브랜치 정리
    if [ -n "$worktree_path" ]; then
      git -C "$PROJECT_ROOT" worktree remove --force "$worktree_path" 2>/dev/null || true
    fi
    git -C "$PROJECT_ROOT" branch -D "$branch" 2>/dev/null || true
    echo "MERGE_OK"
  else
    git -C "$PROJECT_ROOT" merge --abort 2>/dev/null || true
    # resolver 에이전트 활성화
    mkdir -p "${task_dir}/agent_signal"
    touch "${task_dir}/agent_signal/resolver.ready"
    echo "resolver" > "${task_dir}/active_agent.txt"
    echo "MERGE_CONFLICT"
  fi
}

cleanup_task_dir() {
  local task_id="$1"
  rm -rf "${TASKS_DIR}/${task_id}"
}

# per-task 마지막 이벤트 시간 — 파일 기반 (bash 3.x 호환)
get_last_event_time() {
  local ts_file="${1}/zombie_last_event.txt"
  local val
  if [ -f "$ts_file" ]; then
    val=$(tr -d '[:space:]' < "$ts_file")
    [[ "$val" =~ ^[0-9]+$ ]] && echo "$val" || date +%s
  else
    date +%s
  fi
}

set_last_event_time() {
  date +%s > "${1}/zombie_last_event.txt"
}

process_event() {
  local task_dir="$1" line="$2"
  local event agent task_id
  event=$(python3 -c "import sys,json; print(json.loads(sys.argv[1]).get('event',''))" "$line" 2>/dev/null || echo "")
  agent=$(python3 -c "import sys,json; print(json.loads(sys.argv[1]).get('agent',''))" "$line" 2>/dev/null || echo "")
  task_id=$(basename "$task_dir")

  echo "[crew-daemon] task=${task_id} event=${event} agent=${agent}"

  case "$event" in
    PIPELINE_START)
      local start_result
      start_result=$(task_pipeline_start "$task_dir")
      echo "[crew-daemon] task=${task_id} $start_result"
      if [[ "$start_result" == "START_ERROR" ]]; then
        task_pipeline_abort "$task_dir" "pipeline start failed"
        echo "[crew-daemon] task=${task_id} ABORTED (start error)"
      fi
      ;;
    PHASE_COMPLETE)
      local result
      result=$(task_pipeline_advance "$task_dir")
      echo "[crew-daemon] task=${task_id} $result"
      if [[ "$result" == "PIPELINE_DONE" ]]; then
        local merge_result
        merge_result=$(merge_task_branch "$task_dir")
        echo "[crew-daemon] task=${task_id} merge=${merge_result}"
        if [[ "$merge_result" == "MERGE_OK" ]]; then
          cleanup_task_dir "$task_id"
        fi
        # MERGE_CONFLICT: resolver 활성화 — task dir 유지
      elif [[ "$result" == "ADVANCE_ERROR" ]]; then
        task_pipeline_abort "$task_dir" "pipeline advance failed"
        echo "[crew-daemon] task=${task_id} ABORTED (advance error)"
      fi
      ;;
    PIPELINE_ABORT)
      task_pipeline_abort "$task_dir" "에이전트 요청"
      echo "[crew-daemon] task=${task_id} ABORTED"
      ;;
    *)
      echo "[crew-daemon] task=${task_id} 알 수 없는 이벤트: ${event}"
      ;;
  esac
}

# ── 메인 루프 ────────────────────────────────────────────────────

LAST_ACTIVE_TIME=$(date +%s)

while true; do
  ACTIVE_TASKS=0

  for task_dir in "${TASKS_DIR}"/*/; do
    [ -d "$task_dir" ] || continue
    task_id=$(basename "$task_dir")
    status=$(task_status "$task_dir")

    [[ "$status" == "DONE" || "$status" == "FAILED" ]] && continue

    ACTIVE_TASKS=$((ACTIVE_TASKS + 1))
    LAST_ACTIVE_TIME=$(date +%s)

    # zombie_last_event.txt 초기화 (처음 보는 task)
    [ -f "${task_dir}/zombie_last_event.txt" ] || set_last_event_time "$task_dir"

    events_file="${task_dir}/events.jsonl"
    offset_file="${task_dir}/events.offset"
    OFFSET=0
    [ -f "$offset_file" ] && OFFSET=$(cat "$offset_file")

    # 새 이벤트 처리
    if [ -f "$events_file" ]; then
      TOTAL=$(wc -l < "$events_file" | tr -d ' ')
      if [ "$TOTAL" -gt "$OFFSET" ]; then
        while IFS= read -r line; do
          [ -n "$line" ] && process_event "$task_dir" "$line"
          OFFSET=$((OFFSET + 1))
          echo "$OFFSET" > "$offset_file"
          set_last_event_time "$task_dir"
        done < <(tail -n "+$((OFFSET + 1))" "$events_file")
      fi
    fi

    # zombie 감지
    NOW=$(date +%s)
    LAST_EVENT=$(get_last_event_time "$task_dir")
    TASK_IDLE=$(( NOW - LAST_EVENT ))
    if [ "$TASK_IDLE" -ge "$ZOMBIE_TIMEOUT" ]; then
      RETRY=$(cat "${task_dir}/retry_count.txt" 2>/dev/null || echo "0")
      if [ "$RETRY" -ge "$MAX_RETRIES" ]; then
        echo "[crew-daemon] task=${task_id} zombie — 재시도 ${MAX_RETRIES}회 초과, FAILED"
        task_pipeline_abort "$task_dir" "zombie timeout (retry exhausted)"
        branch=$(cat "${task_dir}/branch.txt" 2>/dev/null || echo "")
        worktree_path=$(cat "${task_dir}/worktree_path.txt" 2>/dev/null || echo "")
        if [ -n "$worktree_path" ]; then
          git -C "$PROJECT_ROOT" worktree remove --force "$worktree_path" 2>/dev/null || true
        fi
        [ -n "$branch" ] && git -C "$PROJECT_ROOT" branch -D "$branch" 2>/dev/null || true
      else
        NEW_RETRY=$((RETRY + 1))
        echo "$NEW_RETRY" > "${task_dir}/retry_count.txt"
        set_last_event_time "$task_dir"
        echo "[crew-daemon] task=${task_id} zombie 감지 — 재시작 시도 ${NEW_RETRY}/${MAX_RETRIES}"
        active_agent=$(cat "${task_dir}/active_agent.txt" 2>/dev/null || echo "")
        if [ -n "$active_agent" ]; then
          mkdir -p "${task_dir}/agent_signal"
          touch "${task_dir}/agent_signal/${active_agent}.ready"
          echo "[crew-daemon] task=${task_id} signal: ${active_agent}.ready 재생성"
        fi
      fi
    fi
  done

  # 프로젝트 전체 유휴 타임아웃
  NOW=$(date +%s)
  IDLE=$(( NOW - LAST_ACTIVE_TIME ))
  if [ "$ACTIVE_TASKS" -eq 0 ] && [ "$IDLE" -ge "$IDLE_TIMEOUT" ]; then
    echo "[crew-daemon] ${IDLE_TIMEOUT}s 동안 활성 task 없음 — 유휴 종료"
    exit 0
  fi

  sleep 2
done
