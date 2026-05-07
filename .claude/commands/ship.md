# /ship — 전체 파이프라인 자동 실행

## 핵심 원칙

오케스트레이터(Claude)가 Agent 도구로 각 에이전트를 직접 spawn한다.
파일 폴링, daemon 프로세스, .ready 신호 파일 불필요.

**context 관리 원칙**: 에이전트에게 파일 내용을 인라인으로 넘기지 않는다.
경로(path)만 전달하고, 서브에이전트가 직접 읽는다. 오케스트레이터의 context는 좌표(경로, 상태)만 보유한다.

```
[오케스트레이터] /ship "요청"
      │  context: 좌표(경로, 상태)만 보유
      ▼
[planner] → prd.md + pipeline.json + handoff.md  (격리 context)
      │
      ▼ stage 0: 병렬 spawn — 경로만 전달
[designer] ‖ [backend]  (각자 격리 context, 파일은 직접 읽음)
      │
      ▼ stage 1: spawn — 경로만 전달
[frontend]  (격리 context)
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
  - "이어서 진행 (Recommended)"
  - "새 태스크 시작"

"이어서 진행" 선택 시:
```bash
TASK_DIR=$(dirname "$RESUME_PIPELINE")
TASK_ID=$(basename "$TASK_DIR")
BRANCH="feature/task-${TASK_ID}"
git checkout "${BRANCH}" 2>/dev/null || true
# pipeline.json의 completed_stages 확인 후 해당 stage부터 실행 (5단계 스킵 → 6단계로)
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

완료 후 pipeline.json만 읽는다 (handoff.md 내용은 오케스트레이터가 읽지 않는다):
```bash
cat "${TASK_DIR}/pipeline.json"
```

### 6. 파이프라인 확인 및 사용자 승인
`pipeline.json`에서 `stages` 배열 읽기.

AskUserQuestion:
- 질문: "다음 순서로 진행합니다:\n{stages 목록 (병렬은 ‖ 표시)}\n\n브랜치: {BRANCH}"
- 선택지: "시작 (Recommended)", "취소"

취소 시 정리 후 종료.
`stages`가 비어있으면: 결과 요약 후 종료.

### 7. 파이프라인 실행

`stages`를 순서대로 실행. `completed_stages` 이전 index는 스킵.

각 stage `i`마다 에이전트 프롬프트 형식:

```
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {PROJECT_ROOT}
HANDOFF_PATH: {TASK_DIR}/handoff.md

인계 내용은 HANDOFF_PATH 파일을 직접 읽어라. (인라인으로 전달하지 않음)
PRD는 {TASK_DIR}/context/prd.md 를 직접 읽어라.
담당 작업을 수행하라.
```

병렬 stage (에이전트 2개 이상)는 단일 응답에서 여러 Agent 도구를 동시에 호출.
- "handoff.md는 수정하지 않는다. 자신의 결과 파일에만 저장하라." 명시
- 모든 Agent 완료 대기

stage 완료 후 `completed_stages` 갱신:
```bash
python3 -c "
import json
p = json.load(open('${TASK_DIR}/pipeline.json'))
p['completed_stages'] = $((i+1))
json.dump(p, open('${TASK_DIR}/pipeline.json', 'w'), ensure_ascii=False, indent=2)
"
```

병렬 stage였다면 오케스트레이터가 handoff.md에 결과 포인터만 append (내용 전체 읽기 금지):
```bash
# 결과 파일 경로만 확인
ls "${TASK_DIR}/context/"
# handoff.md에 경로 포인터 추가 (cat 금지)
```

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
