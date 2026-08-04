---
name: handoff-context-preservation
description: Preserve raw input, decisions, evidence, blockers, and next actions when handing work between agents, sessions, or current-session fallbacks.
loaded_by: backend,frontend,devops,documenter,analyst,planner,reviewer
axis: context-handoff
profile_type: communication
detection: handoff OR resume OR fallback OR current_session_required OR context OR raw input OR blocker OR next action OR decision OR artifact OR 인계 OR 재개 OR 컨텍스트 OR 원문 OR 결정 OR 증거 OR 블로커
---

# Skill: handoff-context-preservation

## Purpose

Make work resumable without changing its meaning. A handoff preserves the raw
request, approved plan, loaded skills, evidence, decisions, blockers, and next
actions so the next agent or current-session fallback can continue the same
work instead of re-resolving it.

## References

- `core/global-agents.md`
- `core/rules/runtime-governance.md`
- `core/rules/memory-governance.md`
- `core/docs/host-bridge-handoff-sop.md`
- ISO/IEC/IEEE 29148:2018 requirements traceability principles

## When to Apply

- A workflow, task, or direct agent execution reaches `handoff_ready`,
  `HOST_BRIDGE: current_session_required`, resume, repair, or session transfer.
- Context is compressed, summarized, copied to another host, or converted into
  a continuation prompt.
- The agent must decide whether missing diagnostic notes are advisory gaps or
  true blockers.

## Handoff Contract

Preserve these fields as facts, not rewritten intent:

```text
root input
  -> selected definition / agent / skills
  -> approved scope and side effects
  -> decisions and assumptions
  -> evidence and verification state
  -> blockers vs advisory gaps
  -> next concrete action
```

Do not re-resolve candidates or widen execution nodes during a current-session
fallback. Missing optional notes can be reported as advisory coverage gaps when
real outcomes, diffs, tests, and tool events are sufficient. Hard blockers are
reserved for conditions that make meaningful progress impossible or would
change an approved boundary.

## Checklist

- [ ] Root input is preserved verbatim or referenced by immutable artifact.
- [ ] Loaded skill paths and approval-relevant versions are recorded when a
      task directory exists.
- [ ] Decisions, assumptions, and policy waits are separated.
- [ ] Evidence and verification status are concrete and current.
- [ ] Next action is executable without reinterpreting the task.
