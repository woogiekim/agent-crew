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

## Software Development Three Principles

Apply these three principles to every implementation and review decision:

- **KISS (Keep It Simple, Stupid)** — choose the simplest design that satisfies
  the current requirements, tests, and architecture. Avoid clever control flow,
  speculative framework code, and abstractions that make the change harder to
  read.
- **YAGNI (You Aren't Gonna Need It)** — do not implement future flexibility,
  unused extension points, optional modes, feature flags, caches, adapters, or
  configuration until the current task actually requires them.
- **DRY (Don't Repeat Yourself)** — remove meaningful duplication of knowledge
  or behavior. Do not force premature helpers for incidental similarity; extract
  shared code only when it clarifies the domain rule or reduces real maintenance
  risk.

## DRY Naming

Avoid repeating context that is already supplied by the surrounding class,
interface, module, component, GraphQL type, input type, or field type.

- Service or component methods should name the action, not restate the domain
  already named by the owner. Prefer `reviewMetaService.find(...)` over
  `reviewMetaService.findReviewMetas(...)` when the receiver already gives the
  `ReviewMeta` context.
- Use case interfaces whose name already states the action should use a neutral
  entrypoint such as `execute(...)` or the minimal verb that remains clear.
- Field and input names should avoid restating their type. Prefer
  `statuses: List<ReviewPublicStatus>` over `publicStates:
  List<ReviewPublicStatus>` when the type already supplies the public-status
  context.
- GraphQL input/type fields follow the same rule: the enclosing type and field
  type are part of the call-site context.
- Keep redundant context only when the method or field is part of a public API
  consumed without owner/type context, or when one owner intentionally contains
  multiple domains that need disambiguation.

## Baseline

- Prefer early return, guard clauses, polymorphism, or table-driven dispatch
  over `else` branches in new or modified code.
- Keep one level of indentation per method/function where practical. Extract
  a named helper when a branch, loop, or callback nests another branch or loop.
- Keep the design small enough to explain from the current requirement. If a
  class, helper, CLI flag, adapter, configuration option, or extension hook has
  only a hypothetical future use, remove it until a real requirement appears.
- Consolidate duplicated rules, branching decisions, strings, fixtures, or data
  transformations when the duplication would make future behavior changes
  error-prone. Keep harmless one-off repetition when an abstraction would be
  harder to understand than the repeated code.
- Avoid ternary-heavy or expression-packed control flow when it hides validation
  or error handling. Use named intermediate values or guard clauses instead.
- Keep implementation context changes separated by a blank line. This applies
  across setup, validation, transformation, side effects, error handling,
  rendering, and return/reporting.
- Follow Tell, Don't Ask. Do not pull object state through chains of getters
  to make decisions that belong with the object owning that state.
- Name methods, variables, fields, inputs, and operations by their local
  responsibility. Avoid duplicating context already provided by the class,
  interface, module, component, enclosing schema type, or field type.
- Name behavior by domain action, not implementation mechanics. A method name
  that says what it excludes, applies, nulls, copies, or branches on is often
  describing the implementation instead of the business action. A good call
  site reads like a domain sentence, such as `account.earn(income)`, not
  `account.addIncomedMoney(income)`, when earning is the domain behavior.
- Apply Tell, Don't Ask at responsibility boundaries. This includes asking with
  isX/getX and then branching or mutating elsewhere when the object owning the
  state can make the decision itself; that leaks responsibility out of the
  object that owns the relevant invariant. This does not ban getters for data
  transfer or rendering. Prefer to send an imperative message to that object
  and let it decide from its own state.
- Prefer domain concepts over raw-value comparisons. Convert external input,
  persisted values, and API response values into a meaningful type, value
  object, enum, or named concept before a policy decision whenever the value
  carries business or workflow meaning. Do not compare raw strings, numbers,
  booleans, or nulls when the comparison hides the policy concept being judged.
- Model failure, absence, and valid presence as distinct states. Failure is not
  an empty result, and an empty result is not a valid result. Before converting
  failures into empty results, verify that the fallback does not change a
  policy outcome, contract, audit trail, or caller-visible behavior.
- Do not assign null as policy machinery without contract evidence. When null
  means update exclusion, existing-value preservation, fallback, unspecified,
  or "leave this alone", verify the persistence mapper, serializer, API
  contract, protocol, or comparable source-of-truth first. If null is allowed,
  tests should verify the observable policy result or side effect, not merely
  that a field was set to null inside the implementation.

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
