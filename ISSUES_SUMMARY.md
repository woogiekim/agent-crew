# Agent-Crew Issues Summary

**마지막 업데이트:** 2026-05-29  
**총 이슈 수:** 128 (Open: 2, Closed: 126)

---

## 📊 오픈 이슈 (2개)

### [#128] P4 백그라운드 완료 시 호스트 TaskList 자동 정리 누락
- **상태:** 🟢 Open (3시간 전)
- **라벨:** 없음
- **상세:** 백그라운드 fan-out 경로(`agent_background=true`)에서 supervisor 완료 후 호스트 TaskList 항목(orchestrator task + backend/reviewer stage task)이 `in_progress`/`pending`으로 남아 정리가 안 됨.
- **근본 원인:** supervisor가 파일 기반 마커는 정리하지만 호스트 TaskList의 status를 completed로 전이하지 않음
- **제안:**
  - (a) 오케스트레이터가 백그라운드 완료 알림 수신 시 `host_task_id`들을 `TaskUpdate(status=completed)`로 전이
  - (b) supervisor가 각 stage 종료 시 자신의 `host_task_id`를 `TaskUpdate`로 전이
  - (c) `crew:status`가 `result.md`의 `STATUS: completed`를 읽어 호스트 TaskList 자동 reconcile

### [#127] Allow read-only requests to use crew:agent without the full pipeline
- **상태:** 🟢 Open (1일 전)
- **라벨:** `enhancement`
- **상세:** 간단한 read-only 질문도 `crew:run → supervisor → 모든 stage`를 거치는 오버헤드가 발생
- **제안:** 라우팅 분리
  - Read-only: `crew:agent` (직접 라우팅, supervisor 없음)
  - Mutating: `crew:run` (supervisor)

---

## 📋 최근 해결 이슈 (Closed: 126개)

### 핵심 영역별 분류

#### 1️⃣ 아키텍처 & 설계 (Closed)
- **#126**: Core objective gap: every substantive response must use agent-crew agents
- **#125**: BUG: Host AI ignores STOP/ROUTE hook directives (soft signal vs hard gate gap)
- **#113**: Design durable AI workflow protocol specification
- **#112**: Build workflow-safe plugin and runtime extension architecture
- **#111**: Implement workflow continuity observability system
- **#110**: Implement human-supervised execution approval system
- **#109**: Define role-oriented execution contract architecture
- **#108**: Implement persistent checkpoint and resume system
- **#107**: Design durable workflow state machine architecture
- **#106**: Define Persistent AI Workforce vision
- **#105**: Establish workflow-first architecture direction
- **#104**: Define foundational philosophy and operational constitution

#### 2️⃣ 품질 보증 & 테스팅 (Closed)
- **#114**: Achieve true raw 100% Python test coverage
- **#84**: Require reviewer immediately after each TDD implementation stage
- **#83**: Tighten rework-cycle validation to require same-stage TDD retry semantics
- **#82**: Reject multi-implementer TDD stages before dispatch
- **#81**: Planning-time gate: code implementation stages must start with TDD
- **#80**: GA quality loop: make REVIEW NEEDS_CHANGES trigger implementer retry
- **#79**: GA quality loop: block runtime auto-complete without actual pipeline loop evidence
- **#78**: GA quality loop: verify pipeline-level TDD/review/refactor/re-review execution
- **#77**: GA quality gate: enforce TDD and reviewer loops before implementation completion

#### 3️⃣ 기능 구현 & 개선 (Closed)
- **#122**: P1: Run final GA readiness decision
- **#121**: P0: Generate release artifacts and checksum manifest
- **#120**: P0: Validate hosted adapter auto-completion
- **#119**: P0: Generate production readiness evidence bundle
- **#118**: P0: Clean stale readiness state and host-bridge blockers
- **#117**: FEATURE: Enforce context-break line breaks in generated code
- **#116**: BUG: supervisor bypasses pipeline stages (analyst/backend/reviewer)
- **#115**: issuer 에이전트 책임 확장: create → lifecycle management
- **#97**: Add deterministic multilingual instruction normalization gate
- **#96**: Modularize core CLI responsibilities incrementally
- **#95**: Expand runtime replay golden coverage
- **#94**: Improve cost telemetry realism and routing auditability
- **#93**: Reduce Codex policy-only gaps with practical enforcement
- **#92**: Operationalize state cleanup and stale marker reporting
- **#91**: Improve observability effectiveness for runtime telemetry emission
- **#72**: GA blocker: make Codex host bridge complete crew handoffs automatically

