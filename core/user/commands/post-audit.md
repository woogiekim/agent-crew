---
name: post-audit
kind: review-lens
loaded_by: review-synthesis
lens_id: post-audit
provider: agent-crew
surface: command
read_only: true
mutates: false
requires_mr: none
requires_remote_read: none
requires_supervisor_context: false
default_enabled: true
timeout_seconds: 180
duplicate_group: post-audit
---

# /post-audit - Post-implementation audit

## 방법 비교와 트레이드오프

출력을 작성하기 전에 공통 지침 `core/rules/review-method-comparison.md`를 읽고 적용한다.
설치 환경에서는 `~/.agent-crew/rules/review-method-comparison.md`를 읽는다.
실제 방법명, 채택/권장/판단 보류 구분, 선택 이유, 얻는 점·감수할 점, 빈 줄과
`방법별 비교` 소제목, 후보별 설명·장단점, 확인 근거와 한계를 포함한다.
방법명이나 후보 개수를 고정하지 않는다. 방법 선택이 없는 항목에는 비교를 만들지 않는다.
이 형식은 보고서·분석·계획·인계·반영 노트의 서술에 적용하며, 원문 인용과 원시 증거,
프로토콜 필드, 상태·반영률·승인·실행 경계는 바꾸지 않는다.

## Purpose

Audit an already implemented change and report the missing hardening work before
the operator asks for merge, MR, release, or final closeout. This command is for
finding gaps after implementation, not for doing the implementation itself.

Use this command as a read-mostly quality gate over the current diff, named
files, branch, issue scope, or handoff artifact. It may recommend follow-up
changes, but it must not edit code unless the operator explicitly asks for a
separate fix/implementation run.

## Trigger

- `/post-audit <scope>` or `crew:post-audit <scope>`.
- `$post-audit <scope>` from a host wrapper.
- The user asks for implementation-aftercare, hardening gaps, missed checks, or
  quality audit after a feature, fix, migration, refactor, or review follow-up.

## Skip

- The user is asking for first-pass implementation. Use `crew:run`.
- The user is asking for an independent code review of a branch, path, commit,
  or range. Use the existing review workflow.
- The user is asking for contract parity across systems as the primary goal.
  Use parity-check first, then run post-audit on the implemented follow-up if
  needed.
- There is no implemented change, artifact, branch, or named scope to inspect.
  Report `STATUS: blocked` and ask for the missing target.

## Inputs

- `AUDIT_SCOPE` - current diff, branch, issue key, file path, module, handoff,
  MR note, or free-text scope.
- `PROJECT_ROOT` - repository root for the implemented change.
- `TASK_DIR` - agent-crew task state directory when available.
- `BASE_REF` - optional comparison base. If omitted, infer from local git state
  when safe; otherwise state the assumption.

## Operating Rules

- Keep the pass read-only unless the user explicitly requests follow-up edits.
- Prefer local and offline evidence. Do not push, deploy, merge, publish, or
  mutate external systems.
- Start from the changed surface: diff, touched files, tests, docs, config, and
  generated artifacts.
- Separate facts from assumptions. Mark unknowns as `Unknown`.
- Treat automatic checks and reviewer judgment separately.
- Do not claim a check passed unless the command was actually run or the file
  evidence proves it.
- If the current directory is not a git repository, audit named files and
  provided artifacts only, and report that git diff scope was unavailable.

## Audit Axes

### 1. Architecture Boundaries

Check for layer direction and ownership violations:

- controller/resolver owning domain rules
- service/repository responsibility mixing
- adapter leaking transport concerns into domain/application layers
- reverse dependencies between domain, application, adapter, and infrastructure
- generated artifacts or forbidden project paths changed without explicit scope
- project-specific exclusion rules, such as generated API docs or closed product
  areas, being touched accidentally

Use available local tools when the project supports them, for example detekt,
ktlint, Checkstyle, ArchUnit, dependency analysis, or grep-based boundary
probes. If a tool is not configured, report `not configured` instead of
inventing a result.

### 2. Domain Cohesion and Coupling

Inspect whether the change keeps domain behavior cohesive and coupling low:

- one class or method accumulating unrelated responsibilities
- shared methods changed in a way that affects unrelated phases or legacy paths
- read and write behavior mixed in one path without a deliberate boundary
- duplicated transformation logic that should live in one mapper/adapter
- implicit behavior hidden in flags, nulls, magic strings, or side effects

This axis is heuristic. Report it as `WARN` unless there is direct evidence of a
bug or contract break.

### 3. Test Gaps

Map changed production files to focused tests:

