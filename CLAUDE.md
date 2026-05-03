# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 에이전트 워크플로 명령어

```
/setup          # 현재 프로젝트 워크스페이스 초기화 (최초 1회)
/ship "요청"    # 전체 파이프라인 자동 실행 (권장)
```

`/ship`은 오케스트레이터가 Agent 도구로 각 서브에이전트를 직접 spawn한다.
planner → (designer →) (frontend →) (backend →) 순서로 실제 Claude 서브에이전트 실행.

## 절대 규칙

- 구현 코드 작성 전 반드시 실패하는 테스트 먼저 작성 (backend 에이전트)
- 테스트 없는 소스 코드 커밋 금지
- 컨텍스트 60% 도달 시 즉시 `/compact` 실행

## 빌드 및 테스트 명령어 (Kotlin/Spring Boot 프로젝트)

```bash
./gradlew build
./gradlew test
./gradlew test --tests "TestClassName"
./gradlew test --tests "ClassName.methodName"
```

## 아키텍처 개요

**agent-crew**: Claude Code 글로벌 플러그인 — 모든 프로젝트에서 멀티 에이전트 개발 워크스페이스 제공

### 글로벌 설치 구조

```
~/.claude/
├── commands/                    ← 글로벌 명령어 (모든 프로젝트에서 사용)
│   ├── setup.md
│   └── ship.md
└── agent-crew/
    ├── agents/                  ← 서브에이전트 정의 (flat .md, frontmatter 포함)
    │   ├── planner.md           ← claude-sonnet-4-6
    │   ├── designer.md          ← claude-haiku-4-5
    │   ├── frontend.md          ← claude-sonnet-4-6
    │   ├── backend.md           ← claude-sonnet-4-6
    │   ├── resolver.md          ← claude-haiku-4-5
    │   └── skills/              ← 온디맨드 참조 스킬
    │       ├── tdd.md
    │       ├── ddd.md
    │       └── oop-principles.md
    └── {PROJECT_NAME}/          ← 프로젝트별 상태 (자동 생성)
        └── tasks/
            └── {TASK_ID}/       ← task별 상태 (TASK_ID = YYYYmmdd-HHMMSS)
                ├── pipeline.json    ← {"task": "...", "agents": [...]}
                ├── handoff.md       ← 에이전트 간 인계 문서
                └── context/
                    ├── prd.md
                    ├── design-spec.md
                    └── ...
```

### 에이전트 구성

| 에이전트 | 역할 |
|---------|------|
| planner | 요구사항 분석, PRD 작성, 파이프라인 결정 |
| designer | UI/UX 명세 작성 |
| frontend | UI 구현 및 검증 |
| backend | Kotlin+Spring Boot DDD/TDD 구현 |
| resolver | 병합 충돌 자동 해결 |

### 파이프라인 자동 결정 (planner 기준)

| 요청 유형 | 파이프라인 |
|---------|---------|
| 백엔드 API / 도메인 로직 | planner → backend |
| 풀스택 | planner → designer → frontend → backend |
| UI만 | planner → designer → frontend |

### 자동화 훅

| 훅 | 트리거 | 역할 |
|----|--------|------|
| `verify-rules.sh` | PostToolUse (Edit/Write, `.kt` 파일) | else 사용, getter 과다, 테스트 파일 누락 감지 |
| `guard-dangerous-commands.sh` | PreToolUse (Bash) | 위험 명령어 차단 |

## 플러그인 설치

```
# 한 번만 설치 (모든 프로젝트에서 사용 가능)
/plugin marketplace add https://github.com/woogiekim/agent-crew
/plugin install agent-crew

# 새 프로젝트 시작 시
/setup
/ship "요청 내용"
```
