# Skill: code-review

## Purpose
Enables the reviewer agent to systematically verify that an implementation matches the PRD, covers non-functional requirements, and contains no obvious quality or security issues — without modifying any implementation files.

## When to Apply
- As the final stage of every agent pipeline (always spawned by supervisor)
- After any implementation agent (backend, frontend, devops) completes its work
- When the supervisor needs a quality gate before marking a task complete

---

## Delete-First Review Order

Before correctness/style review, check whether the implementation should be
smaller:

1. What can be deleted?
2. What is duplicated?
3. What already exists in the project?
4. What is over-engineered?
5. Which abstraction is unnecessary?
6. Which dependency is unnecessary?
7. Which code can become configuration or platform behavior?

Blocking findings include unnecessary abstractions, generic frameworks,
premature optimization, duplicated configuration, overly flexible APIs,
speculative extensibility, additional layers without measurable value,
unnecessary interfaces, deep inheritance, and god objects.

Every new class must justify single responsibility, net complexity reduction,
inability to reuse/extend existing code, and easier future maintenance. Every
new dependency must justify why existing project code, the standard library,
framework, browser, database, Kubernetes, or platform capabilities are
insufficient.

## Evidence-first reporting

For bug reports, incident analysis, root-cause claims, review verdicts, and
quality-gate decisions, check that the report follows
`core/rules/evidence-grounded-reasoning.md`.

- [ ] Proven Facts are backed by concrete repository, test, log, trace, git, or
      tool-output evidence.
- [ ] Unverified Hypotheses are labeled as hypotheses and kept out of the final
      conclusion.
- [ ] Needed Evidence names the missing file, command, log, test, trace, HAR, or
      runtime check instead of guessing.
- [ ] Conclusion is narrower than the evidence and does not prescribe code
      changes that are still only hypothetical.

## PRD Coverage Matrix

For each item in the PRD's Core Features list, verify whether it is present in the implementation:

```markdown
| PRD Feature | Status | Location |
|---|---|---|
| User can place an order | PRESENT | OrderController, OrderService |
| Order confirmation email sent | MISSING | — |
| Pagination on order list | PRESENT | OrderController#listOrders |
```

Mark any missing feature as a NEEDS_CHANGES finding.

When the current pipeline stage declares assigned `AC-*` identifiers in
`acceptance_criteria`, include those IDs in the coverage check. Mark any
missing assigned `AC-*` as `REVIEW: NEEDS_CHANGES` with
`REASON: spec_incomplete`.

## Two-Stage Review Order

Run review in this order:

1. **Spec compliance** — complete the PRD coverage matrix first. If any required
   acceptance criterion or core feature is missing, return
   `REVIEW: NEEDS_CHANGES` with `REASON: spec_incomplete`. Do not mix polish
   findings into the first loop-back directive.
2. **Code quality** — after spec compliance passes, review maintainability,
   architecture, security, tests, and style. Return `REVIEW: NEEDS_CHANGES` with
   `REASON: code_quality` for blocking code-quality findings.

This ordering keeps implementation loop-backs focused: complete missing
behavior before polishing code that may still need structural changes.

## Re-Review Scope and New Must Policy

Reviewer retries are scoped differently from the first review:

- `verify-prior-must-only`: verify that prior Must findings (`CRITICAL` or
  `IMPORTANT`) were actually fixed, using the prior `context/review.md`,
  `context/finding-register.json`, changed hunks, tests, and verification
  output. Do not convert the retry into a broad new sweep by default.
- `full-rescan`: perform the normal full review from scratch. Use this only on
  the first review or when the operator/supervisor explicitly requests it.

If a re-review in `verify-prior-must-only` discovers a new Must, classify it in
the finding body with exactly one of:

- `regression`: the Must was introduced by the attempted fix.
- `missed_existing`: the Must existed in Round 1 but the reviewer missed it.
- `severity_escalation`: a prior Should/MINOR is now proven blocking by new
  evidence.
- `unclear_requirement`: the requirement is ambiguous enough that continuing
  would risk an incorrect implementation.

Weakly evidenced new findings must remain non-blocking Should/MINOR items.
Evidence must point to first-party files, changed hunks, task artifacts, or
tool output; speculation, style preference, or missing proof of execution is
not enough to create a new Must.

This is a machine-checked contract. In `verify-prior-must-only`, the supervisor
classifies reviewer output through `reviewer-loop-decision.py`; an unclassified
or weakly evidenced new Must becomes `review_contract_invalid` and retries the
reviewer, not the implementer.

---

## Git Diff Analysis

Use git history to scope the review to only what changed in this task:

```bash
git log --oneline -10
git diff HEAD~{n}..HEAD --stat
git diff HEAD~{n}..HEAD -- {file}
```

Prefer `git merge-base` over guessing commit counts:

