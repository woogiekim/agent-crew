# Skill: git-workflow

## Purpose
Enables all agents to follow consistent branching, committing, and review practices — minimizing merge conflicts, keeping history clean, and enabling safe continuous delivery.

## When to Apply
- Before creating any branch or making the first commit on a task
- When writing a commit message
- When preparing a pull request
- When deciding how to integrate a feature branch into main

---

## Trunk-Based Development (Paul Hamant, "Trunk Based Development", trunkbaseddevelopment.com)

The recommended branching model for teams practicing CI/CD.

**Core rule**: Developers integrate to `main` (trunk) at least once per day. Feature branches are short-lived (< 2 days).

```
main ────●────●────●────●────●─────────► (always deployable)
          \  /      \  /      \   /
        feat/A    feat/B    feat/C
        (hours)   (hours)   (1 day)
```

**vs Gitflow** (for reference, not recommended for CI/CD):
| Aspect | Trunk-Based | Gitflow |
|---|---|---|
| Integration frequency | Daily | Per feature (days-weeks) |
| Merge conflict risk | Low | High |
| Release complexity | Low | High |
| Best for | Continuous delivery | Scheduled releases |

---

## Branch Naming

(Reference: `core/rules/branch-naming.md`)

```
{type}/{slug}

Types:
  feat     — new or improved product behavior
  fix      — bug fix
  docs     — documentation only
  refactor — restructuring without behavior change
  test     — test-only changes
  chore    — build, deps, setup, CI, tooling, maintenance
```

```bash
feat/add-order-cancellation
fix/order-status-race-condition
docs/api-design-guide
refactor/extract-payment-domain
chore/upgrade-spring-boot-3.2
```

**Rules:**
- Lowercase, hyphens only, no spaces or special characters
- Slug derived from task description; max 48 characters
- No generic names: `fix/bug`, `feat/feature`, `my-branch`

---

## Conventional Commits (conventionalcommits.org)

Structured commit messages enable automated changelog generation, semantic versioning bumps, and clear history.

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

```
feat(order): add order cancellation flow

Customers can now cancel orders in PENDING or CONFIRMED status.
Orders in SHIPPED status cannot be cancelled.

BREAKING CHANGE: OrderStatus enum gains CANCELLED variant — existing
switch statements must handle the new case.

Closes #142
```

### Types

| Type | When | SemVer bump |
|---|---|---|
| `feat` | New user-facing feature | MINOR |
| `fix` | Bug fix | PATCH |
| `docs` | Documentation only | — |
| `refactor` | Code restructuring, no behavior change | — |
| `test` | Add or fix tests | — |
| `chore` | Build, deps, CI, tooling | — |
| `perf` | Performance improvement | PATCH |
| `ci` | CI/CD pipeline changes | — |
| `BREAKING CHANGE` | Footer or `!` after type | MAJOR |

### Commit message rules
- Description: imperative mood, lowercase, no period ("add cancellation" not "Added cancellation.")
- Body: wrap at 72 characters; explain **why**, not what
- Footer: reference issues (`Closes #N`), breaking changes

---

## Feature Flags — Ship Code Before It's Ready

(Reference: Martin Fowler, "Feature Toggles", 2016)

Feature flags decouple **deployment** from **release**. Code ships to production behind a flag; the flag enables the feature when ready.

```kotlin
// Flag evaluation at runtime
@Component
class FeatureFlags(private val flagService: FlagService) {
    val orderCancellationEnabled: Boolean
        get() = flagService.isEnabled("order-cancellation")
}

// Controller gated by flag
@PostMapping("/orders/{id}/cancel")
fun cancelOrder(@PathVariable id: UUID): ResponseEntity<*> {
    if (!featureFlags.orderCancellationEnabled) {
        return ResponseEntity.status(404).build<Any>()  // hidden, not disabled
    }
    return orderService.cancel(OrderId(id)).fold(
        ifLeft  = { ResponseEntity.status(422).body(it) },
        ifRight = { ResponseEntity.ok(it) }
    )
}
```

**Flag types:**

