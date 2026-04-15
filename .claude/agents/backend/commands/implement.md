# /implement — TDD 구현

## 상태 경로
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

## 실행 순서
1. `{STATE_DIR}/context/design.md` 읽기
2. `~/.claude/agent-crew/agents/backend/skills/tdd.md` 읽기
3. `~/.claude/agent-crew/agents/backend/skills/oop-principles.md` 읽기
4. 아래 TDD 사이클 반복

## TDD 사이클 (반드시 준수)

### RED
- 실패하는 테스트 작성
- `./gradlew test --tests "[테스트클래스]"` 실행
- FAIL 또는 컴파일 에러 확인 (통과되면 테스트가 잘못된 것)

### GREEN
- 테스트를 통과하는 최소 코드 작성
- `./gradlew test --tests "[테스트클래스]"` 실행
- PASS 확인

### REFACTOR
- 중복 제거, 원칙 점검
- `./gradlew test --tests "[테스트클래스]"` 실행
- 여전히 PASS 확인

## 사이클 완료 시
- `{STATE_DIR}/context/tdd_log.md` 에 사이클 결과 기록
- 모든 기능 구현 완료 시 `{STATE_DIR}/phase.txt` → `VERIFICATION` 갱신
- git commit: `feat: [구현내용] with tests`
