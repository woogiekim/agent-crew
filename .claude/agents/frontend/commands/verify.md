# frontend /verify — UI 검증

## 상태 경로
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

## 실행 순서

1. `{STATE_DIR}/context/design-spec.md` 읽기
2. 아래 체크리스트 하나씩 점검

## 검증 체크리스트
- [ ] 모든 화면 구현 완료 (design-spec의 화면 목록 대조)
- [ ] 컴포넌트 명세 충족 (props, 상태 구조)
- [ ] 인터랙션 흐름 정상 동작
- [ ] API 연동 포인트 인터페이스 준수

## 결과 처리

### 통과 시
1. `{STATE_DIR}/context/verify_checklist.md` 갱신 (PASS)
2. `{STATE_DIR}/pipeline.json` currentIndex + 1
3. `{STATE_DIR}/handoff.md` 갱신 (frontend 산출물 요약)
4. git commit: `chore: frontend verification passed`
5. 다음 에이전트 자동 실행

### 실패 시
1. `{STATE_DIR}/context/verify_checklist.md` 갱신 (FAIL + 실패 항목)
2. frontend /implement 단계로 복귀하여 재구현
