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

Prevent the agent from widening work because a command, imported skill, current
directory, or nearby code hints at a larger system. Scope must come from the
explicit request, source-of-truth contract, approved plan, and observable owner
boundary.

## References

- `core/rules/agent-routing.md`
- `core/rules/disambiguation.md`
- `core/rules/runtime-governance.md`
- David L. Parnas, "On the Criteria To Be Used in Decomposing Systems into Modules" (1972)
- Eric Evans, *Domain-Driven Design* (bounded context)

## When to Apply

- A task mentions scope, owner, boundary, approval, remote mutation, or an
  imported command whose origin could be mistaken for the target.
- The work crosses repository, module, producer/consumer, generated artifact,
  deployment, issue, MR, push, merge, or external-write boundaries.
- The current working root conflicts with the ticket, contract, or user note.

## Boundary Rules

Resolve scope in this order:

1. Explicit user request, ticket, or issue body.
2. Source-of-truth API, schema, route, UI, or operational contract.
3. Current working root.
4. Imported command or skill origin.

Treat destructive, external-write, deployment, push, merge, release,
permission, and credential actions as separate approvals. Local completion does
not imply permission to mutate a remote system.

Keep unrelated generated files, sibling systems, legacy paths, and already
MATCH behavior closed unless the request explicitly reopens them. If scope
remains ambiguous after checking evidence, stop before mutation and ask for a
specific boundary decision.

## Checklist

- [ ] Root input and requested target are preserved before planning.
- [ ] Owner, module, repository, and external side effects are named.
- [ ] Out-of-scope paths and systems are listed when they are nearby.
- [ ] Approval status is separated from technical feasibility.
- [ ] Final report distinguishes local work from remote or operational action.
