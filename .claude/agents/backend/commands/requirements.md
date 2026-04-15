# /requirements — 요구사항 수집

## 상태 경로
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

## 실행 순서
1. `{STATE_DIR}/context/requirements.md` 읽기 (기존 요구사항 확인)
2. 아래 항목을 순서대로 질문하며 요구사항 수집

## 수집 항목
- 도메인 컨텍스트: 어떤 비즈니스 도메인인가?
- 핵심 기능: 구현할 기능은 무엇인가?
- 비즈니스 규칙: 반드시 지켜야 할 규칙은?
- 제약 조건: 기술적/비즈니스적 제약은?
- 완료 기준: 어떤 상태가 되면 완료인가?

## 완료 시
1. `{STATE_DIR}/context/requirements.md` 갱신
2. `{STATE_DIR}/phase.txt` → `DESIGN` 갱신
3. `{STATE_DIR}/active_agent.txt` → `backend` 갱신
4. git commit: `chore: update requirements`
