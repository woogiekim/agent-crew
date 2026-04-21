# frontend /implement — UI 구현

## 상태 경로
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

## 실행 순서

1. `{STATE_DIR}/context/design-spec.md` 읽기
2. `{STATE_DIR}/handoff.md` 읽기

3. 컴포넌트 단위로 순차 구현
   - 공통 컴포넌트 → 페이지 컴포넌트 → 인터랙션 순서로 진행
   - API 연동 포인트는 인터페이스만 정의, 실제 연동은 backend 완료 후

4. git commit: `feat: frontend implement [화면명]`

## 완료 후
`{STATE_DIR}/phase.txt` → `VERIFICATION` 갱신 후 frontend /verify 단계로 진행한다.
