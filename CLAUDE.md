# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 에이전트 워크플로 명령어

```
/setup                           # 현재 프로젝트 워크스페이스 초기화 (최초 1회)
/ship "요청"                     # 단일 태스크 전체 파이프라인 자동 실행
/crew "태스크A" "태스크B" ...    # 여러 독립 태스크 병렬 실행
/cost                            # 세션 비용 요약
```

**`/ship`** — 오케스트레이터가 Agent 도구로 서브에이전트를 직접 spawn.
같은 stage의 에이전트는 단일 응답에서 동시에 호출해 **stage 내 병렬 실행**.
예: 풀스택 → planner → [designer ‖ backend] → frontend

**`/crew`** — 여러 독립 태스크를 각자 git worktree에서 격리 실행.
각 task-runner가 자신의 전체 파이프라인을 자율 실행하며 완전히 독립된 context.
예: "로그인 API" ‖ "상품 API" ‖ "주문 API" → 동시 처리

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
│   ├── ship.md
│   ├── crew.md
│   └── cost.md
└── agent-crew/
    ├── agents/                  ← 서브에이전트 정의 (flat .md, frontmatter 포함)
    │   ├── planner.md           ← claude-sonnet-4-6
    │   ├── designer.md          ← claude-haiku-4-5
    │   ├── frontend.md          ← claude-sonnet-4-6
    │   ├── backend.md           ← claude-sonnet-4-6
    │   ├── resolver.md          ← claude-haiku-4-5
    │   ├── task-runner.md       ← claude-sonnet-4-6  (/crew가 spawn)
    │   └── skills/              ← 온디맨드 참조 스킬
    │       ├── tdd.md
    │       ├── ddd.md
    │       └── oop-principles.md
    └── {PROJECT_NAME}/          ← 프로젝트별 상태 (자동 생성)
        └── tasks/
            └── {TASK_ID}/       ← task별 상태 (TASK_ID = YYYYmmdd-HHMMSS[-index])
                ├── pipeline.json    ← {"task": "...", "stages": [[...], [...]], "completed_stages": 0}
                ├── handoff.md       ← 에이전트 간 인계 문서
                ├── result.md        ← task-runner 완료 보고 (/crew 전용)
                └── context/
                    ├── prd.md
                    ├── design-spec.md
                    └── ...

{PROJECT_ROOT}/
└── .crew-worktrees/             ← 병렬 태스크 작업 디렉토리 (gitignore, 태스크 완료 후 자동 삭제)
    ├── {TASK_ID_0}/             ← git worktree
    └── {TASK_ID_1}/
```

### 에이전트 구성

| 에이전트 | 역할 |
|---------|------|
| planner | 요구사항 분석, PRD 작성, 파이프라인 결정 |
| designer | UI/UX 명세 작성 |
| frontend | UI 구현 및 검증 |
| backend | Kotlin+Spring Boot DDD/TDD 구현 |
| resolver | 병합 충돌 자동 해결 |
| task-runner | 단일 태스크 전체 파이프라인 자율 실행 (`/crew`가 spawn) |

### 파이프라인 자동 결정

`UserPromptSubmit` 훅(`auto-route.sh`)이 자연어 키워드를 감지해 라우팅 힌트를 자동 주입한다.
슬래시 커맨드(`/ship` 등)나 질문/설명 요청은 라우팅 스킵.

| 감지 조건 | 파이프라인 |
|---------|---------|
| 풀스택 키워드 (`풀스택`, `full-stack`, `시스템 개발` 등) | planner → [designer ‖ backend] → frontend |
| 프론트엔드 + 백엔드 키워드 동시 포함 | planner → [designer ‖ backend] → frontend |
| UI 설계 키워드 (`UX`, `와이어프레임`, `화면 설계` 등) | designer (→ frontend) |
| 프론트엔드 키워드만 (`UI`, `컴포넌트`, `React` 등) | designer → frontend |
| 백엔드 키워드만 (`API`, `도메인`, `Entity`, `Spring` 등) | backend |

**키워드 패턴 (auto-route.sh 기준)**
- 백엔드: `API`, `백엔드`, `서버`, `도메인`, `Entity`, `Repository`, `Service`, `Kotlin`, `Spring`, `Controller`, `UseCase`
- 프론트엔드: `UI`, `화면`, `컴포넌트`, `React`, `Vue`, `Next`, `페이지`, `버튼`, `폼`, `CSS`
- 풀스택: `풀스택`, `전체 개발`, `서비스 개발`, `앱 개발`
- UI 설계: `UI 설계`, `화면 설계`, `UX`, `와이어프레임`
- 액션 동사 없으면 라우팅 스킵: `만들어`, `구현해`, `개발해`, `추가해` 등 필요

### 스킬 강제 실행 메커니즘

Claude Code는 스킬이 매칭될 때 스킬을 먼저 호출해야 한다는 시스템 규칙을 갖고 있다.
그러나 Claude의 판단에만 의존하면 이 규칙이 지켜지지 않을 수 있다.

**`auto-route.sh` 훅이 이를 강제한다**:
- 개발 요청 키워드 감지 시 `hookSpecificOutput.additionalContext`로 directive를 주입
- plain text 출력이 아닌 JSON 형식 → Claude의 system context에 확실하게 삽입됨
- 메시지: "⛔ 직접 구현 금지 — 반드시 스킬/에이전트를 먼저 실행할 것"

```
# Claude의 기억(memory/preferences)으로는 보장 불가
# settings.json hooks만이 동작을 보장한다
```

슬래시 명령어(`/ship`, `/crew` 등)나 질문/설명 요청은 스킵.

### Context 관리 원칙

**파일 내용 인라인 금지** — 에이전트 프롬프트에 파일 내용을 직접 삽입하면 부모 context가 매 stage마다 누적된다.
경로(path)만 전달하고 서브에이전트가 직접 읽는다.

```
# 금지 패턴 (context 폭발)
prompt: "--- 인계 내용 ---\n{handoff.md 전체 내용}\n---"

# 올바른 패턴 (context 보존)
prompt: "HANDOFF_PATH: {TASK_DIR}/handoff.md\n인계 내용은 위 파일을 직접 읽어라."
```

**context 흐름 (이상적 상태)**:

| 레벨 | 보유 정보 | 크기 |
|------|----------|------|
| 오케스트레이터 (`/ship`) | 경로, 상태, stage 완료 여부 | 소 |
| task-runner (`/crew`) | 경로, pipeline.json 상태 | 소 |
| 각 서브에이전트 | 자신이 읽은 파일 + 구현 | 중 (격리) |

**context-guard 훅** — Agent 도구 호출 시 프롬프트가 2000자 이상이거나 500자+ 코드블록을 포함하면 경고를 주입한다.

### 자동화 훅

| 훅 | 트리거 | 역할 |
|----|--------|------|
| `verify-rules.sh` | PostToolUse (Edit/Write, `.kt`/`.ts`/`.tsx`/`.js`) | Kotlin: else·getter 과다·테스트 누락 / TS: any·console·테스트 누락 |
| `guard-dangerous-commands.sh` | PreToolUse (Bash) | 위험 명령어 차단 |
| `context-guard.sh` | PreToolUse (Agent) | 에이전트 프롬프트 비대화 감지 (2000자+ 또는 코드블록 500자+) |

## 플러그인 설치

```
# 한 번만 설치 (모든 프로젝트에서 사용 가능)
/plugin marketplace add https://github.com/woogiekim/agent-crew
/plugin install agent-crew

# 새 프로젝트 시작 시
/setup
/ship "요청 내용"
```
