# Skill: code-review

## Purpose
Enables the reviewer agent to systematically verify that an implementation matches the PRD, covers non-functional requirements, and contains no obvious quality or security issues — without modifying any implementation files.

## When to Apply
- As the final stage of every agent pipeline (always spawned by task-runner)
- After any implementation agent (backend, frontend, devops) completes its work
- When the task-runner needs a quality gate before marking a task complete

## Techniques

### PRD Coverage Matrix
For each item in the PRD's Core Features list, verify whether it is present in the implementation:

```markdown
| PRD Feature | Status | Location |
|---|---|---|
| User can place an order | PRESENT | OrderController, OrderService |
| Order confirmation email sent | MISSING | — |
| Pagination on order list | PRESENT | OrderController#listOrders |
```

Mark any missing feature as a NEEDS_CHANGES finding.

### Git Diff Analysis
Use git history to scope the review to only what changed in this task:

```bash
git log --oneline -10
git diff HEAD~{n}..HEAD --stat
git diff HEAD~{n}..HEAD -- {file}
```

Focus review effort on changed files. Do not re-review stable, unchanged code.

### Non-Functional Requirements Checklist
After feature coverage, check non-functional requirements from the PRD:

**Security:**
- [ ] No secrets, credentials, or API keys in source files
- [ ] Input validation present on all public-facing endpoints
- [ ] Authentication and authorization enforced where required

**Performance:**
- [ ] No N+1 query patterns introduced
- [ ] Paginated endpoints do not fetch unbounded result sets

**Maintainability:**
- [ ] No dead code or commented-out blocks committed
- [ ] Naming is clear and consistent with existing codebase conventions

### Test Coverage Sanity Check
Verify that tests exist for the implementation:
- At least one test per new endpoint or component
- Failing paths (error cases) are tested, not just happy paths
- No commented-out test assertions

### Review Report Format
Write findings to `{TASK_DIR}/context/review.md` using this template:

```markdown
# Review: {task name}

## Status
APPROVED | NEEDS_CHANGES

## Coverage
- [x] {feature}: implemented at {path}
- [ ] {feature}: missing — {reason}

## Issues
- {issue description} — {file:line if applicable}

## Recommendation
{next step if NEEDS_CHANGES, or "Ready to merge." if APPROVED}
```

### Issue Severity Classification
When listing issues, classify by severity to help the caller prioritize:
- `BLOCKER` — must fix before merge (missing feature, security hole, broken test)
- `WARNING` — should fix but does not block merge (style, naming, minor gap)
- `NOTE` — informational observation, no action required

## Checklist
- [ ] `{TASK_DIR}/context/prd.md` read before starting review
- [ ] Git diff analyzed to scope review to changed files only
- [ ] PRD coverage matrix completed for all Core Features
- [ ] Non-functional requirements checked (security, performance, maintainability)
- [ ] Test coverage verified (tests exist, error paths covered)
- [ ] `{TASK_DIR}/context/review.md` written with status, coverage, issues, and recommendation
- [ ] No implementation files modified
- [ ] Return value within 4 lines
