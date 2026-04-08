# Agent Orchestrator

## 세션 시작 시 필수 수행
1. `.claude/state/context/` 하위 파일 전체 읽기
2. `.claude/state/phase.txt` 확인 → 현재 페이즈 파악
3. `.claude/state/iterations.txt` 확인 → 반복 횟수 파악
4. `.claude/state/active_agent.txt` 확인 → 활성 에이전트 파악
5. 활성 에이전트의 `AGENT.md` 읽기

## 에이전트 활성화
- 백엔드 개발자: `.claude/agents/backend/AGENT.md`
- 기획자: `.claude/agents/planner/AGENT.md`
- 디자이너: `.claude/agents/designer/AGENT.md`
- 프론트엔드: `.claude/agents/frontend/AGENT.md`

## 에이전트 간 인계
- 인계 문서: `.claude/state/handoff.md`
- 인계 시 산출물 요약 후 다음 에이전트가 읽을 수 있도록 갱신

## 컨텍스트 관리 (IMPORTANT)
- 컨텍스트 60% 도달 시 즉시 `/compact` 실행
- 태스크 완료 시 반드시 `.claude/state/context/session_handoff.md` 갱신 후 git commit
- 태스크와 무관한 파일 읽기 금지

## 절대 규칙 (YOU MUST)
- 구현 코드 작성 전 반드시 실패하는 테스트 먼저 작성
- 테스트 없는 소스 코드 커밋 금지
- 페이즈 전환 시 반드시 `.claude/state/phase.txt` 갱신
