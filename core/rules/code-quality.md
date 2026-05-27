# Code Quality Rules

These rules apply to all code written by agent-crew agents, regardless of
language, file extension, framework, runtime, or host adapter. Language-specific
skills may add stricter guidance, but they do not narrow this baseline.

## Scope

Apply this rule to every code file the agent writes or directly touches,
including Kotlin, Java, JSP/JSPF, TypeScript, JavaScript, Python, Go, Rust,
Ruby, Shell, SQL, Groovy, Scala, Swift, PHP, C/C++, C#, Dart, Vue, Svelte, XML,
YAML, and comparable text-based source files.

Kotlin examples in older skill files are illustrative. The principles are not
Kotlin-only.

## Baseline

- Prefer early return, guard clauses, polymorphism, or table-driven dispatch
  over `else` branches in new or modified code.
- Keep one level of indentation per method/function where practical. Extract
  a named helper when a branch, loop, or callback nests another branch or loop.
- Avoid ternary-heavy or expression-packed control flow when it hides validation
  or error handling. Use named intermediate values or guard clauses instead.
- Keep implementation context changes separated by a blank line. This applies
  across setup, validation, transformation, side effects, error handling,
  rendering, and return/reporting.
- Follow Tell, Don't Ask. Do not pull object state through chains of getters
  to make decisions that belong with the object owning that state.
- Name methods and variables by their local responsibility. Avoid duplicating
  context already provided by the class, module, or component name.

## Language Notes

- `elif` and `else if` are not a free pass. They are acceptable only when the
  language or framework makes a guard-clause/table-driven form less clear.
- Python conditional expressions, Java/Kotlin/JS ternaries, shell `case`, and
  pattern matching should remain small, local, and obvious. If they contain
  validation, fallback, or branching side effects, prefer explicit statements.
- Test code may use shape-focused setup branches where that keeps fixtures
  readable, but production control flow should still follow the baseline.

## Review Requirement

Reviewer agents must apply this rule to changed code without filtering by
language. If a violation appears outside Kotlin, report it with the same weight
as a Kotlin violation.