```bash
BASE=$(git merge-base HEAD main 2>/dev/null || git rev-parse HEAD~1)
git diff "$BASE"..HEAD --stat
git diff "$BASE"..HEAD -- {file}
```

When reporting a finding, include the narrowest useful file and line reference. If a finding is inferred from omitted behavior, name the missing file, test, or artifact.

---

## Security Review — OWASP Top 10 (2021)

(Reference: owasp.org/Top10)

Check the changed code for each applicable risk:

| # | Risk | What to look for |
|---|---|---|
| A01 | Broken Access Control | Missing auth checks on endpoints; IDOR via sequential IDs |
| A02 | Cryptographic Failures | Plaintext secrets, weak hashing (`MD5`/`SHA1` for passwords) |
| A03 | Injection | SQL built via string concat; shell commands with user input |
| A04 | Insecure Design | Missing rate limiting; no abuse-case handling in design |
| A05 | Security Misconfiguration | Default credentials; verbose error stack traces in responses |
| A06 | Vulnerable Components | Newly added deps with known CVEs; unpinned version ranges |
| A07 | Auth & Session Failures | JWT without expiry; session fixation |
| A08 | Software Integrity | Unverified third-party scripts; unsigned artifacts |
| A09 | Logging Failures | Sensitive data (PII, tokens) logged; insufficient audit trail |
| A10 | SSRF | User-controlled URLs fetched server-side without allowlist |

Flag any hit as `CRITICAL`.

---

## Non-Functional Requirements Checklist

### Performance
- [ ] No N+1 query patterns introduced (ORM: check for `LazyInitializationException` risk)
- [ ] Paginated endpoints do not fetch unbounded result sets
- [ ] No synchronous blocking calls inside async/coroutine contexts

### Maintainability
- [ ] No dead code or commented-out blocks committed
- [ ] Naming is clear and consistent with existing codebase conventions
- [ ] No magic numbers — use named constants or enums
- [ ] `core/rules/code-quality.md` is applied to every changed code file,
      regardless of implementation language or file extension. Kotlin examples
      in OOP skills are illustrative, not a scope limit.
- [ ] KISS, YAGNI, and DRY are checked from `core/rules/code-quality.md`.
      Flag needless complexity, speculative future behavior, and meaningful
      duplicated knowledge or behavior.
- [ ] Refactoring guidance from `refactoring-catalog.md` is applied when a diff
      claims cleanup, simplification, review follow-up, or structural
      improvement. Flag refactors that merely shorten code while hiding domain
      intent, collapse failure/absence/presence states, preserve stale
      comments, or create avoidable format churn.
- [ ] DRY Naming is checked. Flag method, field, GraphQL input/type, fixture,
      and helper names that repeat context already supplied by the class,
      interface, module, component, enclosing schema type, or field type unless
      the public API or mixed-domain owner needs disambiguation.
- [ ] Avoidable `else` branches, nested control flow, ternary-heavy
      validation/fallback logic, getter-driven decisions, and names that
      duplicate class/module context are reported in any language.
- [ ] Context changes are separated by blank lines. Flag
      `context_break_missing_blank_line` when validation/reporting is
      immediately followed by early return/throw, setup is immediately followed
      by business logic, side effects are immediately followed by result
      construction/return, or error handling is immediately followed by normal
      flow without a separating blank line.

### Cognitive Complexity
Flag methods with complexity > 15 as a `IMPORTANT`. (Reference: SonarSource "Cognitive Complexity", 2017)

```bash
# Quick proxy: count decision points in a function
grep -c "if\|for\|while\|when\|catch\|\?\." {file}
```

---

## Test Coverage Sanity Check

- Domain behavior coverage comes before code style. Line coverage is not
  sufficient to approve tests.
- For test-writing tasks, inspect `context/test-checklist.md` and
  `context/test-case-mapping.md` before judging the test code itself.
- Confirm checklist-only review is APPROVED in
  `context/test-checklist-review.md`.
- First look for Missing MUST, Missing SHOULD, Duplicate, Low-value Test, and
  Wrong Priority. Style feedback comes after missing domain behavior.
- Every MUST checklist item must have a TC-ID mapped to a concrete test or an
  explicit reviewer-accepted explanation.
- At least one test per new endpoint or public method
- Primary test target variables default to `sut` unless the repository has an
  explicit conflicting convention recorded in the TDD log
- Failing paths (error cases, validation) tested, not only happy paths
- No commented-out test assertions (`//assertThat(...)`)
- Parameterized tests used where multiple similar inputs exist
- For documentation-only or config-only changes: markdown lint, broken-reference check, or schema validation instead of product tests

### Repair-Only Test Check

Review changed tests for repair-only or revert-only tests before approving the
final diff. If a test only proves that a bad intermediate implementation was
reverted, and no durable contract source backs the behavior, mark
`REVIEW: NEEDS_CHANGES` with `REASON: code_quality` and ask for the test to be
removed or converted into evidence.

