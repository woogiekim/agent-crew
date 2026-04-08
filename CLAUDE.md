# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 세션 시작 시 필수 수행

매 세션 시작마다 반드시 다음 순서로 상태를 복원해야 한다:

1. `.claude/state/context/` 하위 파일 전체 읽기
2. `.claude/state/phase.txt` — 현재 페이즈 확인
3. `.claude/state/iterations.txt` — 반복 횟수 확인
4. `.claude/state/active_agent.txt` — 활성 에이전트 확인
5. 활성 에이전트의 `AGENT.md` 읽기 (예: `.claude/agents/backend/AGENT.md`)

## 에이전트 워크플로 명령어

백엔드 에이전트 기준 워크플로:

```
/requirements   # Phase 1: 요구사항 수집
/design         # Phase 2: DDD 도메인 설계
/implement      # Phase 3: TDD 구현 (RED → GREEN → REFACTOR)
/verify         # Phase 4: 체크리스트 검증
```

명령어 정의 파일 위치: `.claude/agents/backend/commands/`

## 절대 규칙

- 구현 코드 작성 전 반드시 실패하는 테스트 먼저 작성
- 테스트 없는 소스 코드 커밋 금지
- 페이즈 전환 시 반드시 `.claude/state/phase.txt` 갱신
- 컨텍스트 60% 도달 시 즉시 `/compact` 실행
- 태스크 완료 시 반드시 `.claude/state/context/session_handoff.md` 갱신 후 git commit

## 빌드 및 테스트 명령어 (Kotlin/Spring Boot 프로젝트)

```bash
./gradlew build                               # 전체 빌드
./gradlew test                                # 전체 테스트 실행
./gradlew test --tests "TestClassName"        # 단일 테스트 클래스 실행
./gradlew test --tests "ClassName.methodName" # 단일 테스트 메서드 실행
```

## 아키텍처 개요

### 멀티 에이전트 시스템

| 에이전트 | AGENT.md 위치 | 역할 | 상태 |
|---------|--------------|------|------|
| backend | `.claude/agents/backend/AGENT.md` | Kotlin+Spring Boot DDD/TDD 구현 | 완료 |
| planner | `.claude/agents/planner/AGENT.md` | 요구사항 분석 및 PRD 작성 | 예정 |
| designer | `.claude/agents/designer/AGENT.md` | UI/UX 명세 설계 | 예정 |
| frontend | `.claude/agents/frontend/AGENT.md` | UI 구현 | 예정 |

### 상태 파일 구조

```
.claude/state/
├── phase.txt             # 현재 페이즈 (REQUIREMENTS / DESIGN / IMPLEMENTATION / VERIFICATION / DONE)
├── active_agent.txt      # 활성 에이전트 이름
├── iterations.txt        # 재시도 횟수 (최대 5회, 초과 시 REQUIREMENTS 재시작)
├── handoff.md            # 에이전트 간 인계 문서
└── context/
    ├── session_handoff.md  # 세션 복원용 핵심 컨텍스트
    ├── requirements.md     # 확정된 요구사항
    ├── design.md           # 확정된 설계
    ├── tdd_log.md          # TDD 사이클 이력
    └── verify_checklist.md # 검증 결과
```

### 백엔드 에이전트 페이즈 전환

```
REQUIREMENTS → DESIGN → IMPLEMENTATION → VERIFICATION → DONE
                  ↑____________↓  (최대 5회 반복)
```

### 스킬 (온디맨드 로딩)

`.claude/agents/backend/skills/` 에 위치한 지식베이스는 필요 시에만 로드:
- `oop-principles.md` — 객체지향 운동 원칙 9가지
- `ddd.md` — DDD 전술 패턴 (Aggregate Root, Entity, Value Object, Domain Event)
- `tdd.md` — TDD 사이클 및 MockK 사용 패턴

### 자동화 훅

`.claude/hooks/` 에 두 개의 훅이 설정되어 있다:

- **verify-rules.sh** (PostToolUse / Edit·Write): Kotlin 파일 수정 시 `else` 사용, 과도한 getter 호출(3회 이상), 테스트 파일 누락 감지
- **guard-dangerous-commands.sh** (PreToolUse / Bash): `rm -rf`, `DROP TABLE`, `git push --force`, `git reset --hard HEAD` 등 위험 명령 차단

## 병렬 에이전트 실행 (Git Worktree)

```bash
# 터미널별로 분리된 워크트리에서 에이전트 병렬 실행
claude --worktree agent/backend
claude --worktree agent/planner
claude --worktree agent/frontend
```
