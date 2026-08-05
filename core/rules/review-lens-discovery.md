---
name: review-lens-discovery
description: Provider-neutral contract for discovering and classifying safe review lenses before review-synthesis aggregation.
applies-to: review-synthesis command, review-synthesis-coordinator, review-related host adapters
---

# Review Lens Discovery

`review-synthesis` discovers review-related capabilities as review lenses. A
review lens is an independent read-only review command, skill, agent, host
capability, or script whose output can be source-labeled and aggregated.

Discovery does not prove that a review ran. Installation, availability,
eligibility, execution, and synthesis are separate states.

## Metadata Contract

Review lenses declare provider-neutral metadata:

```yaml
kind: review-lens
loaded_by: review-synthesis
lens_id: stable-id
provider: agent-crew|codex|claude|gitlab|local|unknown
surface: command|skill|agent|host-native|script
read_only: true
mutates: false
requires_mr: required|optional|none
requires_remote_read: required|optional|none
requires_supervisor_context: false
default_enabled: true
timeout_seconds: 120
duplicate_group: semantic-review-family
```

Host adapters may expose provider-native lenses through the same contract. Core
commands must not call provider-specific review tools without this declaration.

## Status Values

- `eligible`: the lens is safe and context-compatible for the current
  read-only synthesis run, but it has not necessarily executed yet.
- `completed`: the lens actually ran and produced an artifact or inline result
  in the current synthesis run. Discovery helpers must not emit this status.
- `not-run`: the lens is installed but current context does not satisfy an
  ordinary requirement, such as missing MR context.
- `suggested`: the lens may be useful, but required scope, provider
  availability, cost, or comparison contract is missing.
- `blocked`: the lens would require supervisor context, mutation, approval,
  authentication, or another hard precondition.
- `degraded`: discovery or provider interaction failed.
- `duplicate-suppressed`: another lens in the same duplicate group represented
  the semantic review family.

`completed` must not be printed merely because a provider is installed or a
lens is eligible. If a workflow only discovers the lens and does not execute
it, report `eligible` separately from review completion.

## Safety Filter

Default review-synthesis fan-out may run only lenses that are explicitly
read-only, non-mutating, not supervisor-only, and context-compatible. The system
reviewer agent remains supervisor-spawned and is reported as `blocked` when
discovered outside supervisor context.

MR-only lenses require MR context. Parity lenses require an explicit parity or
producer/consumer comparison signal; otherwise they are `suggested` with the
missing comparison scope. Remote-write review follow-up commands are blocked
unless a separate workflow and approval handles the mutation.
