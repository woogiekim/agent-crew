# /ship — 전체 파이프라인 자동 실행

## 핵심 원칙

**오케스트레이터(Claude)가 Agent 도구로 각 에이전트를 직접 spawn한다.**
파일 폴링, daemon 프로세스, .ready 신호 파일 불필요.

```
[오케스트레이터] /ship "요청"
      │
      ▼ Agent 도구로 spawn
[planner 서브에이전트] → prd.md + pipeline.json + handoff.md 작성
      │
      ▼ pipeline.json 읽어 다음 에이전트 결정
[오케스트레이터] 사용자 확인 후
      │
      ▼ Agent 도구로 spawn (순서대로)
[backend / frontend / designer 서브에이전트] → 코드 작성 + commit
      │
      ▼ 모든 에이전트 완료
[오케스트레이터] 완료 보고
```

## 실행 순서

### 1. 요청 파싱
인자 없으면 AskUserQuestion 도구로 입력받기:
- 질문: "어떤 작업을 진행할까요?"

### 2. 상태 경로 초기화
```bash
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}"
TASK_ID=$(date +%Y%m%d-%H%M%S)
TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
mkdir -p "${TASK_DIR}/context"
echo "task_dir=${TASK_DIR}"
```

`{STATE_DIR}` 없으면: "워크스페이스가 초기화되지 않았습니다. /setup을 먼저 실행하세요." 출력 후 종료.

### 3. 피처 브랜치 생성
```bash
BRANCH="feature/task-${TASK_ID}"
git checkout -b "${BRANCH}"
echo "branch=${BRANCH}"
```

### 4. planner 에이전트 spawn
**Agent 도구**를 사용해 planner 에이전트를 spawn한다:
- description: "PRD 작성 및 파이프라인 결정"
- subagent_type: "planner"
- prompt: 아래 형식
  ```
  REQUEST: {사용자 요청 원문}
  TASK_DIR: {TASK_DIR}
  PROJECT_ROOT: {PROJECT_ROOT}

  위 요청을 분석하여 PRD를 작성하고 파이프라인을 결정하라.
  결과물: {TASK_DIR}/context/prd.md, {TASK_DIR}/pipeline.json, {TASK_DIR}/handoff.md
  ```
- **완료될 때까지 대기** (blocking)

planner 완료 후:
```bash
cat "${TASK_DIR}/pipeline.json"
cat "${TASK_DIR}/handoff.md"
```

### 5. 파이프라인 파싱 및 사용자 확인
`{TASK_DIR}/pipeline.json`에서 `agents` 배열 읽기.

AskUserQuestion 도구로 확인:
- 질문: "다음 순서로 진행합니다:\n{에이전트 목록}\n\n브랜치: {BRANCH}"
- 선택지:
  - "시작 (Recommended)"
  - "취소"

"취소" 선택 시:
```bash
git checkout -
git branch -D "${BRANCH}"
rm -rf "${TASK_DIR}"
```
종료.

`agents` 배열이 비어있으면 (설계/분석만): 결과 요약 후 종료.

### 6. 파이프라인 실행

`agents` 배열을 순서대로 실행. 각 에이전트마다:

1. `{TASK_DIR}/handoff.md` 읽기
2. **Agent 도구**로 해당 에이전트 spawn:
   - description: "{에이전트명} 실행"
   - subagent_type: "{에이전트명}"  ← planner / designer / frontend / backend / resolver
   - prompt: 아래 형식
     ```
     TASK_DIR: {TASK_DIR}
     PROJECT_ROOT: {PROJECT_ROOT}

     --- 이전 에이전트 인계 내용 ---
     {handoff.md 전체 내용}
     ---

     위 인계 내용을 바탕으로 담당 작업을 수행하라.
     ```
   - **완료될 때까지 대기** (blocking)

3. 완료 후 다음 에이전트를 위해 `{TASK_DIR}/handoff.md` 다시 읽기

### 7. 완료 보고
모든 에이전트 완료 후:
```bash
git log --oneline feature/main..HEAD 2>/dev/null || git log --oneline -5
```

출력 형식:
```
✅ 파이프라인 완료!
   브랜치: {BRANCH}
   실행된 에이전트: {에이전트 목록}
   커밋 목록: {git log 결과}

다음 단계:
  git merge {BRANCH}    # main에 병합
  /ship "다음 작업"     # 새 작업 시작
```

## 에이전트별 산출물 요약

| 에이전트 | 필수 산출물 |
|---------|---------|
| planner | prd.md, pipeline.json, handoff.md |
| designer | design-spec.md, handoff.md 갱신 |
| frontend | UI 소스코드, git commit, handoff.md 갱신 |
| backend | 도메인 코드 + 테스트, git commit |
| resolver | 충돌 해결, git commit |
