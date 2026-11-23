# Skill: refactoring-catalog

## Source
- Martin Fowler, *Refactoring: Improving the Design of Existing Code*, 2nd ed., 2018
- Kent Beck, *Tidy First? A Personal Exercise in Empirical Software Design*, 2023

## When to Apply
- Before or after a feature change when nearby code shows a smell listed in Rule 5.
- During TDD REFACTOR, once every test is green.
- To split structural and behavioral changes for review.
- To make the next behavior change safer with a small tidying.
- In review, to decide whether a smell warrants a named refactoring or a note.

## Core Rules

### Rule 1: Wear only one hat at a time
> Source: Fowler, *Refactoring* 2e — ch. 2 "The Two Hats"

Name the hat before each edit: **adding behavior** through a red-to-green test
or **refactoring** while preserving observable behavior. Switch hats between edits.

```text
# BAD — one edit both adds a discount rule AND renames/moves helpers
# GOOD — edit 1 (refactor hat): rename + extract, tests stay green
#        edit 2 (behavior hat): add the discount rule via a new red test
```

### Rule 2: Refactor only on green
> Source: Fowler, *Refactoring* 2e — ch. 2, ch. 4 "Building Tests"

Start refactoring only when every test is green, to distinguish regressions from existing failures.

### Rule 3: Take small steps and run tests between every step
> Source: Fowler, *Refactoring* 2e — ch. 2 "Small Steps"

Make one testable move at a time, such as extracting a function or renaming a symbol.
Run the test suite after each move. Split any step that one run cannot verify.

### Rule 4: Separate structural and behavioral changes into different commits
> Source: Beck, *Tidy First?* — Part II "Managing"; Fowler, *Refactoring* 2e — ch. 2

Preserve observable behavior in **structural** edits (rename, move, extract, inline, reorder).
Keep **behavioral** edits free of restructuring. Split mixed diffs before committing
so structural commits stay independently revertible and behavioral commits stay testable.

```text
# commit A (structural): "refactor: extract PricingPolicy, no behavior change"
# commit B (behavioral): "feat: apply loyalty discount to repeat orders"
```

### Rule 5: Map each smell to its named refactoring
> Source: Fowler, *Refactoring* 2e — ch. 3 "Bad Smells in Code"

Use the named refactoring that resolves the smell:

| Code smell | Named refactoring |
|---|---|
| Long Function | Extract Function |
| Duplicated Code | Extract Function / Pull Up Method |
| Feature Envy | Move Function |
| Data Clumps | Introduce Parameter Object / Extract Class |
| Primitive Obsession | Replace Primitive with Object |
| Divergent Change | Split Phase / Extract Class |
| Shotgun Surgery | Move Function / Move Field (Combine into one module) |
| Long Parameter List | Introduce Parameter Object / Preserve Whole Object |
| Large Class | Extract Class / Extract Subclass |
| Mysterious Name | Rename Variable / Rename Function |
| Comments used as deodorant | Extract Function / Rename to make code self-explaining |

### Rule 6: Extract Function to kill Long Function and Duplicated Code
> Source: Fowler, *Refactoring* 2e — "Extract Function"

Extract repeated fragments or separate responsibilities into functions named for their intent.
A block that needs an explanatory comment is a candidate for extraction.

```text
# BAD
def report(order):
    # compute total
    t = 0
    for i in order.items: t += i.price * i.qty
    # apply tax
    t = t * 1.1
    return format(t)

# GOOD
def report(order):
    return format(taxed(subtotal(order)))
```

### Rule 7: Introduce Parameter Object / Preserve Whole Object for Data Clumps
> Source: Fowler, *Refactoring* 2e — "Introduce Parameter Object"

Bundle data that travels together across signatures (e.g. `startDate, endDate` or
`x, y, width, height`) into one object that can own the group's behavior.

### Rule 8: Replace Primitive with Object for Primitive Obsession
> Source: Fowler, *Refactoring* 2e — "Replace Primitive with Object"

Wrap domain primitives such as `money`, `phoneNumber`, and `currencyCode` in small
value types that centralize and enforce their invariants. See `oop-principles.md` and DDD value objects.

### Rule 9: Move Function for Feature Envy and Shotgun Surgery
> Source: Fowler, *Refactoring* 2e — "Move Function"; ch. 3 smells

For Feature Envy, move the function next to the data it uses most.
For Shotgun Surgery, group the code that changes together in one place.

### Rule 10: Split Phase for Divergent Change
> Source: Fowler, *Refactoring* 2e — "Split Phase"; ch. 3 "Divergent Change"

Split modules with unrelated reasons to change into phases or classes with one
responsibility each. Separate computation from formatting and parsing from evaluation.

### Rule 11: Apply Beck's tidyings as the smallest safe structural moves
> Source: Beck, *Tidy First?* — Part I "Tidyings"

