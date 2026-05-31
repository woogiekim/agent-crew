---
name: backend-kotlin-spring
description: >
  Adapter skill for the `backend` dispatcher (Wave B exemplar). Loaded when
  the dispatcher detects a Kotlin + Spring Boot manifest (`build.gradle.kts`,
  `build.gradle`). Captures the Kotlin/Spring/JUnit 5/MockK/Gradle stack
  contract that the framework's backend agent has historically embedded
  inline, now extracted into a Channel B seed template per
  `core/rules/agent-tool-dispatch.md`.
loaded_by: backend
axis: kotlin-spring
detection: build.gradle.kts OR build.gradle (with kotlin / kotlin-spring plugin)
---

# backend-kotlin-spring — Adapter Skill

This skill is the **Channel B seed template** for the `backend` dispatcher
when the detected manifest axis is `kotlin-spring`. It is faithfully
re-packaged from the canonical Kotlin/Spring + TDD/DDD content that
`core/agents/backend.md` documented prior to the Wave B refactor — see
`core/rules/agent-tool-dispatch.md` § Channel B template seeding for the
runtime contract (`crew:setup` copy-if-absent; never overwrites a user
edit).

## Tech Stack

- **Language**: Kotlin
- **Framework**: Spring Boot
- **Test**: JUnit 5 + MockK
- **Build**: Gradle (`./gradlew test`)

## TDD Cycle (RED → GREEN → REFACTOR)

The backend agent's TDD contract is non-negotiable. For each behaviour
unit, execute the full cycle:

```text
RED      → Write failing test file → ./gradlew test → confirm failure (test MUST fail at this step)
GREEN    → Write minimal implementation → ./gradlew test → confirm pass
REFACTOR → Remove duplication, improve design → ./gradlew test → confirm still passes
```

**Test-first enforcement (non-negotiable):**
- Write the failing test FIRST. Implementation code MUST NOT be written
  until a failing test exists and has been confirmed to fail.
- Every new class or function MUST have a corresponding test file before
  the implementation file is created.
- Test files MUST be committed in the same commit as the implementation
  they cover.

## Test File Naming Convention

| Test type | Filename pattern |
|---|---|
| Unit test | `{ClassName}Test.kt` |
| Integration test | `{ClassName}IntegrationTest.kt` |

**Test target naming convention**: default the class, service, function
wrapper, repository adapter, or other primary system under test variable
to `sut`. Keep collaborators, inputs, expected values, and results
domain-specific.

**Minimum test coverage per cycle**: happy path + at least one
failure/edge case.

## Coverage Gate

**100% changed executable coverage**. Every new or modified public
method, branch, domain rule, endpoint behavior, and documented failure
mode must be covered by an automated test or listed as a narrow
exception in `{TASK_DIR}/context/test-coverage.md`.

## DDD Tactical Patterns

When implementing domain logic, design the model around DDD tactical
patterns:

- **Aggregate Root** — the consistency boundary; the only entry point
  for state mutation within the aggregate.
- **Entity** — has identity that persists across state changes.
- **Value Object** — defined entirely by its attributes; immutable.
- **Domain Event** — a record of something that happened in the domain;
  emitted by aggregate state transitions.

For complex aggregates or multiple bounded contexts, also consult
`~/.agent-crew/system/agents/skills/domain-driven-design.md` for the
full pattern set (Repository, Factory, Anti-Corruption Layer, etc.).

## Object Calisthenics + Tell, Don't Ask (Kotlin flavor)

The Kotlin/Spring stack enforces Object Calisthenics + Tell, Don't Ask
as code-style invariants. The most-cited constraints:

- **No `else`** (Object Calisthenics rule #2) — favor early-return /
  guard-style control flow.
- **No getter-based decision logic** (Tell, Don't Ask) — let the object
  decide; don't pull state out to decide externally.
- **Every public method must be covered by at least one test.**

These rules are language-agnostic in spirit; their framework-level
authority lives in `~/.agent-crew/system/agents/skills/oop-principles.md`
(which the backend dispatcher loads via the declared on-demand
mechanism). This template captures the Kotlin/Spring-flavored phrasing
the agent uses when applying them.

## Commit Conventions

- `git commit` is the closing step of every TDD cycle (post-REFACTOR).
- A commit containing only implementation files (no tests) is a
  pipeline violation and MUST be rejected.
- The commit MUST include both test files and implementation files.
- All tests must be GREEN (`./gradlew test`) before commit.

## Verification Checklist (before STATUS: completed)

- [ ] Every new/modified class has a corresponding test file
- [ ] All tests ran and are GREEN (`./gradlew test`)
- [ ] 100% changed executable coverage is satisfied or every exception
      is narrowly justified in `{TASK_DIR}/context/test-coverage.md`
- [ ] Object Calisthenics — no violations
- [ ] Tell, Don't Ask — followed
- [ ] DDD tactical patterns — applied correctly
- [ ] `{TASK_DIR}/context/tdd_log.md` updated with all TDD cycles

If no test framework is available in the project, halt and report
BLOCKED — do not implement without tests.

## Layered Architecture Notes (Spring Boot specific)

When crossing layer boundaries (controller → service → repository),
apply the Dependency Rule and port/adapter pattern from
`~/.agent-crew/system/agents/skills/clean-architecture.md`. In a Spring
Boot codebase, this typically means:

- Controllers depend on application services via constructor injection.
- Application services depend on repository interfaces (ports), not
  Spring Data repositories (adapters).
- DTOs are the transport boundary; domain models do not leak into the
  API layer.

## DGS / Feign / GraphQL DataLoader Notes

When the Kotlin/Spring project uses Netflix DGS, GraphQL field
resolvers, Feign clients, or downstream HTTP enrichment for list /
nested fields, additionally consult
`~/.agent-crew/system/agents/skills/dgs-dataloader.md` before designing
resolver or service changes. The skill defines DataLoader batching,
request-scoped cache boundaries, and call-count verification required
to prevent DGS/Feign N+1 regressions.

## See also

- `core/agents/backend.md` — the dispatcher that loads this skill when
  the kotlin-spring axis is resolved.
- `core/rules/agent-tool-dispatch.md` — the 5-step dispatch protocol,
  naming convention, and Channel B template seeding contract.
- `~/.agent-crew/system/agents/skills/tdd.md` — the language-agnostic
  TDD cycle (declared on-demand load).
- `~/.agent-crew/system/agents/skills/effective-kotlin.md` — Kotlin
  language best practices (declared on-demand load).
- `~/.agent-crew/system/agents/skills/oop-principles.md` — Object
  Calisthenics + Tell, Don't Ask rules (declared on-demand load).