#### 4️⃣ 문서 & 규칙 (Closed)
- **#124**: RULE: Avoid redundant context in method names
- **#123**: 코드 품질 규칙을 언어/환경에 무관하게 적용
- **#76**: Keep active-work workflow explanations brief
- **#87**: Clarify Codex adapter capability reports for policy-only support
- **#90**: Add dry-run cleanup and archival policy for stale task state

#### 5️⃣ 메모리 & 통합 (Closed)
- **#99**: Define a stable memory provider contract between agent-crew and mnemos
- **#101**: Publish compatibility matrix for agent-crew and mnemos versions
- **#102**: Remove direct dependency on mnemos internal FTS database path
- **#57**: mnemos: AI 대화 중 중요 인사이트를 자동 수집하여 세션 간 컨텍스트 연속성 보장
- **#89**: Operationalize stable memory retrieval scores in wrapper and fixtures
- **#88**: Expose cost proxy metrics when host token telemetry is unavailable

#### 6️⃣ 에이전트 & Issuer (Closed)
- **#103**: AI가 issuer 에이전트를 우회하고 MCP 도구를 직접 호출하여 이슈 발행
- **#59**: issuer agent: routes to first-match MCP (Plane) even when GitHub remote exists
- **#56**: issuer: 이슈 발행 전 대상 프로젝트 확인 단계 추가
- **#55**: issuer-github.md is an orphaned skill file
- **#47**: analyst.md uses wrong agent discovery path
- **#50**: Support agents missing P44.1 mnemos recall sections

#### 7️⃣ Codex 어댑터 (Closed)
- **#51**: Codex adapter does not write capabilities.json
- **#42**: Codex adapter: missing capabilities.json auto-generation
- **#41**: Codex adapter: missing mnemos-capture-guard PostToolUse hook
- **#40**: Codex agent-crew flow does not enforce mnemos recall/capture
- **#39**: Codex can publish GitHub issues directly when routing required
- **#87**: Clarify Codex adapter capability reports
- **#93**: Reduce Codex policy-only gaps with practical enforcement
- **#67**: Codex routing speed and stabilization follow-ups

#### 8️⃣ 버그 수정 (Closed)
- **#65**: memory capture should tolerate mnemos vault sync push failures
- **#64**: installed smoke-test-state.sh resolves repo root incorrectly
- **#63**: Codex runs can inherit stale Claude capabilities.json
- **#62**: crew:update leaves global Codex agents stale
- **#58**: crew:update `merge_*_to_discovery` does not prune stale files
- **#54**: frontend.md TDD execution phase missing MANDATORY tdd.md read block
- **#53**: planner.md, documenter.md, requirements.md missing MANDATORY enforcement
- **#52**: backend.md skill loading phrasing weaker than standard
- **#48**: backend.md MANDATORY blocks use old relative skill path
- **#45**: crew:update skips installed-but-not-running hosts
- **#43**: supervisor pipeline: reviewer stage auto-add regression

#### 9️⃣ 유틸리티 & 다양한 개선 (Closed)
- **#98**: Ensure issue-solving workflows ingest issue comments before planning
- **#100**: Evaluate monorepo or workspace structure
- **#70**: 프론트엔드/백엔드 에이전트 코드 스타일 규칙 관리
- **#69**: Add shopping dgs-dataloader guidance to prevent DGS/Feign N+1
- **#68**: Research faster parallel processing for agent-crew
- **#75**: Productize Mnemos/evidence quality metrics
- **#74**: Beta hardening: expand user customization preservation matrix
- **#73**: GA readiness: define and enforce cold/remote update latency SLOs
- **#86**: Require telemetry coverage checks
- **#85**: Normalize pipeline state against capability policy
- **#44**: architecture: stage agents lack proactive mnemos search/capture obligation
- **#71**: Phase 3.1 scribe migration re-fires every crew:update
- **#66**: Third beta usability follow-ups

---

## 🔍 주요 패턴 분석

### 상태별 분포
| 상태 | 개수 | 비율 |
|------|------|------|
| 🟢 Open | 2 | 1.6% |
| 🔴 Closed | 126 | 98.4% |

