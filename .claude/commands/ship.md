# /ship — 전체 파이프라인 자동 실행

## 상태 경로 규칙
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
PROJECT_ROOT = $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR    = ~/.claude/agent-crew/{PROJECT_NAME}
TASK_ID      = $(date +%Y%m%d-%H%M%S)
TASK_DIR     = {STATE_DIR}/tasks/{TASK_ID}
```

## 핵심 원칙

**Claude Code(에이전트)는 pipeline.json / phase.txt / active_agent.txt를 직접 수정하지 않는다.**
모든 파이프라인 상태 전환은 `events.jsonl` 이벤트 emit → crew-daemon 처리를 통해서만 이루어진다.

```
[Claude Code] 작업 완료
      │
      ▼ emit {"event": "PHASE_COMPLETE", "agent": "..."}
[events.jsonl]
      │
      ▼ crew-daemon reads
[pipeline_update.py advance]
      │
      ▼ updates pipeline.json + phase.txt + active_agent.txt
      ▼ creates agent_signal/{next_agent}.ready
[Claude Code] {next_agent}.ready 감지 → 다음 에이전트로 전환
```

## 실행 순서

1. `/ship "[요청]"` 형태로 입력 받음
   - 인자 없으면: AskUserQuestion 도구로 작업 내용 입력 받기

2. `{STATE_DIR}` 존재 확인
   - 없으면: "워크스페이스가 초기화되지 않았습니다. /setup을 먼저 실행하세요."

3. 동시 실행 제한 확인
   ```bash
   CONFIG="${STATE_DIR}/config.json"
   MAX=$(python3 -c "import json; print(json.load(open('$CONFIG')).get('maxConcurrentTasks',2))" 2>/dev/null || echo 2)
   ACTIVE=$(python3 -c "
   import json, glob
   count = 0
   for f in glob.glob('${STATE_DIR}/tasks/*/pipeline.json'):
       try:
           p = json.load(open(f))
           if p.get('status') == 'IN_PROGRESS': count += 1
       except: pass
   print(count)
   ")
   echo "active=$ACTIVE max=$MAX"
   ```
   - `ACTIVE >= MAX`이면: AskUserQuestion 도구로 안내

4. TASK_ID 생성 및 브랜치/워크트리 생성
   ```bash
   TASK_ID=$(date +%Y%m%d-%H%M%S)
   BRANCH="feature/task-${TASK_ID}"
   WORKTREE_PATH="${PROJECT_ROOT}/../$(basename ${PROJECT_ROOT})-task-${TASK_ID}"

   git show-ref --verify --quiet refs/heads/feature/main \
     || git checkout -b feature/main

   git checkout -b "$BRANCH" feature/main
   git checkout -
   git worktree add "$WORKTREE_PATH" "$BRANCH"

   TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
   mkdir -p "${TASK_DIR}/context" "${TASK_DIR}/agent_signal"
   echo "$WORKTREE_PATH" > "${TASK_DIR}/worktree_path.txt"
   echo "$BRANCH"        > "${TASK_DIR}/branch.txt"
   echo "0"              > "${TASK_DIR}/iterations.txt"
   echo "0"              > "${TASK_DIR}/retry_count.txt"
   echo "$TASK_ID"       > "${WORKTREE_PATH}/.crew_task_id"
   echo "task_id=$TASK_ID worktree=$WORKTREE_PATH"
   ```

5. crew-daemon 상태 확인 및 시작
   ```bash
   bash ~/.claude/agent-crew/crew-daemon.sh status | grep -q RUNNING \
     || nohup bash ~/.claude/agent-crew/crew-daemon.sh start \
          >> "${STATE_DIR}/daemon.log" 2>&1 &
   sleep 1  # 데몬 초기화 대기
   ```

6. planner로 요청 분석 → 에이전트 목록 결정
   - `~/.claude/agent-crew/agents/planner/AGENT.md` 읽기
   - 요청 유형에 따라 파이프라인 결정 (planner AGENT.md의 기준 참조)

7. 사용자 확인 (AskUserQuestion 도구 사용)
   - 질문: "다음 순서로 진행합니다: [에이전트 목록]. 시작할까요?\n브랜치: {BRANCH}"
   - 선택지: "시작 (Recommended)" / "취소"
   - "취소" 선택 시:
     ```bash
     git worktree remove --force "$WORKTREE_PATH"
     git branch -D "$BRANCH"
     rm -rf "$TASK_DIR"
     ```

8. 초기 `pipeline.json` 저장 (status=PENDING) 후 PIPELINE_START emit
   ```bash
   # pipeline.json 저장 — status는 PENDING (daemon이 IN_PROGRESS로 전환)
   cat > "${TASK_DIR}/pipeline.json" <<EOF
   {
     "task": "[요청 원문]",
     "agents": ["planner", ...],
     "currentIndex": 0,
     "status": "PENDING"
   }
   EOF

   # 데몬에게 파이프라인 시작 신호
   echo '{"event":"PIPELINE_START"}' >> "${TASK_DIR}/events.jsonl"
   ```

9. planner.ready 감지 대기 (daemon이 생성)
   ```bash
   SIGNAL="${TASK_DIR}/agent_signal/planner.ready"
   for i in $(seq 1 15); do
     [ -f "$SIGNAL" ] && break
     sleep 2
   done
   [ -f "$SIGNAL" ] || { echo "ERROR: planner.ready 신호 없음"; exit 1; }
   rm -f "$SIGNAL"
   ```

10. planner 에이전트 작업 수행 (requirements)
    - `{WORKTREE_PATH}` 기준으로 작업
    - 완료 시 **오직** 아래만 수행:
      ```bash
      echo '{"event":"PHASE_COMPLETE","agent":"planner"}' >> "${TASK_DIR}/events.jsonl"
      ```
    - pipeline.json / phase.txt / active_agent.txt **직접 수정 금지**

11. 다음 에이전트 감지 루프 (각 에이전트 완료 후 반복)
    ```bash
    # daemon이 다음 에이전트의 .ready 신호를 생성할 때까지 대기
    NEXT_AGENT=""
    for i in $(seq 1 15); do
      for sig in "${TASK_DIR}/agent_signal/"*.ready; do
        [ -f "$sig" ] && NEXT_AGENT=$(basename "$sig" .ready) && break 2
      done
      sleep 2
    done

    if [ -n "$NEXT_AGENT" ]; then
      rm -f "${TASK_DIR}/agent_signal/${NEXT_AGENT}.ready"
      # NEXT_AGENT의 AGENT.md 읽고 에이전트 전환
    fi
    ```

12. 모든 에이전트 완료 → daemon이 자동으로 merge 처리
    - 충돌 없음: worktree 정리 후 task 디렉토리 삭제
    - 충돌 있음: resolver.ready 생성 → resolver 에이전트 활성화

## 에이전트별 담당 단계 및 완료 이벤트

| 에이전트 | 담당 단계 | 완료 emit |
|---------|---------|---------|
| planner | requirements | `PHASE_COMPLETE` |
| designer | design | `PHASE_COMPLETE` |
| frontend | implement → verify | `PHASE_COMPLETE` |
| backend | design → implement → verify | `PHASE_COMPLETE` |
| resolver | merge-resolve | `PHASE_COMPLETE` |

**모든 에이전트 공통 규칙:**
- 단계 완료 시 `events.jsonl`에 `PHASE_COMPLETE` emit만 수행
- `phase.txt`, `active_agent.txt`, `pipeline.json` 직접 수정 금지
- 다음 에이전트 활성화는 daemon이 자동 처리

## STATE_DIR 규칙 (에이전트 공통)
```bash
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
TASK_ID=$(cat "${PROJECT_ROOT}/.crew_task_id" 2>/dev/null || echo "")
if [ -n "$TASK_ID" ]; then
  STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}/tasks/${TASK_ID}"
else
  STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}"
fi
```
