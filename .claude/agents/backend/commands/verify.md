# /verify — 검증

## 상태 경로
```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

## 실행 순서
1. `~/.claude/agent-crew/agents/backend/skills/oop-principles.md` 읽기
2. `~/.claude/agent-crew/agents/backend/skills/ddd.md` 읽기
3. `./gradlew test` 실행 → 전체 테스트 통과 확인
4. 아래 체크리스트 하나씩 점검

## 검증 체크리스트
- [ ] 객체지향 생활체조 원칙 위반 없음
  - 메서드 들여쓰기 1단계
  - else 키워드 미사용
  - 원시값 포장
  - 일급 컬렉션
  - 점 하나
  - 축약 금지
- [ ] Tell, Don't Ask 원칙 준수 (getter로 꺼내서 판단하지 않음)
- [ ] DDD 전술 패턴 올바른 적용
  - Aggregate Root가 트랜잭션 경계인가
  - Value Object가 불변인가
  - Domain Event가 발행되는가
  - Repository 인터페이스가 도메인 레이어에 있는가
- [ ] 모든 테스트 GREEN (`./gradlew test`)
- [ ] 트레이드오프 문서화 (`{STATE_DIR}/context/design.md`)

## 결과 처리

### 통과 시
1. `{STATE_DIR}/context/verify_checklist.md` 갱신 (PASS)
2. 완료 이벤트 emit
   ```bash
   echo "{\"ts\":\"$(date -u +%FT%TZ)\",\"agent\":\"backend\",\"event\":\"PHASE_COMPLETE\",\"payload\":{\"phase\":\"verification\"}}" >> {STATE_DIR}/events.jsonl
   ```
   - 데몬 실행 중: 데몬이 `pipeline.json` status → DONE, `phase.txt` → DONE 처리
   - 데몬 없음 (fallback): `{STATE_DIR}/phase.txt` → `DONE` 직접 갱신
3. git commit: `chore: verification passed`

### 실패 시
1. `{STATE_DIR}/context/verify_checklist.md` 갱신 (FAIL + 실패 항목)
2. `{STATE_DIR}/iterations.txt` 값 +1 갱신
3. iterations < 5: `{STATE_DIR}/phase.txt` → `DESIGN` 직접 갱신 (복귀이므로 데몬 우회)
4. iterations >= 5: `{STATE_DIR}/phase.txt` → `REQUIREMENTS`, iterations → `0` 직접 갱신
