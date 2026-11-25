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

Claim parity only when real call paths confirm agreement between producer and
consumer contracts and reachable behavior within the approved scope.

## References

- `core/rules/evidence-grounded-reasoning.md`
- `core/rules/quality-loop.md`
- Martin Fowler, "Consumer-Driven Contracts" (2011)
- Pact documentation, consumer-driven contract testing
- Eric Evans, *Domain-Driven Design* (bounded context)

## When to Apply

- Parity, migration, compatibility, producer/consumer, upstream/downstream,
  endpoint, schema, UI route, callback, or legacy behavior.
- Classifying changed paths as source of truth, mirror, adapter, generated
  artifact, or unrelated sibling.
- Fixing a gap that could break an already matching contract.

## Parity Method

Inventory the reachable chain before changing behavior:

```text
caller/UI/job/callback
  -> handler/controller/adapter
  -> service/use case
  -> DAO/client/gateway
  -> downstream schema/API/state
```

Exhaustive caller graph within the approved parity scope is required before
claiming parity or migration completion. Do not claim parity from matching names,
endpoint labels, sibling structure, or diff shape alone.

Use BFS inventory for consumer-visible entrypoints, producer state, adapters,
schemas, tests, and configuration. Trace at least one consumer-visible entrypoint
to the producer state or contract it observes, then cover all other reachable
callers in scope. Use a selective DFS deep dive to prove each contract-risk path
end-to-end. Mark unchecked dynamic paths, external systems, generated artifacts,
or runtime-only registrations as `UNKNOWN`.

Classify each compared path:

- `MATCH`: behavior already agrees; preserve it.
- `GAP`: source and target differ in a user-visible or contract-visible way.
- `INTENTIONAL_DIFF`: difference is documented and owned by the approved scope.
- `UNKNOWN`: evidence is incomplete; do not claim parity.

Use structured parsers, tests, schemas, or first-party fixtures when available.

For normalization, serialization, filtering, and other boundary transformations,
compare the observable contract. Use `BOUNDARY_CONTRACT_REVIEW` from
`core/rules/contract-first-feedback-fidelity.md`; avoid a role-local copy.

Report local and runtime verification separately. Require live evidence for
runtime parity claims.

## Checklist

- [ ] Source-of-truth contract is named.
- [ ] Producer and consumer ownership are identified.
- [ ] Reachable caller path is traced, not just endpoint existence.
- [ ] Existing `MATCH` behavior is preserved.
- [ ] Remaining `GAP` and `UNKNOWN` items are reported separately.
