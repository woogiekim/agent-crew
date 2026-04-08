# /verify — 검증

## 실행 순서
1. `.claude/agents/backend/skills/oop-principles.md` 읽기
2. `.claude/agents/backend/skills/ddd.md` 읽기
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
- [ ] 트레이드오프 문서화 (`.claude/state/context/design.md`)

## 결과 처리

### 통과 시
1. `.claude/state/context/verify_checklist.md` 갱신 (PASS)
2. `.claude/state/phase.txt` → `DONE` 갱신
3. git commit: `chore: verification passed`

### 실패 시
1. `.claude/state/context/verify_checklist.md` 갱신 (FAIL + 실패 항목)
2. `.claude/state/iterations.txt` 값 +1 갱신
3. iterations < 5: `.claude/state/phase.txt` → `DESIGN`
4. iterations >= 5: `.claude/state/phase.txt` → `REQUIREMENTS`, iterations → `0`