To ease the next change, prefer a small tidying. Apply each of these 15 structural moves
independently and preserve behavior:

1. **Guard Clauses** — replace nested conditionals with early returns.
2. **Dead Code** — delete code that is never reached or referenced.
3. **Normalize Symmetries** — make similar things look similar, different
   things look different.
4. **New Interface, Old Implementation** — introduce the interface you wish
   existed and delegate to the current implementation.
5. **Reading Order** — reorder elements in the order a reader needs them.
6. **Cohesion Order** — place coupled elements adjacent to each other.
7. **Move Declaration and Initialization Together** — declare a variable next
   to where it is first assigned and used.
8. **Explaining Variables** — name a subexpression with a variable that states
   its meaning.
9. **Explaining Constants** — replace a magic literal with a named constant.
10. **Explicit Parameters** — pass what a function needs explicitly instead of
    reaching into shared/global state.
11. **Chunk Statements** — separate statement groups with a blank line at each
    change of purpose.
12. **Extract Helper** — pull a cohesive block into a helper with an intent-
    revealing name.
13. **One Pile** — temporarily inline over-separated fragments into one place
    so a better structure can be seen, before re-splitting.
14. **Explaining Comments** — add a comment only where the code cannot be made
    to explain itself.
15. **Delete Redundant Comments** — remove comments that merely restate the
    code.

### Rule 12: Establish a test safety net before restructuring untested code
> Source: Fowler, *Refactoring* 2e — ch. 4 "Building Tests"

Add tests before restructuring untested code. For legacy code, pin current behavior
with characterization tests (see `legacy-code-seams.md`), then refactor on green.

### Rule 13: Commit at every green and keep each commit revertible
> Source: Fowler, *Refactoring* 2e — ch. 2; Beck, *Tidy First?* — "Batch Sizes"

Commit each coherent structural or behavioral move on green. Keep each commit small, single-purpose, and independently revertible.

### Rule 14: Reveal intent instead of merely shortening code

Refactoring should reveal intent, not merely shorten code. A shorter expression
is worse when it hides parsing, validation, transformation, absence handling,
failure handling, or a policy decision. Prefer names and structure that let a
reviewer see the domain concept being judged.

### Rule 15: Keep transformation and decision phases distinct

Use functional pipelines only when they separate transformation from decision.
A pipeline should make data flow easier to read: parse or normalize input,
map it into meaningful concepts, then evaluate the policy. Do not collapse
lookup, fallback, mutation, and policy judgment into one expression just to
avoid a loop.

### Rule 16: Keep comments aligned with the current contract

Remove comments that no longer match the current contract. A useful comment
explains intent, invariant, compatibility reason, or operational constraint
that the code cannot express directly. Do not preserve stale comments, comments
that merely narrate the old implementation, or comments used to justify code
that should be renamed or extracted.

### Rule 17: Keep the diff reviewable

Keep diffs reviewable by limiting them to the smallest meaningful change. Avoid
format churn, broad whitespace rewrites, unrelated line wrapping, and mechanical
movement that obscures the behavioral or structural change under review.

## Anti-Patterns
- Mixing a rename/move with a behavior change in one commit or one edit.
- Refactoring while a test is red, or with no tests at all.
- "Big bang" restructuring with no test run between steps.
- Inventing an ad-hoc restructuring when a catalogued refactoring already fits
  the smell.
- Leaving a magic literal or a mysterious name in place because "it works".
- Using comments to explain a block that should be an extracted, well-named
  function.
- Treating a large redesign as the only option when a small tidying would
  unblock the next change.
- Replacing a readable loop with a pipeline that hides fallback, failure, or
  policy judgment.
- Preserving comments that disagree with the code's current contract.
- Expanding a focused cleanup into format churn that makes review harder.

## Interaction with Other Skills
- Works alongside `tdd.md` — the REFACTOR step of Red→Green→Refactor is the
  natural home for the moves in this catalog; never refactor on red.
- Works alongside `legacy-code-seams.md` — when the target code is untested,
  build a characterization-test net there before applying any refactoring here.
- Works alongside `dead-code-elimination.md` — the "Dead Code" tidying and the
  "Remove Dead Code" refactoring are the same move; that skill covers the
  safe-deletion procedure in depth.
- Reinforces `oop-principles.md` — Replace Primitive with Object, Extract
  Class, and Move Function are how SOLID and Object Calisthenics get applied to
  existing code.

## References
- Martin Fowler, *Refactoring: Improving the Design of Existing Code*,
  2nd ed., Addison-Wesley, 2018. ISBN 978-0134757599.
- Kent Beck, *Tidy First? A Personal Exercise in Empirical Software Design*,
  O'Reilly Media, 2023. ISBN 978-1098151249.
