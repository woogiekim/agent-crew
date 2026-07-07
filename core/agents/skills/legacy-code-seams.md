# Skill: legacy-code-seams

## Source
- Michael C. Feathers, *Working Effectively with Legacy Code*, 2004

## When to Apply
- Before modifying any code that has no tests ("legacy code" in Feathers'
  sense: code without tests, regardless of age).
- When red-first TDD is impossible because the existing code cannot be
  instantiated or exercised in isolation.
- When a bug must be fixed or a feature added inside a large untested
  procedure and a full rewrite is out of scope.
- When a class cannot be constructed under test because of hard-wired
  dependencies (globals, singletons, `new` inside the body, network/DB calls).
- When deciding where to insert a test-enabling boundary without changing
  production behavior first.

## Core Rules

### Rule 1: Treat code without tests as legacy code and net it before changing it
> Source: Feathers, *WELC* — Preface, ch. 2 "Working with Feedback"

Legacy code is code without tests. Before you edit any untested code, establish
a test safety net around the behavior you are about to touch. Editing untested
code without a net is the change that causes regressions; the net is not
optional overhead, it is the precondition for a safe change.

### Rule 2: Write characterization tests to pin current actual behavior
> Source: Feathers, *WELC* — ch. 13 "I Need to Make a Change, but I Don't Know What Tests to Write"

A characterization test documents what the code **actually does**, not what it
should do. Procedure:

1. Write a test that calls the code with realistic inputs.
2. Assert against a value you know is wrong (e.g. `assertEquals(0, result)`).
3. Run it; the failure message reveals the real output.
4. Replace the wrong value with the observed output, so the test now passes
   and encodes current behavior.
5. Repeat for the branches you need to cover.

Only after the behavior is pinned do you modify. A surprising or even buggy
observed behavior is still encoded first; correcting it is a separate,
test-driven behavioral change.

### Rule 3: Find a seam before you insert a test
> Source: Feathers, *WELC* — ch. 4 "The Seam Model"

A **seam** is a place where you can alter behavior without editing in that
place. Every seam has an **enabling point** where you choose which behavior
runs. Locate a seam around the dependency that blocks testing, then use it to
substitute a test double — instead of rewriting the untested body.

### Rule 4: Prefer object seams over preprocessing and link seams
> Source: Feathers, *WELC* — ch. 4 "Seam Types"

Enumerate the seam types and prefer the most maintainable:

- **Object seam** — override a method or inject a collaborator via an
  interface/subclass; the enabling point is object construction or dependency
  injection. **Prefer this.**
- **Preprocessing seam** — alter behavior via macros/preprocessor before
  compilation; language-limited and hard to reason about.
- **Link seam** — swap an implementation at link/classpath/module-resolution
  time; useful when source cannot be changed, but the enabling point is far
  from the code.

Reach for object seams first because their enabling point is explicit in code
and visible to readers.

### Rule 5: Use Sprout Method to add new behavior in tested code
> Source: Feathers, *WELC* — ch. 6 "Sprout Method"

When you must add behavior to an untested method, do not grow the untested
body. Write the new behavior as a new, fully test-driven method, and call it
from the legacy site with a single line. The new code is born under test; the
old code is untouched except for the one call.

```text
# BAD — new logic buried inside the untested method
def post_entries(entries):
    ...50 untested lines...
    for e in entries:            # new dedupe logic added inline, untested
        if e.id not in seen: ...

# GOOD — sprout a tested method, call it from the legacy site
def post_entries(entries):
    entries = unique_entries(entries)   # new, fully tested
    ...50 untested lines unchanged...
```

### Rule 6: Use Sprout Class when the sprout needs its own home
> Source: Feathers, *WELC* — ch. 6 "Sprout Class"

When the new behavior is substantial, or the legacy class cannot even be
instantiated under test, put the new behavior in a new class that is fully
tested, and call into it from the legacy site. This gives new logic a clean,
tested home without depending on the untestable host.

### Rule 7: Use Wrap Method to run new behavior around unchanged old behavior
> Source: Feathers, *WELC* — ch. 7 "Wrap Method"

To add behavior that always runs with an existing method, rename the old method
and create a new method with the original name that calls the renamed original
plus the new behavior. The untested body is preserved verbatim; the addition is
isolated and testable.

```text
# rename original pay() -> dispatch_payment(); new pay() wraps it
def pay():
    dispatch_payment()   # original body, unchanged
    log_payment()        # new, tested behavior
```

### Rule 8: Use Wrap Class (decorator) to add behavior across a whole interface
> Source: Feathers, *WELC* — ch. 7 "Wrap Class"

When new behavior must apply around many methods, wrap the existing class in a
decorator that implements the same interface, adds the new behavior, and
delegates to the wrapped instance. The original class stays untouched and
untested-body-preserving; the wrapper is small and testable.

### Rule 9: Break dependencies with the least behavior-changing move available
> Source: Feathers, *WELC* — ch. 25 "Dependency-Breaking Techniques"

To get code into a test harness you often must break a dependency (Extract
Interface, Parameterize Constructor, Extract and Override Factory Method,
Introduce Static Setter). Choose the technique that changes the least
production behavior and can itself be applied without tests (these enabling
edits are the sanctioned exception; see Rule 11). Once a seam exists, the real
change is test-driven.

### Rule 10: Cover the change points and the effect sketch, not the whole class
> Source: Feathers, *WELC* — ch. 11 "I Need to Make a Change. What Methods Should I Test?"

You do not need to characterize an entire legacy class before changing one
method. Identify the change points, sketch how effects propagate from them
(the "effect sketch"), and put characterization tests at the boundary of that
effect. Test what your change can break, not everything that exists.

### Rule 11: Characterization tests are the sanctioned re-entry into the TDD cycle
> Source: Feathers, *WELC* — ch. 13; agent-crew `tdd.md` (new-code authority)

`tdd.md` remains authoritative for **new** code: red first, then green, then
refactor. This skill regularizes the framework's **TDD exception path** for
untested legacy code, where a red-first test is impossible because the code is
not yet reachable under test. The sanctioned sequence is:

```text
identify change point
  -> find/create a seam (minimal dependency-breaking edit)
  -> write characterization tests that pin current behavior (green)
  -> now on green, make the change test-first (red -> green -> refactor)
```

Record the exception explicitly (why red-first was impossible, what seam was
introduced) so the reviewer can see the safety net was built before the change.

## Anti-Patterns
- Editing untested code directly "because it is a small change".
- Writing a characterization test that asserts intended behavior instead of
  actual behavior, hiding the real current output.
- Growing an untested method with new inline logic instead of sprouting a
  tested method or class.
- Rewriting an untested body to make it testable before any net exists.
- Breaking a dependency with a large, behavior-altering redesign when a small
  Extract Interface / Parameterize Constructor would do.
- Trying to characterize an entire class before touching one method.
- Skipping the recorded exception, so a reviewer cannot tell a net was built.

## Interaction with Other Skills
- Extends `tdd.md` — `tdd.md` owns new-code red-first discipline; this skill
  owns the sanctioned re-entry path when red-first is impossible on untested
  code. Both end in the same Red→Green→Refactor loop.
- Works alongside `refactoring-catalog.md` — build the characterization net
  here first, then apply catalogued refactorings on green.
- Works alongside `oop-principles.md` — Extract Interface and dependency
  injection seams are Dependency Inversion applied to make code testable.

## References
- Michael C. Feathers, *Working Effectively with Legacy Code*, Prentice Hall,
  2004. ISBN 978-0131177055.
