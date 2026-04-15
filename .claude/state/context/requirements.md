# 요구사항 명세

## 프로젝트
- 이름: agent-crew
- 리포지토리: woogiekim/agent-crew
- 성격: Claude Code 플러그인 — 멀티 에이전트 개발 워크스페이스

## 우선순위
D → C → B → A

---

## D. 워크스페이스 설치/배포

### 설치 방식
- Claude Code 플러그인 마켓플레이스
- 설치 명령: `/plugin install agent-crew`
- 초기화 명령: `/setup`

### /setup 동작
- 모든 에이전트 동시 활성화 (선택 없음)
- `.claude/state/` 초기화
- 기존 `.claude/` 있을 때 덮어쓰기 여부 확인
- 완료 메시지 출력

---

## C. 에이전트 간 인계 워크플로

### 진입점
- `/start "사용자 요청"` — 전체 파이프라인 자동 실행

### 동작 흐름
1. planner가 요청 분석 → 필요한 에이전트 목록 결정
2. 사용자에게 파이프라인 확인 요청 ("backend, designer, frontend 에이전트가 필요합니다. 진행할까요?")
3. 확인 후 에이전트 순서대로 자동 순차 실행
4. 각 단계 완료 시 다음 에이전트로 자동 인계

### 에이전트 실행 순서 (풀스택 예시)
```
planner → designer → frontend → backend
```

---

## B. 기존 백엔드 에이전트 개선

### 명령어 (사용자 관점 — 단순하게 유지)
- `/requirements` — 요구사항 정리
- `/design`       — 설계
- `/implement`    — 구현
- `/verify`       — 검증

### 내부 동작
- 명령어 실행 시 `active_agent.txt` 읽어 해당 에이전트 로직으로 라우팅
- 사용자는 어떤 에이전트가 처리하는지 알 필요 없음

### 기술 스택 유지
- Kotlin + Spring Boot
- JUnit5 + MockK
- Gradle

---

## A. 새 에이전트 구현

### planner
- 역할: 사용자 요청 분석, PRD 작성, 필요 에이전트 판단
- 산출물: `.claude/state/context/prd.md`

### designer
- 역할: PRD 기반 UI/UX 명세 작성 (화면 구성, 컴포넌트 정의)
- 산출물: `.claude/state/context/design-spec.md`

### frontend
- 역할: 디자인 명세 기반 UI 구현
- 기술 스택: 추후 결정
- 산출물: 프론트엔드 소스 코드

### backend
- 현행 유지 (Kotlin+Spring Boot, DDD/TDD)

---

## 완료 기준
- [ ] `/plugin install agent-crew` 로 설치 가능
- [ ] `/setup` 으로 워크스페이스 초기화
- [ ] `/start "요청"` 으로 전체 파이프라인 자동 실행
- [ ] `/requirements` `/design` `/implement` `/verify` 단계별 수동 실행 가능
- [ ] planner가 불필요한 에이전트를 자동으로 제외
