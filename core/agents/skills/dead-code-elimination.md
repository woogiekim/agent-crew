---
name: dead-code-elimination
description: Identify and safely remove unreachable, unused, or stale code paths.
loaded_by: backend,frontend,reviewer
axis: code-cleanup
profile_type: review-policy
detection: cleanup|refactor|dead.code|dead-code|unused|remove.code|delete.code|stale.code
---

# Skill: dead-code-elimination

## Source
- Martin Fowler, *Refactoring*, 2nd ed. — "Remove Dead Code" refactoring.
- Robert C. Martin, *Clean Code*, ch. 17 "Smells and Heuristics" — G9 "Dead Code".

## When to Apply
- The task description contains keywords like `cleanup`, `refactor`,
  `dead code`, `unused`, or `remove`.
- A code review surfaces unreachable branches, unused functions, or
  imports that no callers reference.
- Pre-release hygiene passes before tagging a version.
- Migration cleanups after a feature flag flip or deprecated API removal.

## Core Rules

### Rule 1: Confirm zero references before deletion
> Source: Fowler, *Refactoring* 2e — "Remove Dead Code"

Before deleting any symbol, grep the entire repository (including
tests, fixtures, and configuration files) for every name the symbol
could be referenced by. Public API symbols MUST also be checked
against downstream callers (other repos, generated clients,
documentation) when applicable.

For behavior, public API, generated, reflective, scheduled, configured, or
cross-repository symbols, use caller graph evidence rather than a single grep
hit. Start with BFS inventory over entrypoints, callers, callees, config, and
registration paths, then use selective DFS deep dive on any path that can
produce an observable side effect. `No references found` means only that the
declared search found no references; it is not by itself a global unused-code
proof.

```bash
# Search across source AND tests
grep -rn "symbolName" --include="*.ts" --include="*.kt" --include="*.py"
# Also check docs and config
grep -rn "symbolName" docs/ config/
```

### Rule 2: Delete in a dedicated commit
> Source: Martin, *Clean Code* — G9

Dead-code removal MUST be a separate commit from feature work or
behavior changes. A reviewer should be able to revert the deletion
in isolation if a hidden caller is discovered post-merge.

### Rule 3: Prefer deletion over commenting out
> Source: Martin, *Clean Code* — G9

Never leave dead code as a comment "for future reference" — version
control IS the history. Commented-out code rots, misleads future
readers, and breaks `grep`-based reference checks.

```kotlin
// BAD
fun process(input: String): String {
    // val cached = legacyCache.lookup(input)
    // if (cached != null) return cached
    return transform(input)
}

// GOOD
fun process(input: String): String {
    return transform(input)
}
```

### Rule 4: Run the full test suite after deletion
> Source: Fowler, *Refactoring* 2e — "Remove Dead Code"

After deletion, run the full test suite (not just the focused unit
tests). Tests that silently passed because the dead code was never
exercised will not surface the issue without a broader run.

### Rule 5: Type checkers and linters are the first gate
> Source: Fowler, *Refactoring* 2e — Automated refactoring tooling

Run the project's type checker (`tsc --noEmit`, `mypy`, `kotlinc`)
and dead-code linter (`ts-prune`, `vulture`, `detekt UnusedPrivate*`)
BEFORE manual grep. Tooling catches the obvious cases; grep covers
the dynamic / string-referenced ones.

## Anti-Patterns
- Commenting out instead of deleting.
- Deleting public symbols without searching downstream consumers.
- Treating `No references found` in one bounded caller graph search as proof
  that a symbol is globally unused.
- Bundling dead-code removal into a behavior-change commit.
- Skipping the full test suite because "no behavior changed".
- Removing test fixtures that look unused without confirming no
  parametrized test references them by string key.

## Interaction with Other Skills
- Works alongside `tdd.md` — TDD's red/green/refactor cycle's refactor
  step is the natural home for in-progress dead-code removal.
- Works alongside `clean-architecture.md` — boundary-violating dead
  code may have been kept "just in case" past a layer rewrite; the
  layer rewrite is the safe deletion point.

## References
- Martin Fowler, *Refactoring: Improving the Design of Existing Code*,
  2nd ed., Addison-Wesley, 2018. ISBN 978-0134757599.
- Robert C. Martin, *Clean Code: A Handbook of Agile Software
  Craftsmanship*, Prentice Hall, 2008. ISBN 978-0132350884.
