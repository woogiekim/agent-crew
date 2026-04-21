# Agent Orchestrator

## 상태 경로 규칙
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

에이전트는 항상 위 규칙으로 STATE_DIR을 결정한다.
워크트리 내에서 실행 중이면 TASK_ID가 존재하므로 task-level STATE_DIR을 사용한다.

## 세션 시작 시 필수 수행
1. `{STATE_DIR}/context/session_handoff.md` 읽기 → 직전 세션 컨텍스트 파악
2. `{STATE_DIR}/pipeline.json` 확인 → 진행 중인 파이프라인 파악
3. `{STATE_DIR}/phase.txt` 확인 → 현재 페이즈 파악
4. `{STATE_DIR}/active_agent.txt` 확인 → 활성 에이전트 파악
5. 활성 에이전트의 `~/.claude/agent-crew/agents/[에이전트]/AGENT.md` 읽기

## 에이전트 활성화
- 기획자: `~/.claude/agent-crew/agents/planner/AGENT.md`
- 디자이너: `~/.claude/agent-crew/agents/designer/AGENT.md`
- 프론트엔드: `~/.claude/agent-crew/agents/frontend/AGENT.md`
- 백엔드 개발자: `~/.claude/agent-crew/agents/backend/AGENT.md`
- 충돌 해결자: `~/.claude/agent-crew/agents/resolver/AGENT.md`

## 에이전트 간 인계
- 인계 문서: `{STATE_DIR}/handoff.md`
- 인계 시 산출물 요약 후 다음 에이전트가 읽을 수 있도록 갱신

## 컨텍스트 관리 (IMPORTANT)
- 컨텍스트 60% 도달 시 즉시 `/compact` 실행
- 태스크 완료 시 반드시 `{STATE_DIR}/context/session_handoff.md` 갱신 후 git commit
- 태스크와 무관한 파일 읽기 금지

## UX 규칙 (YOU MUST)
- 사용자에게 확인이나 선택을 요청할 때는 반드시 `AskUserQuestion` 도구를 사용한다
- `[y/N]`, `[Y/n]` 등 텍스트 프롬프트 방식은 절대 사용하지 않는다
- 선택지는 명확한 label과 description으로 구성하며, 권장 옵션이 있으면 "(Recommended)"를 붙여 첫 번째에 배치한다

## 절대 규칙 (YOU MUST)
- 구현 코드 작성 전 반드시 실패하는 테스트 먼저 작성
- 테스트 없는 소스 코드 커밋 금지
- 페이즈 전환 시 반드시 `{STATE_DIR}/phase.txt` 갱신
