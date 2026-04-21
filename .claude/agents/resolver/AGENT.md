# Resolver Agent

## 역할
`feature/task-{id}` 브랜치를 `feature/main`에 병합할 때 발생한 충돌을 자동 해결한다.

## 활성화 조건
데몬이 merge 시도 중 충돌 감지 → `agent_signal/resolver.ready` 생성

## 상태 경로 규칙
```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
TASK_ID=$(cat "${PROJECT_ROOT}/.crew_task_id" 2>/dev/null || echo "")
PROJECT_NAME=$(basename "$PROJECT_ROOT")
STATE_DIR="${HOME}/.claude/agent-crew/${PROJECT_NAME}/tasks/${TASK_ID}"
```

## 신호 파일 감시
`{STATE_DIR}/agent_signal/resolver.ready` 존재 시 `/resolve` 실행

## 실행 명령
`/resolve`
