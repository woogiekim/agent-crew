---
name: scope-boundary-control
description: Keep implementation, review, and planning work inside the explicit request, ownership boundary, and approved mutation scope.
loaded_by: backend,frontend,devops,documenter,analyst,planner,reviewer
axis: scope-boundary
profile_type: review-policy
detection: scope OR boundary OR ownership OR owner OR out of scope OR exclude OR include OR mutation OR remote OR approval OR contract OR 범위 OR 경계 OR 소유 OR 제외 OR 포함 OR 승인 OR 원격 OR 계약
---

# Skill: scope-boundary-control

## Purpose

Ground scope in the explicit request, source-of-truth contract, approved plan,
and observable ownership. Keep that boundary when commands, imported skills,
the current directory, or nearby code suggest broader work.

## References

- `core/rules/agent-routing.md`
- `core/rules/disambiguation.md`
- `core/rules/runtime-governance.md`
- David L. Parnas, "On the Criteria To Be Used in Decomposing Systems into Modules" (1972)
- Eric Evans, *Domain-Driven Design* (bounded context)

## When to Apply

- Tasks involving scope, boundaries, ownership, approval, remote mutation, or an imported
  command whose origin could be confused with the target.
- Work crossing repository, module, producer/consumer, generated artifact,
  deployment, issue, MR, push, merge, or external-write boundaries.
- Conflicts between the working root and the ticket, contract, or user note.

## Boundary Rules

Resolve scope in this order:

1. Explicit user request, ticket, or issue body.
2. Source-of-truth API, schema, route, UI, or operational contract.
3. Current working root.
4. Imported command or skill origin.

Treat destructive, external-write, deployment, push, merge, release,
permission, and credential actions as separate approvals. Local completion does
not imply permission to mutate a remote system.

Keep unrelated generated files, sibling systems, legacy paths, and existing
MATCH behavior closed unless the request reopens them explicitly. If evidence
leaves scope ambiguous, ask for a specific boundary decision before mutation.

Fix problems introduced by the current change inside the current scope. Do not
leave a new problem because similar legacy code already exists nearby. Do not
expand into repository-wide legacy cleanup because the same smell exists in
older code. Clean the code you touched, and split broad legacy cleanup into a
separate follow-up with its own scope and evidence.

Before crossing or changing a boundary, trace the bounded caller graph within approved
scope. Cover affected entrypoints, scheduled jobs, callbacks, adapters, external
consumers, producer paths, persistence or API contracts, and configuration
wiring. Label incomplete coverage a partial graph and limit plan or review
conclusions to checked paths.

## Checklist

- [ ] Root input and requested target are preserved before planning.
- [ ] Owner, module, repository, and external side effects are named.
- [ ] Out-of-scope paths and systems are listed when they are nearby.
- [ ] Boundary changes include caller graph coverage, or explicitly mark the
      coverage as partial with `Unknown` paths.
- [ ] Current-change issues are fixed without widening into unrelated legacy
      cleanup.
- [ ] Approval status is separated from technical feasibility.
- [ ] Final report distinguishes local work from remote or operational action.
