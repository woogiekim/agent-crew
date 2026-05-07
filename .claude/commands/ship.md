# /ship — 전체 파이프라인 자동 실행

## 핵심 원칙

오케스트레이터(Claude)가 Agent 도구로 각 에이전트를 직접 spawn한다.
파일 폴링, daemon 프로세스, .ready 신호 파일 불필요.

같은 stage의 에이전트는 **단일 응답에서 여러 Agent 도구를 동시에 호출**해 병렬 실행한다.

```
[오케스트레이터] /ship "요청"
      │
      ▼ planner spawn
[planner] → prd.md + pipeline.json (stages) + handoff.md
      │
      ▼ stage 0: 병렬 spawn (단일 응답에서 두 Agent 동시 호출)
[designer] ‖ [backend] → 각자 결과 파일 작성
      │
      ▼ 오케스트레이터가 handoff.md 갱신 (결과 파일 경로 기록)
      │
      ▼ stage 1: spawn
[frontend] → UI 구현
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
```

`{STATE_DIR}` 없으면: "워크스페이스가 초기화되지 않았습니다. /setup을 먼저 실행하세요." 출력 후 종료.

### 3. 재개 확인
```bash
# 완료되지 않은 최근 태스크 찾기
RESUME_PIPELINE=$(find "${STATE_DIR}/tasks" -name "pipeline.json" 2>/dev/null \
  | xargs grep -l '"completed_stages"' 2>/dev/null \
  | while read f; do
      DONE=$(python3 -c "import json; d=json.load(open('$f')); print(len(d.get('stages',[])) > d.get('completed_stages',0))" 2>/dev/null)
      [ "$DONE" = "True" ] && echo "$f"
    done | sort | tail -1)
```

`RESUME_PIPELINE`이 존재하면 AskUserQuestion:
- 질문: "완료되지 않은 태스크가 있습니다. 어떻게 할까요?"
- 선택지:
  - "이어서 진행 (Recommended)" — 마지막 완료 stage부터 재개
  - "새 태스크 시작" — 새 TASK_ID로 시작

"이어서 진행" 선택 시:
```bash
TASK_DIR=$(dirname "$RESUME_PIPELINE")
TASK_ID=$(basename "$TASK_DIR")
BRANCH="feature/task-${TASK_ID}"
git checkout "${BRANCH}" 2>/dev/null || true
# pipeline.json 읽어 completed_stages 파악 후 해당 stage부터 실행 (5단계 스킵 → 6단계로)
```

"새 태스크 시작" 선택 시:
```bash
TASK_ID=$(date +%Y%m%d-%H%M%S)
TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
mkdir -p "${TASK_DIR}/context"
```

### 4. 피처 브랜치 생성 (새 태스크만)
```bash
BRANCH="feature/task-${TASK_ID}"
git checkout -b "${BRANCH}"
```

### 5. planner spawn (새 태스크만)
Agent 도구로 planner spawn (blocking):
```
REQUEST: {사용자 요청 원문}
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {PROJECT_ROOT}

위 요청을 분석하여 PRD를 작성하고 파이프라인을 결정하라.
결과물: {TASK_DIR}/context/prd.md, {TASK_DIR}/pipeline.json, {TASK_DIR}/handoff.md
```

완료 후:
```bash
cat "${TASK_DIR}/pipeline.json"
```

### 6. 파이프라인 확인 및 사용자 승인
`pipeline.json`에서 `stages` 배열 읽기.

stages 표시 형식:
- 단일 에이전트: `backend`
- 병렬 에이전트: `designer ‖ backend`

AskUserQuestion:
- 질문: "다음 순서로 진행합니다:\n{stages 목록}\n\n브랜치: {BRANCH}"
- 선택지: "시작 (Recommended)", "취소"

취소 시:
```bash
git checkout -
git branch -D "${BRANCH}"
rm -rf "${TASK_DIR}"
```
종료.

`stages`가 비어있으면 (설계/분석만): 결과 요약 후 종료.

### 7. 파이프라인 실행

`stages`를 순서대로 실행. `completed_stages` 이전 index는 스킵.

각 stage `i`마다:

**stage 내 에이전트가 1개** — 단독 blocking spawn:
```
Agent 도구 1개 호출:
  TASK_DIR: {TASK_DIR}
  PROJECT_ROOT: {PROJECT_ROOT}

  --- 인계 내용 ---
  {handoff.md 전체 내용}
  ---

  담당 작업을 수행하라.
```

**stage 내 에이전트가 2개 이상** — **단일 응답에서 여러 Agent 도구를 동시에 호출** (병렬):
- 각 에이전트에 동일한 프롬프트 구조 사용
- 프롬프트에 명시: "handoff.md는 수정하지 않는다. 자신의 결과 파일(design-spec.md, design.md 등)에만 저장하라."
- **모든 Agent 완료 대기**

stage 완료 후:
1. `pipeline.json`의 `completed_stages` 갱신 (재개 포인트 저장):
   ```bash
   python3 -c "
   import json
   p = json.load(open('${TASK_DIR}/pipeline.json'))
   p['completed_stages'] = $((i+1))
   json.dump(p, open('${TASK_DIR}/pipeline.json', 'w'), ensure_ascii=False, indent=2)
   "
   ```

2. 병렬 stage였다면 오케스트레이터가 handoff.md에 결과 포인터 추가:
   ```
   ## stage {i} 완료 — {에이전트 목록}
   - designer 결과: {TASK_DIR}/context/design-spec.md
   - backend 결과: 최신 git commit 참조
   ```

3. 다음 stage 에이전트에게는 갱신된 handoff.md 전달.

### 8. 완료 보고
```bash
git log --oneline feature/main..HEAD 2>/dev/null || git log --oneline -5
```

출력:
```
✅ 파이프라인 완료!
   브랜치: {BRANCH}
   실행된 에이전트: {에이전트 목록}
   커밋 목록: {git log 결과}

다음 단계:
  git merge {BRANCH}    # main에 병합
  /ship "다음 작업"     # 새 작업 시작
```

## 에이전트별 산출물

| 에이전트 | 결과 파일 | handoff.md |
|---------|---------|---------|
| planner | prd.md, pipeline.json | 작성 |
| designer | design-spec.md | 병렬 시 미수정, 단독 시 갱신 |
| backend | 코드 + tests, git commit | 병렬 시 미수정, 단독 시 갱신 |
| frontend | UI 소스코드, git commit | 갱신 |
| resolver | 충돌 해결, git commit | 갱신 |
