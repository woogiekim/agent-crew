# Persistent Workflow Test Strategy

This document defines the test strategy for validating agent-crew as a:

```text
Persistent AI Workforce System
```

The strategy exists to test agent-crew as a long-running operational workflow
system, not merely as request/response software, prompt execution tooling, or
isolated AI tasks.

Round 1 treats agent-crew as a long-running operational workflow system.
Round 2 adds deterministic operational chaos scenarios and derives persistent
workflow success metrics from those scenarios.

## Objective

Validate that agent-crew prioritizes:

- workflow durability
- execution continuity
- resumability
- operational safety
- deterministic orchestration

over:

- stateless AI tooling
- short-lived prompt wrappers
- superficial latency metrics
- benchmark-style prompt throughput

## Critical Validation Questions

Round 1 establishes deterministic coverage for these questions:

1. Can workflows survive interruption?
2. Can workflows resume safely?
3. Does human supervision remain authoritative?
4. Does workflow determinism remain stable?
5. Can external extensions safely coexist?

The most important validation question is:

```text
Can this AI continue working tomorrow?
```

## Test Categories

| Category | Validates | Round 1 evidence |
|---|---|---|
| Workflow durability | long-running execution, interruption survival, persistent orchestration, workflow continuity | Durable workflow architecture check and workflow replay fixture |
| Resume and recovery | checkpoint restoration, workflow rehydration, state integrity, execution continuation | Durable workflow schema, retry-chaos token-resume case, resume-oriented state checks |
| Human approval integrity | approval enforcement, dangerous operation blocking, manual override safety | Dangerous-command guard tests and approval-gate framework controls |
| Workflow determinism | stable transitions, predictable orchestration, consistent recovery behavior | Workflow replay check and durable state-machine contract |
| Workflow observability | operational visibility, continuity monitoring, recovery diagnostics | Progress buffer, telemetry taxonomy, and framework review controls |
| Plugin isolation | plugin failure isolation, workflow survival, runtime durability | Extension safety policy in durable workflow architecture and capability preflight checks |
| Long-running operational tests | operational endurance, sustained execution, multi-phase continuity | Round 1 defines deterministic contract coverage; later rounds should add time-based hosted endurance evidence |

## Chaos Engineering Requirements

The platform must be validated against:

- process crash
- runtime restart
- partial persistence failure
- plugin failure
- token exhaustion
- memory corruption
- infrastructure interruption

Round 1 does not attempt multi-hour hosted chaos. It creates the deterministic
contract that later hosted tests must satisfy and links each chaos condition to
an existing or planned evidence surface.

## Critical Success Metrics

Persistent workflow validation must track:

- Resume Success Rate
- Workflow Survival Rate
- Recovery Accuracy
- Approval Integrity
- Deterministic Stability
- Workflow Continuity Score

These metrics are operational outcomes. They should be derived from durable
workflow state, checkpoint/recovery events, approval gates, replay results,
retry analytics, and telemetry rather than from prompt speed alone.

## Round 1 Scope

Round 1 adds:

- `docs/persistent-workflow-test-strategy.md`
- `core/evaluations/persistent-workflow-test-strategy.json`
- `core/scripts/persistent-workflow-test-check.py`
- `tests/python/test_persistent_workflow_test_strategy.py`
- framework-review coverage so the strategy remains enforced

Round 1 validates that the repository contains a coherent persistent workflow
test strategy and that the strategy is connected to existing deterministic
checks. It is intentionally not a substitute for future hosted endurance tests.

## Round 2 Scope

Round 2 adds:

- `core/evaluations/persistent-workflow-chaos.json`
- `core/scripts/persistent-workflow-chaos-check.py`
- `tests/python/test_persistent_workflow_chaos.py`
- framework-review coverage for the operational chaos contract

Round 2 validates deterministic operational chaos scenarios for:

- process crash resume
- runtime restart with approval preservation
- token exhaustion partial replay
- plugin failure isolation
- partial persistence failure safe block
- memory corruption quarantine
- infrastructure interruption rehydration

The round 2 checker derives the required operational metrics from scenario
outcomes:

- Resume Success Rate
- Workflow Survival Rate
- Recovery Accuracy
- Approval Integrity
- Deterministic Stability
- Workflow Continuity Score

## Anti-Goals

This test strategy must not focus primarily on:

- raw token speed
- prompt throughput
- benchmark scoring
- superficial latency metrics

Those are secondary concerns. The primary validation remains:

```text
Can the workflow survive and continue safely?
```
