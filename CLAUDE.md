# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 세션 시작 시 필수 수행

매 세션 시작마다 반드시 다음 순서로 상태를 복원한다. 파일이 없으면 초기 상태로 간주한다:

1. `.claude/state/context/session_handoff.md` 읽기 — 직전 세션 컨텍스트 파악
2. `.claude/state/pipeline.json` — 진행 중인 파이프라인 확인
3. `.claude/state/phase.txt` — 현재 페이즈 확인
4. `.claude/state/active_agent.txt` — 활성 에이전트 확인
5. 활성 에이전트의 `AGENT.md` 읽기

## 에이전트 워크플로 명령어

```
/setup          # 워크스페이스 초기화
/start "요청"   # 전체 파이프라인 자동 실행 (권장)

/requirements   # 요구사항 단계 수동 실행
/design         # 설계 단계 수동 실행
/implement      # 구현 단계 수동 실행
/verify         # 검증 단계 수동 실행
```

명령어는 `pipeline.json`의 `agents[currentIndex]`를 읽어 자동 라우팅된다.

## 절대 규칙

- 구현 코드 작성 전 반드시 실패하는 테스트 먼저 작성 (backend 에이전트)
- 테스트 없는 소스 코드 커밋 금지
- 페이즈 전환 시 반드시 `.claude/state/phase.txt` 갱신
- 컨텍스트 60% 도달 시 즉시 `/compact` 실행
- 태스크 완료 시 반드시 `.claude/state/context/session_handoff.md` 갱신 후 git commit

## 빌드 및 테스트 명령어 (Kotlin/Spring Boot 프로젝트)

```bash
./gradlew build
./gradlew test
./gradlew test --tests "TestClassName"
./gradlew test --tests "ClassName.methodName"
```

## 아키텍처 개요

**agent-crew**: Claude Code 플러그인 — 멀티 에이전트 개발 워크스페이스

### 에이전트 구성

| 에이전트 | AGENT.md | 역할 |
|---------|----------|------|
| planner | `.claude/agents/planner/AGENT.md` | 요구사항 분석, PRD 작성, 파이프라인 결정 |
| designer | `.claude/agents/designer/AGENT.md` | UI/UX 명세 작성 |
| frontend | `.claude/agents/frontend/AGENT.md` | UI 구현 및 검증 |
| backend | `.claude/agents/backend/AGENT.md` | Kotlin+Spring Boot DDD/TDD 구현 |

### 파이프라인 자동 결정 (planner 기준)

| 요청 유형 | 파이프라인 |
|---------|---------|
| 백엔드 API / 도메인 로직 | planner → backend |
| 풀스택 | planner → designer → frontend → backend |
| UI만 | planner → designer → frontend |

### 상태 파일 구조

```
.claude/state/
├── phase.txt             # REQUIREMENTS / DESIGN / IMPLEMENTATION / VERIFICATION / DONE
├── active_agent.txt      # 현재 에이전트
├── iterations.txt        # 재시도 횟수 (backend 에이전트, 최대 5회)
├── pipeline.json         # 파이프라인 정의 {"task","agents","currentIndex","status"}
├── handoff.md            # 에이전트 간 인계 문서
└── context/
    ├── session_handoff.md  # 세션 복원용
    ├── prd.md              # planner 산출물
    ├── design-spec.md      # designer 산출물
    ├── requirements.md     # backend 도메인 요구사항
    ├── design.md           # backend DDD 설계
    ├── tdd_log.md          # TDD 사이클 이력
    └── verify_checklist.md # 검증 결과
```

### 자동화 훅

| 훅 | 트리거 | 역할 |
|----|--------|------|
| `verify-rules.sh` | PostToolUse (Edit/Write, `.kt` 파일) | else 사용, getter 과다, 테스트 파일 누락 감지 |
| `guard-dangerous-commands.sh` | PreToolUse (Bash) | 위험 명령어 차단 |

### 스킬 (온디맨드 로딩)

`.claude/agents/backend/skills/`:
- `oop-principles.md` — 객체지향 생활체조 원칙 9가지
- `ddd.md` — DDD 전술 패턴
- `tdd.md` — TDD 사이클 및 MockK 패턴

## 플러그인 설치

```bash
/plugin install agent-crew
/setup
```
