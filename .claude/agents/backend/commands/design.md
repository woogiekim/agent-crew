# /design — 설계

## 실행 순서
1. `.claude/state/context/requirements.md` 읽기
2. `.claude/agents/backend/skills/ddd.md` 읽기
3. `.claude/agents/backend/skills/oop-principles.md` 읽기
4. 아래 항목 순서로 설계 수행

## 설계 항목
### 도메인 모델 도출
- Aggregate Root 식별
- Entity 식별
- Value Object 식별
- Domain Event 식별

### 트레이드오프 분석
| 선택 | 장점 | 단점 |
|------|------|------|

### 원칙 검증
- 생활체조 원칙 위반 여부
- Tell Don't Ask 위반 여부
- DDD 패턴 올바른 적용 여부

## 완료 시
1. `.claude/state/context/design.md` 갱신
2. `.claude/state/phase.txt` → `IMPLEMENTATION` 갱신
3. git commit: `docs: update design`
