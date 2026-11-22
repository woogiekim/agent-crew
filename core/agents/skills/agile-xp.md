# Skill: agile-xp

## Source
- Kent Beck, *Extreme Programming Explained: Embrace Change* (2nd ed.), Addison-Wesley, 2004
- Ken Schwaber & Jeff Sutherland, *The Scrum Guide* (2020), https://scrumguides.org/
- Martin Fowler, *Refactoring: Improving the Design of Existing Code* (2nd ed.), Addison-Wesley, 2018
- Ron Jeffries, Ann Anderson & Chet Hendrickson, *Extreme Programming Installed*, Addison-Wesley, 2000

## When to Apply
- Before beginning any implementation cycle
- Before deciding how much code to write before getting feedback
- When scoping an iteration: what is the minimum deliverable slice?
- During review: does this change embody YAGNI, incremental delivery, and collective ownership?

---

## Core Rules

Rule 2 covers YAGNI. Rule 5 covers KISS and DRY.

### Rule 1: Test-First — write the test before the code (XP's core discipline)
> Source: Beck, Ch. 18 "Test-First Programming"; Fowler, Refactoring Ch. 4

**No production code without a failing test.** This is the most important XP
practice. It drives design, provides a living specification, and guarantees
regression safety for every future change.

See `core/agents/skills/tdd.md` for the full RED → GREEN → REFACTOR cycle.

### Rule 2: YAGNI — You Aren't Gonna Need It
> Source: Beck, Ch. 17 "Incremental Design"; Jeffries et al., Part II

Implement only what the current story or task requires. Premature
generalisation adds complexity and maintenance work.

```
// YAGNI violations to avoid:
- Adding a cache layer "because we'll need it"
- Adding a second DB adapter "for future flexibility"
- Adding a feature flag framework before there is a second flag
- Building an abstraction with one concrete implementation
```

### Rule 3: Continuous Integration — integrate and test at least daily
> Source: Beck, Ch. 7 "Continuous Integration"; Fowler, *Continuous Integration* (2006)

All code lives in a shared branch. Every developer integrates (or every CI
pipeline merges) at least once per day. Long-lived feature branches accumulate
merge debt. The integration build must be green at all times — a red build is
the team's top priority.

CI integrates code, tests, and documentation. In an agent-crew task, the
integration unit is the whole shared understanding that the next agent, reviewer,
or human operator must inherit.

Documentation synchronization is part of the integration slice whenever a
change alters public behavior, workflow commands, domain language, operational
constraints, setup/update flows, or architecture decisions.

Implementation implications:

- Agents must commit incremental, working slices — not one massive commit at the
  end.
- Each slice must keep durable docs coherent with the changed code, rules,
  prompts, and tests. This can mean updating tracked docs (`README.md`,
  `docs/**`, agent/rule markdown) or recording `doc_impact: none` with a reason
  in the task artifacts.
- If a documentation backend is configured, the documenter or adapter skill must
  produce the repo-side evidence first and then synchronize externally through
  the configured backend. A missing external adapter may degrade to side-car
  output, but it must not silently erase the documentation obligation.

### Rule 4: Small Releases — ship the smallest useful increment
> Source: Beck, Ch. 4 "Small Releases"; Scrum Guide § Sprint

Release the smallest useful increment to test assumptions early. Each stage
should produce a self-contained, test-passing commit that advances the task
one coherent step. Avoid feature-wide commits that combine multiple steps.

### Rule 5: Simple Design — KISS and DRY
> Source: Beck, Ch. 12 "Simple Design"; Fowler, Refactoring introduction

The design is simple when it:
1. Passes all tests.
2. Expresses every intention clearly (no obscure naming).
3. Contains no duplication.
4. Has the fewest possible elements (no speculative abstractions).

Order these criteria in priority. Tests pass first; remove duplication next;
reduce elements last.

Apply KISS by choosing the smallest readable design that satisfies the current
story. Apply DRY by extracting duplicated knowledge or behavior only when the
extraction reduces maintenance risk without hiding intent.