| Type | Purpose | Lifetime |
|---|---|---|
| Release flag | Hide incomplete feature | Days–weeks; delete after release |
| Experiment flag | A/B test | Duration of experiment |
| Ops flag | Kill switch for production incidents | Indefinite; document in runbook |
| Permission flag | Gradual rollout (10% → 50% → 100%) | Until full rollout |

**Rule:** delete release flags within 1 sprint of full rollout. Accumulating dead flags is a maintenance burden.

---

## Pull Request Standards

(Reference: GitHub Flow; Google Engineering Practices — Code Review)

### PR size
- Target: < 400 lines changed (excluding generated code and lock files)
- One PR = one logical change; if it needs more, split by concern
- Stacked PRs for dependent changes

### PR description template

```markdown
## Summary
- What changed and why (not what the code does)
- Link to issue / task: Closes #N

## Test plan
- [ ] Unit tests added/updated for new behaviour
- [ ] Integration test covers the happy path
- [ ] Edge cases tested: {list them}
- [ ] Manual test: {steps to verify in a browser or via curl}

## Checklist
- [ ] No TODO comments left in code
- [ ] DB migration backward-compatible (no locks on large tables)
- [ ] Feature flag added if feature not ready for all users
```

### Review SLAs (Google Code Review Guidelines)
- Author responds to comments within 1 business day
- Reviewer completes first pass within 1 business day of PR creation
- Blocking comments must be resolved before merge; non-blocking comments noted and may be addressed in follow-up

---

## Commit Hygiene

```bash
# Amend last commit (before push) — fix typo in message or add forgotten file
git add forgotten-file.kt
git commit --amend --no-edit

# Interactive rebase — squash, reorder, or edit commits before PR (before push)
git rebase -i main

# Never amend or force-push after PR review has started
# Never rewrite history on shared branches (main, develop)

# Fixup commit — squash into previous commit on review
git commit --fixup HEAD~1
git rebase -i --autosquash main
```

### Commit atomicity rule
One commit = one logical change. Each commit should:
- Pass the test suite independently
- Be understandable in isolation from the commit message alone
- Not combine unrelated changes (e.g., bug fix + refactor)

---

## Merge Strategy

| Strategy | Command | When |
|---|---|---|
| **Merge commit** (recommended) | `git merge --no-ff` | Default; preserves branch history |
| **Squash merge** | `git merge --squash` | Noisy WIP commits on branch; clean single commit on main |
| **Rebase + merge** | `git rebase main && git merge --ff` | Clean linear history; branch < 5 commits |

**Rule:** always use `--no-ff` for feature branches on `main` — it preserves the context that a group of commits belongs to a feature, even when merging a single commit.

---

## Git Hooks (local)

```bash
# .git/hooks/commit-msg — enforce Conventional Commits format
#!/bin/sh
MSG=$(cat "$1")
PATTERN="^(feat|fix|docs|style|refactor|test|chore|perf|ci)(\(.+\))?: .{1,72}"
if ! echo "$MSG" | grep -qE "$PATTERN"; then
  echo "ERROR: Commit message must follow Conventional Commits format."
  echo "  Example: feat(order): add cancellation flow"
  exit 1
fi
```

```bash
# .git/hooks/pre-push — run tests before push
#!/bin/sh
./gradlew test --quiet || { echo "Tests failed. Push aborted."; exit 1; }
```

Install with: `chmod +x .git/hooks/commit-msg .git/hooks/pre-push`

---

## Checklist
- [ ] Branch name follows `{type}/{slug}` convention
- [ ] Commits follow Conventional Commits format (imperative, lowercase, no period)
- [ ] Each commit is atomic — one logical change, passes tests independently
- [ ] No debug code, TODO comments, or commented-out blocks committed
- [ ] Feature flag added if feature is not ready for all users
- [ ] PR < 400 lines changed; split if larger
- [ ] PR description includes summary, test plan, and checklist
- [ ] DB migrations backward-compatible (no table locks on large tables)
- [ ] `git merge --no-ff` used for feature branch integration to main
- [ ] Local git hooks installed: `commit-msg` (format) and `pre-push` (tests)