- happy path, empty response, error response, authorization, boundary values
- fallback and exception behavior
- public contract, DTO, routing, serializer, or mapper changes
- parity tests when v1/v2 or upstream/downstream behavior must match
- meaningful test names rather than opaque numbering

If no runnable test harness exists, state the reason and suggest the smallest
manual or static verification substitute.

### 4. Contract Compatibility

Check whether public or downstream-facing contracts changed:

- REST/GraphQL path, method, request, response, nullable, default, enum, or
  error shape
- legacy response status or wrapper semantics such as `result.code`
- fallback behavior, empty model behavior, and no-content normalization
- caller headers, actor propagation, or internal/external endpoint selection
- downstream consumers that may depend on the old shape

Report concrete compatibility risk as `AUTO FAIL` when the implementation
breaks a known contract without an explicit migration plan.

### 5. Authorization and Security

Check for:

- missing admin/user guard on privileged read/write paths
- caller/actor propagation gaps
- internal endpoint exposed through public routes
- sensitive values in logs, exceptions, docs, tests, or fixtures
- authorization failures hidden by broad fallback

Treat missing guard or actor propagation on privileged mutations as `AUTO FAIL`
unless the scope explicitly documents why the path is public.

### 6. Operational Risk

Check for operational diagnosability and runtime safety:

- exceptions swallowed into empty responses without actionable logs
- WARN/ERROR logs missing target id, operation, upstream, status, or cause
- duplicate logging that obscures the real failure
- dev/prod URL, profile, feature flag, property, secret, or host override drift
- loop-internal HTTP/DB calls, N+1 queries, missing pagination, or unbounded load
- retry/fallback behavior that can hide data loss or partial writes

### 7. Documentation and KDoc

Check whether documentation reflects the implemented behavior:

- public API/resolver/controller/port/interface KDoc missing or stale
- comments describing legacy behavior after a route or contract changed
- TODO/FIXME left without owner, condition, or follow-up
- MR/report-ready implementation summary missing material constraints or risks

Do not require decorative comments. Flag documentation gaps only when they would
help future maintainers understand boundary, contract, risk, or operational
behavior.

## Suggested Evidence Collection

Use only commands that fit the local project and scope. Examples:

```bash
git status --short --branch
git diff --name-only
git diff --check
rg -n "TODO|FIXME|deprecated|legacy|fallback|AdminGuard|X-Auth|result.code"
```

For Gradle/Kotlin projects, prefer offline/cache-friendly focused checks when
available:

```bash
./gradlew --offline ktlintCheck detekt test
```

For Maven/Java projects, prefer focused local tests when available:

```bash
mvn -o -Dtest='*ChangedArea*Test' test
```

When a command cannot run offline because dependencies are missing, stop and
report the blocker before switching to network-backed verification.

## Output

Write the audit report in the user's output language. Default user-facing output must be
readable first. Preserve the meaning of must-fix `AUTO FAIL` issues and heuristic `WARN`
items, but render them with natural headings in the default report. Use parser-oriented
section tokens only in an explicit raw/debug mode.

```text
구현 후 점검 결과입니다.

점검 범위: <scope audited>
기준: <base ref, current diff, named files, or unknown>

반드시 고쳐야 할 문제:
- <must-fix issue, or none>

주의가 필요한 항목:
- <review-needed risk, or none>

확인한 내용:
- 변경 표면: <files/modules/contracts checked>
- 실행한 확인: <commands actually run>
- 실행하지 못한 확인: <commands skipped and why>

영향 범위:
- 계약 영향: <none|details>
- 보안 영향: <none|details>
- 운영 영향: <none|details>
- 문서 영향: <none|details>

다음에 무엇을 할까요?

1. 후속 수정 작업으로 진행
2. 보고서만 유지
3. 감사 범위 다시 지정
4. 종료
```

Selection handling:

- `1` must not edit files inside this read-only audit. Return the smallest actionable prompt
  or logical intent for a separate `crew:run` or suitable implementation workflow.
- `2` returns the report only.
- `3` asks for a revised audit scope and reruns the read-only audit.
- `4` stops without further action.

Use ordinary numbered choices such as `1.` and do not use circled digit characters. If an
automation or parser needs machine-oriented output, expose it only in an explicit raw/debug
mode. If that mode is not implemented, keep the default output human-readable.

## Completion

The command completes when it has produced the report above and clearly
separated:

- confirmed automatic failures
- heuristic warnings
- evidence gathered
- checks that were not run
- recommended next actions

If follow-up implementation is required, return the smallest actionable task
prompt for a separate `crew:run` or fix workflow instead of silently editing
inside this audit pass.
