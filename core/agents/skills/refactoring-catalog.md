# Skill: refactoring-catalog

## Source
- Martin Fowler, *Refactoring: Improving the Design of Existing Code*, 2nd ed., 2018
- Kent Beck, *Tidy First? A Personal Exercise in Empirical Software Design*, 2023

## When to Apply
- Before or after any feature change, when the surrounding code shows a code
  smell (long function, duplicated code, feature envy, data clumps, primitive
  obsession, shotgun surgery, divergent change).
- During the REFACTOR step of the TDD cycle, once every test is green.
- When a diff mixes structural change (renames, moves, extractions) with
  behavioral change and the two should be separated for review.
- When a small structural cleanup ("tidying") would make an imminent behavior
  change easier to land safely.
- When reviewing a change and deciding whether a smell justifies a named
  refactoring versus a note.

## Core Rules

### Rule 1: Wear only one hat at a time
> Source: Fowler, *Refactoring* 2e — ch. 2 "The Two Hats"

At any moment you are either **adding behavior** (new capability, new test
going red-to-green) or **refactoring** (restructuring without changing
observable behavior). Never do both in the same edit. Name which hat you are
wearing before you type. Switching is fine and frequent; blending is not.

```text
# BAD — one edit both adds a discount rule AND renames/moves helpers
# GOOD — edit 1 (refactor hat): rename + extract, tests stay green
#        edit 2 (behavior hat): add the discount rule via a new red test
```

### Rule 2: Refactor only on green
> Source: Fowler, *Refactoring* 2e — ch. 2, ch. 4 "Building Tests"

Never start a refactoring while any test is red. A failing test means behavior
is in flux; restructuring on top of it destroys your ability to tell a
regression from an in-progress change. Get to green first, then refactor.

### Rule 3: Take small steps and run tests between every step
> Source: Fowler, *Refactoring* 2e — ch. 2 "Small Steps"

Each refactoring move must be small enough that the test suite can run after
it. Extract one function, run tests. Rename one symbol, run tests. If a step
is too large to verify with a single test run, split it. The safety of
refactoring comes from the frequency of verification, not the cleverness of
the move.

### Rule 4: Separate structural and behavioral changes into different commits
> Source: Beck, *Tidy First?* — Part II "Managing"; Fowler, *Refactoring* 2e — ch. 2

A **structural** change (rename, move, extract, inline, reorder) must never
change observable behavior. A **behavioral** change must never restructure.
Commit them separately: a structural commit is safe to revert in isolation, and
a reviewer can verify a behavioral commit against tests without wading through
mechanical noise. When a diff mixes both, split it before committing.

```text
# commit A (structural): "refactor: extract PricingPolicy, no behavior change"
# commit B (behavioral): "feat: apply loyalty discount to repeat orders"
```

### Rule 5: Map each smell to its named refactoring
> Source: Fowler, *Refactoring* 2e — ch. 3 "Bad Smells in Code"

Do not improvise. When a smell appears, reach for the catalogued refactoring
that resolves it:

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

When a function does more than one thing, or a fragment repeats, extract the
fragment into a well-named function. The name must state intent, not
mechanism. A function whose body needs a comment to explain a block is a
function waiting to be extracted.

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

When the same group of data items travels together through multiple signatures
(e.g. `startDate, endDate` or `x, y, width, height`), bundle them into a single
object. This kills Data Clumps and Long Parameter List at once and gives the
group a home for behavior.

### Rule 8: Replace Primitive with Object for Primitive Obsession
> Source: Fowler, *Refactoring* 2e — "Replace Primitive with Object"

When a primitive (string, int) carries domain meaning and validation
(`money`, `phoneNumber`, `currencyCode`), wrap it in a small value type so the
invariant lives in one place and cannot be bypassed. This complements
`oop-principles.md` (Wrap Primitive Types) and DDD value objects.

### Rule 9: Move Function for Feature Envy and Shotgun Surgery
> Source: Fowler, *Refactoring* 2e — "Move Function"; ch. 3 smells

When a function is more interested in another module's data than its own
(Feature Envy), move it next to the data it uses. When one conceptual change
forces edits scattered across many modules (Shotgun Surgery), move the scattered
pieces together so the change has a single home.

### Rule 10: Split Phase for Divergent Change
> Source: Fowler, *Refactoring* 2e — "Split Phase"; ch. 3 "Divergent Change"

When one module changes for several unrelated reasons, separate it into phases
or classes so each has exactly one reason to change (Single Responsibility).
Split a computation from its formatting; split parsing from evaluation.

### Rule 11: Apply Beck's tidyings as the smallest safe structural moves
> Source: Beck, *Tidy First?* — Part I "Tidyings"

Prefer a tiny tidying over a large redesign when the goal is only to make the
next change easier. The fifteen tidyings, each a self-contained structural move
that must not change behavior:

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

Refactoring is only safe under tests. If the code you want to restructure has
no tests, stop and build the net first. For untested legacy code, use
characterization tests (see `legacy-code-seams.md`) to pin current behavior,
then refactor on green.

### Rule 13: Commit at every green and keep each commit revertible
> Source: Fowler, *Refactoring* 2e — ch. 2; Beck, *Tidy First?* — "Batch Sizes"

Commit whenever the suite is green and one coherent structural or behavioral
move is complete. Small, frequent, single-purpose commits make bisection and
revert cheap and keep review focused.

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
</content>
</invoke>
