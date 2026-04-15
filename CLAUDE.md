# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 세션 시작 시 필수 수행

매 세션 시작마다 반드시 다음 순서로 상태를 복원한다. 파일이 없으면 초기 상태로 간주한다:

```
PROJECT_NAME = basename $(git rev-parse --show-toplevel 2>/dev/null || pwd)
STATE_DIR = ~/.claude/agent-crew/{PROJECT_NAME}
```

1. `{STATE_DIR}/context/session_handoff.md` 읽기
2. `{STATE_DIR}/pipeline.json` 확인
3. `{STATE_DIR}/phase.txt` 확인
4. `{STATE_DIR}/active_agent.txt` 확인
5. 활성 에이전트의 `~/.claude/agent-crew/agents/[에이전트]/AGENT.md` 읽기

## 에이전트 워크플로 명령어

```
/setup          # 현재 프로젝트 워크스페이스 초기화 (최초 1회)
/start "요청"   # 전체 파이프라인 자동 실행 (권장)

/requirements   # 요구사항 단계 수동 실행
/design         # 설계 단계 수동 실행
/implement      # 구현 단계 수동 실행
/verify         # 검증 단계 수동 실행
```

명령어는 `{STATE_DIR}/pipeline.json`의 `agents[currentIndex]`를 읽어 자동 라우팅된다.

## 절대 규칙

- 구현 코드 작성 전 반드시 실패하는 테스트 먼저 작성 (backend 에이전트)
- 테스트 없는 소스 코드 커밋 금지
- 페이즈 전환 시 반드시 `{STATE_DIR}/phase.txt` 갱신
- 컨텍스트 60% 도달 시 즉시 `/compact` 실행
- 태스크 완료 시 반드시 `{STATE_DIR}/context/session_handoff.md` 갱신 후 git commit

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
│   ├── start.md
│   ├── requirements.md
│   ├── design.md
│   ├── implement.md
│   └── verify.md
└── agent-crew/
    ├── agents/                  ← 에이전트 정의 (글로벌)
    │   ├── planner/
    │   ├── designer/
    │   ├── frontend/
    │   └── backend/
    └── {PROJECT_NAME}/          ← 프로젝트별 상태 (자동 생성)
        ├── pipeline.json
        ├── phase.txt
        ├── active_agent.txt
        ├── iterations.txt
        ├── handoff.md
        └── context/
            ├── session_handoff.md
            ├── prd.md
            ├── design-spec.md
            ├── requirements.md
            ├── design.md
            ├── tdd_log.md
            └── verify_checklist.md
```

### 에이전트 구성

| 에이전트 | 역할 |
|---------|------|
| planner | 요구사항 분석, PRD 작성, 파이프라인 결정 |
| designer | UI/UX 명세 작성 |
| frontend | UI 구현 및 검증 |
| backend | Kotlin+Spring Boot DDD/TDD 구현 |

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

```bash
# 한 번만 설치 (모든 프로젝트에서 사용 가능)
curl -s https://raw.githubusercontent.com/woogiekim/agent-crew/main/install.sh | bash

# 새 프로젝트 시작 시
/setup
/start "요청 내용"
```
