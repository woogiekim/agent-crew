---
name: contract-parity-checking
description: Compare producer, consumer, and sibling behavior through reachable contracts before claiming parity or migration completeness.
loaded_by: backend,frontend,devops,analyst,planner,qa-owner,reviewer,resolver
axis: contract-parity
profile_type: review-policy
detection: parity OR migration OR contract OR producer OR consumer OR upstream OR downstream OR endpoint OR schema OR route OR screen OR compatibility OR 호환 OR 패리티 OR 이관 OR 계약 OR 생산자 OR 소비자
---

# Skill: contract-parity-checking

## Purpose

Prove compatibility by following real call paths and contracts, not by matching
file names or endpoint labels. A parity claim is valid only when the producer,
consumer, and reachable behavior agree within the approved migration scope.

## References

- `core/rules/evidence-grounded-reasoning.md`
- `core/rules/quality-loop.md`
- Martin Fowler, "Consumer-Driven Contracts" (2011)
- Pact documentation, consumer-driven contract testing
- Eric Evans, *Domain-Driven Design* (bounded context)

## When to Apply

- A task mentions parity, migration, compatibility, producer/consumer,
  upstream/downstream, endpoint, schema, UI route, callback, or legacy behavior.
- The agent must decide whether a changed path is a source of truth, mirror,
  adapter, generated artifact, or unrelated sibling path.
- The work risks breaking an already matching contract while fixing a nearby
  gap.

## Parity Method

Inventory the reachable chain before changing behavior:

```text
caller/UI/job/callback
  -> handler/controller/adapter
  -> service/use case
  -> DAO/client/gateway
  -> downstream schema/API/state
```

Exhaustive caller graph within the approved parity scope is required before a
parity or migration completion claim. Do not claim parity from matching names,
similar endpoint labels, sibling file structure, or current diff shape alone.
Trace at least one consumer-visible entrypoint through the producer state or
contract it observes, then expand to the other reachable callers inside the
approved boundary. If a dynamic path, external system, generated artifact, or
runtime-only registration cannot be checked, classify that path as `UNKNOWN`
instead of treating it as matched.

Use BFS inventory to find the reachable parity surface first: consumer-visible
entrypoints, producer state, adapters, schemas, tests, and configuration. Then
use selective DFS deep dive for each contract-risk path where the behavior must
be proven end-to-end.

Classify each compared path:

- `MATCH`: behavior already agrees; preserve it.
- `GAP`: source and target differ in a user-visible or contract-visible way.
- `INTENTIONAL_DIFF`: difference is documented and owned by the approved scope.
- `UNKNOWN`: evidence is incomplete; do not claim parity.

Use structured parsers, tests, schemas, or first-party fixtures when available.
Do not infer parity from current branch diff alone.

When the parity surface includes normalization, serialization, filtering, or
other boundary transformations, compare the observable contract instead of the
helper shape. Use `core/rules/contract-first-feedback-fidelity.md`
`BOUNDARY_CONTRACT_REVIEW` as the canonical matrix instead of maintaining a
role-local copy.

Report local verification separately from runtime verification; a focused
local test or fixture does not prove live runtime parity by itself.

## Checklist

- [ ] Source-of-truth contract is named.
- [ ] Producer and consumer ownership are identified.
- [ ] Reachable caller path is traced, not just endpoint existence.
- [ ] Existing `MATCH` behavior is preserved.
- [ ] Remaining `GAP` and `UNKNOWN` items are reported separately.
