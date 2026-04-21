# /ship — 전체 파이프라인 자동 실행

## 상태 경로 규칙
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
PROJECT_ROOT = $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR    = ~/.claude/agent-crew/{PROJECT_NAME}
TASK_ID      = $(date +%Y%m%d-%H%M%S)
TASK_DIR     = {STATE_DIR}/tasks/{TASK_ID}
```

## 실행 순서

1. `/ship "[요청]"` 형태로 입력 받음
   - 인자 없으면: AskUserQuestion 도구로 작업 내용 입력 받기

2. `{STATE_DIR}` 존재 확인
   - 없으면: "워크스페이스가 초기화되지 않았습니다. /setup을 먼저 실행하세요."

3. 동시 실행 제한 확인 (Bash 도구로 실행)
   ```bash
   CONFIG="${STATE_DIR}/config.json"
   MAX=$(python3 -c "import json,os; print(json.load(open('$CONFIG')).get('maxConcurrentTasks',2))" 2>/dev/null || echo 2)
   ACTIVE=$(python3 -c "
   import json, glob, os
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
     - 질문: "현재 {ACTIVE}개 task가 실행 중입니다 (최대 {MAX}개). 어떻게 할까요?"
     - 선택지: "대기 (나중에 실행)" / "강제 시작 (제한 무시)"
     - "대기" 선택 시 종료

4. TASK_ID 생성 및 브랜치/워크트리 생성 (Bash 도구로 실행)
   ```bash
   TASK_ID=$(date +%Y%m%d-%H%M%S)
   BRANCH="feature/task-${TASK_ID}"
   WORKTREE_PATH="${PROJECT_ROOT}/../$(basename ${PROJECT_ROOT})-task-${TASK_ID}"

   # feature/main 없으면 생성
   git show-ref --verify --quiet refs/heads/feature/main \
     || git checkout -b feature/main

   # task 브랜치 생성 및 워크트리 추가
   git checkout -b "$BRANCH" feature/main
   git checkout -  # 원래 브랜치로 복귀
   git worktree add "$WORKTREE_PATH" "$BRANCH"

   # task 상태 디렉토리 초기화
   TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
   mkdir -p "${TASK_DIR}/context" "${TASK_DIR}/agent_signal"
   echo "$WORKTREE_PATH" > "${TASK_DIR}/worktree_path.txt"
   echo "$BRANCH"        > "${TASK_DIR}/branch.txt"
   echo "REQUIREMENTS"   > "${TASK_DIR}/phase.txt"
   echo "planner"        > "${TASK_DIR}/active_agent.txt"
   echo "0"              > "${TASK_DIR}/iterations.txt"
   echo "0"              > "${TASK_DIR}/retry_count.txt"
   # .crew_task_id 를 워크트리 루트에 기록 (에이전트가 TASK_ID 식별용)
   echo "$TASK_ID"       > "${WORKTREE_PATH}/.crew_task_id"
   echo '{"task":"","agents":[],"currentIndex":0,"status":"PENDING"}' > "${TASK_DIR}/pipeline.json"
   echo "task_id=$TASK_ID worktree=$WORKTREE_PATH"
   ```

5. crew-daemon 상태 확인 및 시작 (반드시 Bash 도구로 실행)
   ```bash
   bash ~/.claude/agent-crew/crew-daemon.sh status | grep -q RUNNING \
     || nohup bash ~/.claude/agent-crew/crew-daemon.sh start \
          >> "${STATE_DIR}/daemon.log" 2>&1 &
   ```

6. planner 에이전트 활성화
   - `{TASK_DIR}/active_agent.txt` → `planner`
   - `~/.claude/agent-crew/agents/planner/AGENT.md` 읽기
   - **중요**: 이후 모든 작업은 `{WORKTREE_PATH}` 디렉토리에서 수행

7. planner가 요청 분석 → 필요 에이전트 목록 결정
   - 판단 기준: `~/.claude/agent-crew/agents/planner/AGENT.md` 참조

8. 사용자 확인 (AskUserQuestion 도구 사용)
   - 질문: "다음 순서로 진행합니다: [에이전트 목록]. 시작할까요?\n브랜치: {BRANCH}"
   - 선택지: "시작 (Recommended)" / "취소"
   - "취소" 선택 시: worktree 및 브랜치 정리 후 종료
     ```bash
     git worktree remove --force "$WORKTREE_PATH"
     git branch -D "$BRANCH"
     rm -rf "$TASK_DIR"
     ```

9. `{TASK_DIR}/pipeline.json` 저장
   ```json
   {
     "task": "[요청 원문]",
     "agents": ["planner", ...],
     "currentIndex": 0,
     "status": "IN_PROGRESS"
   }
   ```

10. 파이프라인 순차 실행 (워크트리에서)
    - 모든 코드 변경은 `{WORKTREE_PATH}` 기준으로 수행
    - 각 단계 완료 후 에이전트가 `{TASK_DIR}/events.jsonl`에 emit → 데몬이 갱신

11. task 완료 시 (데몬이 PIPELINE_DONE 처리)
    - `git merge {BRANCH} → feature/main` 자동 시도
    - 충돌 없음: worktree 정리 (`git worktree remove`, `git branch -D`)
    - 충돌 있음: resolver 에이전트 활성화

## 에이전트별 담당 단계

| 에이전트 | 실행 단계 |
|---------|---------|
| planner | requirements |
| designer | design |
| frontend | implement → verify |
| backend | design → implement → verify |
| resolver | merge-resolve |

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
