---
name: backend-java-spring
description: >
  Adapter skill for the `backend` dispatcher. Loaded when the dispatcher
  detects a Java + Spring Boot manifest (`pom.xml`, `build.gradle`, or
  `build.gradle.kts`). Captures the Java/Spring/JUnit/Mockito stack contract
  that Java Spring backend tasks require.
loaded_by: backend
axis: java-spring
detection: pom.xml AND spring-boot-starter-parent OR pom.xml AND spring-boot-dependencies OR pom.xml AND org.springframework.boot OR build.gradle AND id.java AND org.springframework.boot OR build.gradle.kts AND id.java AND org.springframework.boot OR build.gradle.kts AND plugins.java AND org.springframework.boot
---

# backend-java-spring - Adapter Skill

This skill is the Channel B seed template for the `backend` dispatcher when
the detected manifest axis is `java-spring`. It supplies the Java/Spring Boot
runtime contract while the backend dispatcher continues to own the generic
TDD, DDD, and quality workflow.

## Tech Stack

- **Language**: Java
- **Framework**: Spring Boot
- **Test**: JUnit 5 + Mockito
- **Build**: Maven (`mvn test`) or Gradle (`./gradlew test`), according to
  the project manifest.

## Mixed Java/Kotlin Spring Projects

Kotlin and Java may coexist in the same JVM Spring service. This skill applies
to Java source, Java tests, and Java-specific tooling only. If a project also
exposes Kotlin language evidence, the dispatcher may load
`backend-kotlin-spring` as a parallel language adapter; keep Mockito/MockK and
`.java`/`.kt` guidance scoped to the files being changed.

## TDD Cycle (RED -> GREEN -> REFACTOR)

The backend agent's TDD contract is non-negotiable. For each behavior unit,
execute the full cycle using the project test command:

```text
RED      -> Write failing test file -> mvn test or ./gradlew test -> confirm failure (test MUST fail at this step)
GREEN    -> Write minimal implementation -> mvn test or ./gradlew test -> confirm pass
REFACTOR -> Remove duplication, improve design -> mvn test or ./gradlew test -> confirm still passes
```

**Test-first enforcement (non-negotiable):**
- Write the failing test FIRST. Implementation code MUST NOT be written until a
  failing test exists and has been confirmed to fail.
- Every new class or function MUST have a corresponding test file before the
  implementation file is created.
- Test files MUST be committed in the same commit as the implementation they
  cover.

## Test File Naming Convention

| Test type | Filename pattern |
|---|---|
| Unit test | `{ClassName}Test.java` |
| Integration test | `{ClassName}IntegrationTest.java` |

## Test Case Name Convention

Test case names follow the language-agnostic nature prefix contract from
`tdd.md`: `<nature-prefix>[(<qualifier>)] - <behavior>`.

Java/JUnit examples:

```java
@DisplayName("success-case - saves author byline and profile in one transaction")
@Test
void savesAuthorBylineAndProfile() {
}

@DisplayName("failure-case(propagation-rollback) - rolls back byline insert when profile write fails")
@Test
void rollsBackBylineInsertWhenProfileWriteFails() {
}
```

**Test target naming convention**: default the class, service, controller,
repository adapter, or other primary system under test variable to `sut`.
Keep collaborators, inputs, expected values, and results domain-specific.

**Minimum test coverage per cycle**: happy path + at least one failure or edge
case.

## Coverage Gate

**100% changed executable coverage**. Every new or modified public method,
branch, domain rule, endpoint behavior, and documented failure mode must be
covered by an automated test or listed as a narrow exception in
`{TASK_DIR}/context/test-coverage.md`.

## DDD Tactical Patterns

When implementing domain logic, design the model around DDD tactical patterns:

- **Aggregate Root** - the consistency boundary; the only entry point for
  state mutation within the aggregate.
- **Entity** - has identity that persists across state changes.
- **Value Object** - defined entirely by its attributes; immutable.
- **Domain Event** - a record of something that happened in the domain.

For complex aggregates or multiple bounded contexts, also consult
`~/.agent-crew/system/agents/skills/domain-driven-design.md` for the full
pattern set.

## Object Calisthenics + Tell, Don't Ask (Java flavor)

The Java/Spring stack enforces Object Calisthenics + Tell, Don't Ask as
code-style invariants. The most-cited constraints:

- **No `else`** (Object Calisthenics rule #2) - favor early-return /
  guard-style control flow.
- **No getter-based decision logic** (Tell, Don't Ask) - let the object decide;
  do not pull state out to decide externally.
- **Every public method must be covered by at least one test.**
- Prefer constructor injection for Spring beans; avoid field injection.
- Prefer interfaces for ports and concrete classes for adapters.

These rules are language-agnostic in spirit; their framework-level authority
lives in `~/.agent-crew/system/agents/skills/oop-principles.md`, which the
backend dispatcher loads through the declared agent-associated skill contract.

## Commit Conventions

- `git commit` is the closing step of every TDD cycle (post-REFACTOR).
- A commit containing only implementation files (no tests) is a pipeline
  violation and MUST be rejected.
- The commit MUST include both test files and implementation files.
- All tests must be GREEN with the project test command (`mvn test` or
  `./gradlew test`) before commit.

## Verification Checklist (before STATUS: completed)

- [ ] Every new/modified class has a corresponding test file
- [ ] All tests ran and are GREEN with the project test command (`mvn test` or
      `./gradlew test`)
- [ ] 100% changed executable coverage is satisfied or every exception is
      narrowly justified in `{TASK_DIR}/context/test-coverage.md`
- [ ] Object Calisthenics - no violations
- [ ] Tell, Don't Ask - followed
- [ ] DDD tactical patterns - applied correctly
- [ ] `{TASK_DIR}/context/tdd_log.md` updated with all TDD cycles

If no test framework is available in the project, halt and report BLOCKED -
do not implement without tests.

## Layered Architecture Notes (Spring Boot specific)

When crossing layer boundaries (controller -> service -> repository), apply the
Dependency Rule and port/adapter pattern from
`~/.agent-crew/system/agents/skills/clean-architecture.md`. In a Spring Boot
codebase, this typically means:

- Controllers are thin request/response adapters.
- Controllers depend on application services via constructor injection.
- Application services depend on repository interfaces or mapper/repository
  ports, not concrete infrastructure when a port boundary exists.
- DTOs are the transport boundary; domain models do not leak into the API layer.
- Repository adapters translate persistence exceptions at the boundary.

## Legacy Spring MVC / WAR Notes

Some Java Spring projects are Maven WAR applications or older Spring Boot 2.x /
Java 8 codebases. Preserve the project's existing test harness and dependency
style:

- Use the existing Maven profile or module command when the repo documents one.
- Do not introduce JUnit 5 or Mockito upgrades unless the task explicitly
  requires dependency migration.
- If the project uses JUnit 4, run the existing Maven test target and preserve
  existing test style.
- Keep controller changes minimal and compatible with current Spring MVC
  annotations and request binding.

## See also

- `core/agents/backend.md` - the dispatcher that loads this skill when the
  java-spring axis is resolved.
- `core/rules/agent-tool-dispatch.md` - the 5-step dispatch protocol, naming
  convention, and Channel B template seeding contract.
- `~/.agent-crew/system/agents/skills/tdd.md` - the language-agnostic TDD
  cycle.
- `~/.agent-crew/system/agents/skills/effective-java.md` - Java language best
  practices.
- `~/.agent-crew/system/agents/skills/oop-principles.md` - Object
  Calisthenics + Tell, Don't Ask rules.