A durable contract source can be public API behavior, product requirement,
security policy, data rule, legacy parity, or compatibility requirement. When
that source exists, preserve the regression test and require the source to be
visible in the PRD, checklist reason, test-case mapping, test name/docstring,
or task evidence.

For internal repair confidence without a durable contract source, prefer
temporary local checks, focused command output, diff evidence, or task-context
notes instead of permanent tests.

## Documentation Integration Review

Treat documentation synchronization as part of CI, not as optional polish. For
each diff, compare the PRD and handoff `doc_impact` entry with the changed files
and the public/domain surface of the task.

Return `REVIEW: NEEDS_CHANGES` with `REASON: documentation_ci_missing` when any
of these are true:

- Public behavior, CLI/API/UI usage, setup/update/deploy flow, domain language,
  architecture, or long-lived agent guidance changed but no tracked doc,
  side-car doc, or external-sync evidence was updated.
- The PRD marks `documentation_ci_required: true` but the diff and task
  artifacts do not name synchronized documentation targets.
- The PRD omits `doc_impact` for a change whose impact is visible to future
  operators, agents, or domain readers.
- Documentation is intentionally unchanged but there is no reviewable
  `doc_impact: none` rationale.

For severity, missing documentation synchronization is an IMPORTANT finding
unless it hides a safety, setup, migration, or security change; escalate those
to CRITICAL. Acceptable evidence includes tracked markdown changes,
`{TASK_DIR}/result.md`, side-car README/CHANGELOG drafts, external backend sync
logs, or an explicit no-impact rationale.

---

## Conventional Commits Verification

(Reference: conventionalcommits.org)

Check that new commits follow the format:
```
<type>(<scope>): <description>

Types: feat | fix | docs | style | refactor | test | chore | perf | ci
```

Flag non-conforming commit messages as `MINOR`.

---

## Anti-Pattern Reference

Flag the following as `IMPORTANT` or `CRITICAL` depending on context:

| Anti-pattern | Severity | Fix |
|---|---|---|
| God class (> 300 lines, > 10 methods) | IMPORTANT | Split by SRP |
| Feature envy (method uses another class's data more than its own) | IMPORTANT | Move method |
| Primitive obsession (raw `String` for domain concepts) | IMPORTANT | Wrap in Value Object |
| Anemic domain model (entity is a data bag; logic in service) | IMPORTANT | Move logic to entity |
| Hardcoded configuration (URLs, timeouts, credentials) | CRITICAL | Move to env / config |
| Catch-all exception handler swallowing errors | CRITICAL | Narrow the catch clause |

---

## Review Report Format

Write findings to `{TASK_DIR}/context/review.md`:

```markdown
# Review: {task name}

## Status
APPROVED | NEEDS_CHANGES

## Coverage
- [x] {feature}: implemented at {path}
- [ ] {feature}: missing — {reason}

## Issues
- [CRITICAL] {description} — {file:line}
- [IMPORTANT] {description} — {file:line}
- [MINOR] {description}

## Recommendation
{next step if NEEDS_CHANGES, or "Ready to merge." if APPROVED}
```

### Issue Severity Classification

| Severity | Meaning | Blocks merge? |
|---|---|---|
| `CRITICAL` | Missing feature, security hole, broken test | Yes |
| `IMPORTANT` | Style, naming, minor gap that should still block merge | Yes |
| `MINOR` | Informational observation or low-impact polish | No — auto-promoted to `deferred-minor` |

`CRITICAL` and `IMPORTANT` both trigger the reviewer's
`REVIEW: NEEDS_CHANGES` verdict. `MINOR` does NOT block merge — when the
only findings in a review are `MINOR`, the reviewer auto-promotes each one
into `finding-register.json` with `status: deferred-minor` and emits
`REVIEW: APPROVED` plus a `MINOR_DEFERRED: <count> ids=<...>` annotation
so the supervisor can carry the deferred items forward in `handoff.md`.
See `core/agents/reviewer.md` § Step 4.5 for the upsert flow and
`core/rules/quality-loop.md` § Confirmed Finding Register for the
terminal-status contract.

---

## Checklist
- [ ] `{TASK_DIR}/context/prd.md` read before starting review
- [ ] Git diff analyzed from merge-base or task commit range
- [ ] PRD coverage matrix completed for all Core Features
- [ ] OWASP Top 10 risks checked for applicable items
- [ ] Non-functional requirements checked (security, performance, maintainability)
- [ ] Cognitive complexity checked for new/changed methods
- [ ] Context-break blank line rule checked for new/changed code
- [ ] Conventional Commits format verified
- [ ] Tests or risk-appropriate validation checks verified
- [ ] Documentation Integration Review completed; doc targets or
      `doc_impact: none` rationale verified
- [ ] Anti-pattern scan completed
- [ ] `{TASK_DIR}/context/review.md` written with status, coverage, issues, and recommendation
- [ ] No implementation files modified
- [ ] Return value within 4 lines
