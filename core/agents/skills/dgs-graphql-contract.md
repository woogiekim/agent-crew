---
name: dgs-graphql-contract
description: Keep Netflix DGS GraphQL resolver boundaries, generated schema types, documentation, and tests aligned as one external contract.
loaded_by: backend,reviewer
axis: graphql-dgs-contract
profile_type: review-policy
detection: DGS OR GraphQL resolver OR graphqls OR generated.types OR DgsQuery OR DgsMutation OR CLAUDE.md
---

# Skill: dgs-graphql-contract

## Source
- agent-crew user feedback, "GraphQL schema is an external contract; resolver, generated type, docs, and tests must tell the same truth", 2026-07-18.
- Netflix DGS Framework generated types and execution testing conventions.
- DDD ubiquitous language and boundary contracts: shared model terms must stay aligned across code and documentation.

## When to Apply
- A Kotlin/Spring project uses Netflix DGS.
- A change touches `.graphqls`, `@DgsQuery`, `@DgsMutation`, resolver return types, generated GraphQL types, proxy/domain DTO mapping, or GraphQL contract tests.
- A review mentions generated DGS types, resolver direct calls, CLAUDE.md drift, schema binding, or test naming/path conventions.

## Core Rules

### Rule 1: Resolver return types must honor the generated schema contract

GraphQL schema is an external contract. A DGS resolver should return the DGS
codegen generated type at the resolver boundary, not a hand-written proxy or
domain DTO, when a generated type exists for that schema field.

Use explicit mapper functions such as `toGql()` between proxy/domain models and
generated types. This makes schema field, nullable, and naming drift visible at
compile time.

Do not expose domain/proxy DTOs directly from a resolver merely because DGS can
serialize matching property names today.

### Rule 2: Documentation is part of the boundary contract

If implementation and `CLAUDE.md`, README, migration docs, or schema docs
contradict each other, fix the owning document in the same change. In an
agent-assisted repository, stale docs are not background noise; they are
operational input for the next agent, reviewer, and maintainer.

Do not leave "not implemented", "out of scope", or stale ownership statements
after the code has implemented that contract.

### Rule 3: Direct resolver tests are not enough for external API confidence

Resolver direct-call tests verify Kotlin function behavior only. For new or
changed GraphQL contract surfaces, add or update a DGS execution-path test when
reasonable so the SDL, DGS binding, generated type serialization, and GraphQL
selection set shape are exercised together.

If a DGS execution-path test is impractical, record the concrete reason in the
test or task summary and keep at least one lower-level test for the mapper and
resolver delegation.

### Rule 4: Test names and paths are automation contracts

Use the project's established test path and naming conventions. Test names are
not only style; they support search, review triage, and multi-agent quality
control.

If the repository uses prefixes such as `정상 케이스`, `예외 케이스`, or
`경계 케이스`, preserve them so reviewers can classify intent consistently.

### Rule 5: Reviewer severity

Reviewer agents should classify a DGS contract drift as `IMPORTANT` when any of
these are true:

- a resolver returns a hand-written DTO while a generated DGS type exists for
  the schema contract;
- an owning document contradicts the implemented GraphQL behavior or ownership
  boundary;
- only resolver direct-call tests exist for a changed external GraphQL field and
  no DGS execution-path coverage or explicit exception is provided;
- test names or paths break the project's searchable convention enough to hide
  contract coverage from review.

## Anti-Patterns
- Returning proxy/domain DTOs directly from DGS resolvers because property names happen to match.
- Treating `CLAUDE.md` or migration docs as optional commentary after changing an external contract.
- Claiming GraphQL contract parity from resolver direct calls only.
- Adding DGS execution tests that duplicate every unit assertion instead of covering the binding/serialization path.
- Renaming tests into generic prose that loses the repository's classification prefix.

## Interaction with Other Skills
- Works with `backend-kotlin-spring.md`: DGS resolver work must consult this skill alongside Kotlin/Spring rules.
- Works with `documentation-impact.md`: stale GraphQL/docs contract drift is a real documentation-impact finding.
- Works with `dgs-dataloader.md`: use DataLoader guidance for list/nested field performance; use this skill for schema boundary correctness.
- Works with `code-review.md`: report DGS contract drift as `IMPORTANT` when it affects external API confidence.
