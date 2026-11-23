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

Legacy code is code without tests. Establish a safety net for the affected behavior before editing it.

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

Pin the observed behavior before modifying it, even if it is surprising or buggy.
Correct it in a separate test-driven change.

### Rule 3: Find a seam before you insert a test
> Source: Feathers, *WELC* — ch. 4 "The Seam Model"

A **seam** lets you alter behavior without editing that code. Its **enabling point**
selects the behavior. Find the seam around the blocking dependency and substitute a test double
while keeping the untested body intact.

### Rule 4: Prefer object seams over preprocessing and link seams
> Source: Feathers, *WELC* — ch. 4 "Seam Types"

- **Object seam** — prefer overriding a method or injecting a collaborator via an
  interface or subclass. Construction or injection makes the enabling point explicit.
- **Preprocessing seam** — macros change behavior before compilation. This is language-limited
  and harder to reason about.
- **Link seam** — swap the implementation at link, classpath, or module resolution. Useful when
  source is unavailable to edit. The enabling point is farther from the code.

### Rule 5: Use Sprout Method to add new behavior in tested code
> Source: Feathers, *WELC* — ch. 6 "Sprout Method"

Add behavior in a new, fully test-driven method. Call it with one line from
the legacy method and preserve the rest of the untested body.

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

If new behavior is substantial or the legacy class cannot be instantiated under test,
put the behavior in a fully tested class and delegate to it from the legacy site.

### Rule 7: Use Wrap Method to run new behavior around unchanged old behavior
> Source: Feathers, *WELC* — ch. 7 "Wrap Method"

Rename the original method and preserve its body verbatim. Under the original name,
add a wrapper that calls both the renamed method and the new, independently testable behavior.

```text
# rename original pay() -> dispatch_payment(); new pay() wraps it
def pay():
    dispatch_payment()   # original body, unchanged
    log_payment()        # new, tested behavior
```

### Rule 8: Use Wrap Class (decorator) to add behavior across a whole interface
> Source: Feathers, *WELC* — ch. 7 "Wrap Class"

For behavior spanning multiple methods, add a small, testable decorator with
the same interface. Delegate to the original instance and leave its class untouched.

### Rule 9: Break dependencies with the least behavior-changing move available
> Source: Feathers, *WELC* — ch. 25 "Dependency-Breaking Techniques"

Choose the dependency break with the least effect on production behavior: Extract Interface,
Parameterize Constructor, Extract and Override Factory Method, or Introduce Static Setter.
The technique must be safe to apply without tests under Rule 11's enabling-edit exception.
Once the seam exists, make the real change test-first.

### Rule 10: Cover the change points and the effect sketch, not the whole class
> Source: Feathers, *WELC* — ch. 11 "I Need to Make a Change. What Methods Should I Test?"

Identify the change points and make an effect sketch of how their effects propagate.
Characterize the boundary of that effect to cover behavior the change could break.

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

## 관찰 계약과 TDD 증거 연결

이미 테스트가 있는 코드도 변경 전 코드·호출자의 정상/실패/경계와 부작용을 먼저 점검한다. 보존할 기존 TC를 변경 전 구현에서 실행하고, 승인된 변경은 별도 Red로 시작한다. `tdd.md`의 구현 전 계약/실행 수집 순서를 따른다. 사후 TC를 이전 기준의 증거로 소급하지 않는다. 실행 불가 seam/환경 예외는 구현 전에 한계·대체 근거·잔여 위험을 기록하며, 미실행을 통과로 표시하지 않는다.

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