### 라벨별 분류
| 라벨 | 이슈 수 |
|------|--------|
| `enhancement` | 30+ |
| `bug` | 20+ |
| `documentation` | 10+ |
| `migration` | 2 |

### 우선순위별 (제목에서 추출)
| 우선순위 | 설명 | 개수 |
|---------|------|------|
| **P0** | Production-critical | 5 |
| **P1** | High-priority | 2 |
| **P4** | Background/low-priority | 1 |
| **BETA** | Beta testing feedback | 10+ |
| **GA** | General Availability readiness | 10+ |

---

## 🎯 핵심 해결 영역

### 1. 아키텍처 & 철학 (완료)
- ✅ Persistent AI Workforce 비전 정의
- ✅ Workflow-first 아키텍처 방향 수립
- ✅ 역할 기반 실행 계약 아키텍처 정의
- ✅ 지속 가능한 상태 머신 설계

### 2. 품질 보증 시스템 (완료)
- ✅ TDD-first 파이프라인 강제
- ✅ Reviewer 루프 자동화
- ✅ 100% Python 테스트 커버리지
- ✅ GA 품질 게이트 구현

### 3. 메모리 & 연속성 (완료)
- ✅ Mnemos 통합 안정화
- ✅ 메모리 수집/회수 자동화
- ✅ 세션 간 컨텍스트 연속성 보장

### 4. 에이전트 생태계 (완료)
- ✅ issuer 에이전트 라이프사이클 관리 확대
- ✅ 다국어 명령어 정규화
- ✅ 에이전트 발견 경로 통일

### 5. Codex 어댑터 (완료)
- ✅ capabilities.json 자동 생성
- ✅ mnemos recall/capture 강제
- ✅ STOP/ROUTE 훅 처리

---

## ⚠️ 현재 블로킹 이슈

### 1. [#128] P4 백그라운드 TaskList 정리
- **영향:** UX 결함 (완료된 작업이 "pending"으로 표시)
- **해결 우선순위:** 높음 (사용자 가시성)
- **예상 난이도:** 중간

### 2. [#127] Read-only 경로 최적화
- **영향:** 성능 (불필요한 supervisor spawn)
- **해결 우선순위:** 중간 (이미 `crew:agent` 분리됨)
- **예상 난이도:** 낮음

---

## 📈 프로젝트 진행 상황

### 최근 30일 활동
```
├─ 해결된 이슈: 126개 ✅
├─ 오픈 이슈: 2개 ⏳
├─ 병합된 PR: 2개 (61, 60)
└─ 주요 성과:
    ├─ GA 품질 게이트 구현
    ├─ Mnemos 통합 안정화
    ├─ Codex 어댑터 강화
    └─ 다국어 지원 추가
```

### 마일스톤 추이
1. **아키텍처 설계** (Completed)
   - Workflow-first 철학 정립
   - Role-oriented 계약 정의
   - Checkpoint/Resume 시스템 설계

2. **Beta 품질 보증** (Completed)
   - TDD 강제
   - Reviewer 자동화
   - 테스트 커버리지 100%

3. **GA 준비** (Mostly Completed)
   - P0/P1 이슈 해결
   - 호스트 브릿지 완성
   - 릴리스 아티팩트 생성

---

## 🔗 관련 리소스

- **Open Issues Dashboard:** [GitHub Issues](https://github.com/woogiekim/agent-crew/issues)
- **Pull Requests:** [GitHub PRs](https://github.com/woogiekim/agent-crew/pulls)
- **Repository:** [woogiekim/agent-crew](https://github.com/woogiekim/agent-crew)

---

## 📝 노트

- **종료된 이슈 (Closed) 비율이 매우 높음 (98.4%)** → 프로젝트 성숙도 높음
- **최근 핵심 초점:** GA 품질 게이트, Mnemos 통합, 다국어 지원
- **남은 작업:** P4 백그라운드 정리, read-only 최적화 (2개만 오픈)
- **기술 부채:** 거의 해결됨 (Beta 피드백 기반 버그 모두 수정)

---

*이 문서는 자동 생성되었습니다. 최신 정보는 [GitHub Issues 페이지](https://github.com/woogiekim/agent-crew/issues)를 참조하세요.*
