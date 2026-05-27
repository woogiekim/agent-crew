# Skill: code-review

## Purpose
Enables the reviewer agent to systematically verify that an implementation matches the PRD, covers non-functional requirements, and contains no obvious quality or security issues — without modifying any implementation files.

## When to Apply
- As the final stage of every agent pipeline (always spawned by supervisor)
- After any implementation agent (backend, frontend, devops) completes its work
- When the supervisor needs a quality gate before marking a task complete

---

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

Flag any hit as `BLOCKER`.

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
Flag methods with complexity > 15 as a WARNING. (Reference: SonarSource "Cognitive Complexity", 2017)

```bash
# Quick proxy: count decision points in a function
grep -c "if\|for\|while\|when\|catch\|\?\." {file}
```

---

## Test Coverage Sanity Check

- At least one test per new endpoint or public method
- Primary test target variables default to `sut` unless the repository has an
  explicit conflicting convention recorded in the TDD log
- Failing paths (error cases, validation) tested, not only happy paths
- No commented-out test assertions (`//assertThat(...)`)
- Parameterized tests used where multiple similar inputs exist
- For documentation-only or config-only changes: markdown lint, broken-reference check, or schema validation instead of product tests

---

## Conventional Commits Verification

(Reference: conventionalcommits.org)

Check that new commits follow the format:
```
<type>(<scope>): <description>

Types: feat | fix | docs | style | refactor | test | chore | perf | ci
```

Flag non-conforming commit messages as `NOTE`.

---

## Anti-Pattern Reference

Flag the following as `WARNING` or `BLOCKER` depending on context:

| Anti-pattern | Severity | Fix |
|---|---|---|
| God class (> 300 lines, > 10 methods) | WARNING | Split by SRP |
| Feature envy (method uses another class's data more than its own) | WARNING | Move method |
| Primitive obsession (raw `String` for domain concepts) | WARNING | Wrap in Value Object |
| Anemic domain model (entity is a data bag; logic in service) | WARNING | Move logic to entity |
| Hardcoded configuration (URLs, timeouts, credentials) | BLOCKER | Move to env / config |
| Catch-all exception handler swallowing errors | BLOCKER | Narrow the catch clause |

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
- [BLOCKER] {description} — {file:line}
- [WARNING] {description} — {file:line}
- [NOTE] {description}

## Recommendation
{next step if NEEDS_CHANGES, or "Ready to merge." if APPROVED}
```

### Issue Severity Classification

| Severity | Meaning | Blocks merge? |
|---|---|---|
| `BLOCKER` | Missing feature, security hole, broken test | Yes |
| `WARNING` | Style, naming, minor gap | No (but should fix soon) |
| `NOTE` | Informational observation | No |

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
- [ ] Anti-pattern scan completed
- [ ] `{TASK_DIR}/context/review.md` written with status, coverage, issues, and recommendation
- [ ] No implementation files modified
- [ ] Return value within 4 lines
