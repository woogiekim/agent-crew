# Branch Naming Rules

Defines how `crew:run` constructs the working branch for every task.

## Prefix Classification

Scan the task description for keywords (case-insensitive). Use the **first**
matching rule; rules are evaluated in the order listed.

| Prefix | Trigger keywords / phrases |
|---|---|
| `fix` | fix, fixes, fixed, bug, bugs, repair, repairs, broken, error, errors, failing, failure, failures, regression, regressions |
| `docs` | doc, docs, documentation, readme, guide, guides, instruction, instructions, manual |
| `refactor` | refactor, refactors, refactoring, restructure, cleanup, simplify, reorganize, "clean up" |
| `test` | test, tests, testing, spec, specs, coverage, qa |
| `chore` | chore, chores, build, dependency, dependencies, deps, config, configuration, setup, tooling, maintenance, "continuous integration" |
| `feat` | _(default — none of the above matched)_ |

The keyword scan operates on the full set of words extracted by
`re.findall(r"[a-z0-9]+", text.lower())` plus phrase matching against the
lowercased description for multi-word triggers (e.g., `"clean up"`).

## Slug Generation

Generate a concise kebab-case slug from the task description:

1. Lowercase the description.
2. Extract all `[a-z0-9]+` tokens.
3. Remove stopwords:
   `a, an, and, are, as, at, be, by, for, from, in, into, is, it, of, on, or,
   so, that, the, to, with, instead, only, than, rather`
4. Join remaining tokens with `-`.
5. Truncate to 48 characters and strip trailing `-`.
6. If the result is empty, use `task` as the fallback.

## Final Format

```
BRANCH="{prefix}/{slug}"
```

No TASK_ID suffix is appended. The slug derived from the task description
provides sufficient uniqueness for human-readable branch names.

## Examples

| Task description | Branch |
|---|---|
| Fix login redirect loop | `fix/fix-login-redirect-loop` |
| Add user authentication to the API | `feat/add-user-authentication-api` |
| Refactor database connection pooling | `refactor/refactor-database-connection-pooling` |
| Update README with setup instructions | `docs/update-readme-setup-instructions` |
| Improve branch naming in crew:run workflow | `refactor/improve-branch-naming-crew:run-workflow` |
| Add order management API | `feat/add-order-management-api` |

## Implementation Reference

The authoritative implementation lives in **`core/commands/run.md` — Step 4**
(`branch_prefix_for_task` and `task_slug_for_branch` Python helpers).
This rule file is the human-readable specification; the Step 4 code is the
executable form.
