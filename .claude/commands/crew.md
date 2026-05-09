# /crew — 멀티 태스크 병렬 실행

여러 독립 작업을 동시에 실행한다.
각 태스크는 별도 git worktree에서 격리되어 실행되며, 완전히 독립된 context로 처리된다.

```
[오케스트레이터] /crew "태스크A" "태스크B" "태스크C"
      │
      ▼ 각 태스크 준비 (worktree + branch + TASK_DIR)
      │
      ▼ 단일 응답에서 모든 task-runner를 동시에 spawn
[task-runner A] ‖ [task-runner B] ‖ [task-runner C]
  planner→stages    planner→stages    planner→stages
  (격리 worktree)   (격리 worktree)   (격리 worktree)
      │
      ▼ 모든 완료 대기
[오케스트레이터] 결과 취합 + 병합 안내
```

## 실행 순서

### 1. 태스크 목록 수집

인자가 있으면 그대로 사용. 없으면 AskUserQuestion:
- 질문: "병렬로 실행할 작업을 입력하세요."
- 형식 안내: 여러 작업은 줄바꿈이나 번호로 구분

### 2. 상태 경로 초기화

```bash
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}"
BASE_TIME=$(date +%Y%m%d-%H%M%S)
```

`{STATE_DIR}` 없으면: "/setup을 먼저 실행하세요." 출력 후 종료.

### 3. 각 태스크별 준비

태스크 인덱스 `i` (0부터 시작)마다:

```bash
TASK_ID="${BASE_TIME}-${i}"
TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
BRANCH="feature/task-${TASK_ID}"
WORKTREE_PATH="${PROJECT_ROOT}/.crew-worktrees/${TASK_ID}"

mkdir -p "${TASK_DIR}/context"
git worktree add "${WORKTREE_PATH}" -b "${BRANCH}"

echo "${WORKTREE_PATH}" > "${TASK_DIR}/worktree_path.txt"
echo "${BRANCH}"        > "${TASK_DIR}/branch.txt"
echo "${TASK_DESC}"     > "${TASK_DIR}/task.txt"
```

### 4. 사용자 확인

AskUserQuestion:
- 질문: "{N}개 작업을 병렬로 실행합니다:\n\n{번호별 태스크 목록}\n\n각 작업은 독립 브랜치에서 격리 실행됩니다."
- 선택지:
  - "시작 (Recommended)"
  - "취소"

취소 시: 생성된 worktree와 TASK_DIR 전부 정리 후 종료:
```bash
for WORKTREE_PATH in {생성된 경로들}; do
  git worktree remove "${WORKTREE_PATH}" --force 2>/dev/null || true
done
```

### 5. 병렬 실행

**단일 응답에서 모든 task-runner Agent를 동시에 호출**:

태스크마다 Agent 도구 하나씩, 전부 같은 메시지에:
```
subagent_type: "task-runner"
prompt:
  TASK: {태스크 설명}
  TASK_ID: {TASK_ID}
  TASK_DIR: {TASK_DIR}
  WORKTREE_PATH: {WORKTREE_PATH}
  BRANCH: {BRANCH}

  위 작업을 자율적으로 완료하라.
```

모든 task-runner 완료까지 대기.

### 6. 결과 취합 및 보고

각 태스크마다:
```bash
TASK_DESC=$(cat "${TASK_DIR}/task.txt")
BRANCH=$(cat "${TASK_DIR}/branch.txt")
RESULT=$(cat "${TASK_DIR}/result.md" 2>/dev/null || echo "결과 없음")
```

출력 형식:
```
✅ 멀티 태스크 완료! ({N}개 작업)

┌─ 태스크 1: {설명}
│  브랜치: feature/task-{ID1}
│  커밋: {git log 요약}
│
├─ 태스크 2: {설명}
│  브랜치: feature/task-{ID2}
│  커밋: {git log 요약}
│
└─ 태스크 N: {설명}
   브랜치: feature/task-{IDN}
   커밋: {git log 요약}

다음 단계 (순서대로 병합):
  git merge feature/task-{ID1}
  git merge feature/task-{ID2}
  ...
  # 충돌 발생 시: /task "resolve merge conflicts"
```

## 주의사항

- 태스크 간 의존성이 있는 경우 `/crew` 대신 `/task`을 사용하라.
  예) "A를 구현하고, A를 사용하는 B를 구현" → `/task` (순차 필요)
- 완전히 독립적인 기능들을 병렬 처리하는 데 최적화되어 있다.
  예) "로그인 API", "상품 목록 API", "주문 API" → `/crew` (독립적)