DRY also applies to names. Do not repeat the class, module, component,
GraphQL type/input, or field type context inside method, field, or helper names
unless the owner intentionally spans multiple domains or the public API is used
without owner/type context.

### Rule 6: Refactor Mercilessly — the code is always improvable
> Source: Beck, Ch. 10 "Refactoring"; Fowler, Refactoring Ch. 2

Refactoring (improving structure without changing behaviour) is not optional.
It is the "R" in RED → GREEN → **REFACTOR**. Accumulating structural debt
slows every future change.

**Refactoring mechanics (Fowler catalogue):**
- Extract Method / Function: isolate a block with a clear purpose
- Rename Variable / Method: make intent obvious
- Move Method: put the method in the class that owns the data
- Replace Conditional with Polymorphism: eliminate type-checking chains
- Introduce Parameter Object: consolidate related parameters

Always refactor with tests green. Never refactor and add features simultaneously.

### Rule 7: Collective Ownership — any developer (or agent) may improve any code
> Source: Beck, Ch. 7 "Collective Code Ownership"

Any developer or agent may improve shared code. When a stage agent finds a
better design in an existing file, refactor it with tests to avoid a workaround.

### Rule 8: Pair Programming / Code Review — all production code is reviewed
> Source: Beck, Ch. 7 "Pair Programming"; Scrum Guide § Definition of Done

Every change to production code is reviewed by at least one other party
(pair programmer, pull request reviewer, or the reviewer agent in the pipeline).
Review catches bugs, spreads knowledge, and maintains collective ownership.

### Rule 9: On-Site Customer — requirements are conversations, not documents
> Source: Beck, Ch. 7 "On-Site Customer"

Clarify requirements with the customer or their representative, including the
product owner, handoff.md, or PRD. Flag ambiguity in the result and ask for
clarification before choosing an interpretation.

### Rule 10: Done means shippable — the Definition of Done is non-negotiable
> Source: Scrum Guide § Definition of Done; XP "Done Done"

A user story is done when it:
- Passes all unit and integration tests
- Passes the acceptance criteria in the PRD
- Has been code-reviewed / reviewer-approved
- Has no known regressions
- Has documentation synchronized for changed behavior, workflow, domain
  language, or architecture decisions
- Is committed to the main branch (or ready for merge)

"90% done" is not done. Partially implemented features must not be committed
to the main branch without a feature flag or an incomplete-but-safe state.

Done means code, tests, and docs are coherent. When docs are intentionally not
changed, the task must carry a reviewable explanation rather than leaving the
absence implicit.

---

## Anti-Patterns
- Big Design Up Front (BDUF) — designing the entire system before writing a line of code
- Long-lived feature branches (> 2 days) — merge daily
- Speculative abstraction — building frameworks, plugins, or generic layers before there are two concrete use cases
- Skipping refactoring to "save time" — structural debt compounds
- Writing code for assumed future requirements — YAGNI
- Committing failing tests to the main branch
- One enormous commit at the end of a stage instead of incremental working commits

## Interaction with Other Skills
- `tdd.md` is the implementation of Rule 1 and Rule 6 (RED → GREEN → REFACTOR)
- `clean-architecture.md` Rule 5 (Simple Design) and Rule 8 (Humble Object) express the same simplicity values
- `code-review.md` is the implementation of Rule 8 (Pair Programming / Code Review)
- `domain-driven-design.md` Rule 9 explains why documentation is part of shared
  model integration for domain and workflow language changes
- All language-specific skills (`effective-kotlin.md`, etc.) should be applied during Rule 6 (Refactor Mercilessly)

## References
- Kent Beck, *Extreme Programming Explained: Embrace Change* (2nd ed.), Addison-Wesley, 2004. ISBN 978-0-32-127865-4.
- Ken Schwaber & Jeff Sutherland, *The Scrum Guide* (2020), https://scrumguides.org/
- Martin Fowler, *Refactoring: Improving the Design of Existing Code* (2nd ed.), Addison-Wesley, 2018. ISBN 978-0-13-468599-1.
- Ron Jeffries, Ann Anderson & Chet Hendrickson, *Extreme Programming Installed*, Addison-Wesley, 2000. ISBN 978-0-20-170842-4.
