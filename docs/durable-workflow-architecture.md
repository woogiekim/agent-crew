# Durable Workflow Architecture

This document defines the strategic execution architecture for the
agent-crew Persistent AI Workforce System.

It is the repository-level contract for:

- durable workflow state machines
- persistent checkpoint and resume
- role-oriented execution contracts
- human-supervised approval gates
- workflow continuity observability
- workflow-safe plugin and runtime extension
- durable AI workflow protocol semantics

## Issue Coverage

| Issue | Architecture surface |
|---|---|
| #107 | Durable workflow state machine |
| #108 | Persistent checkpoint and resume |
| #109 | Role-oriented execution contracts |
| #110 | Human-supervised execution approvals |
| #111 | Workflow continuity observability |
| #112 | Workflow-safe plugin and runtime extension |
| #113 | Durable AI workflow protocol specification |

## Core Direction

agent-crew workflows are optimized for:

```text
long-running durable AI execution
```

The runtime must prioritize:

- workflow durability
- operational continuity
- long-running execution
- resumable workflows
- human-supervised execution
- durable orchestration

over:

- short-lived prompt execution
- stateless agent loops
- recursive autonomy
- uncontrolled agent proliferation
- arbitrary extension injection

## State Machine

Durable workflows use explicit lifecycle states. The canonical states are:

| State | Meaning |
|---|---|
| `PLANNING` | Requirements, analysis, role selection, and execution graph preparation are active. |
| `CHECKPOINTING` | The runtime is serializing a replayable workflow snapshot before a risky transition. |
| `WAITING_APPROVAL` | Execution is paused until a human approves, revises, or cancels a gated action. |
| `EXECUTING` | One or more bounded role stages are performing work. |
| `REVIEWING` | Reviewer validation, quality gates, and consistency checks are active. |
| `RECOVERING` | The runtime is classifying interruption, failure, or corruption before continuing. |
| `RESUMING` | The runtime is rehydrating state and replaying only the safe continuation path. |
| `ROLLING_BACK` | The runtime is restoring a previous checkpoint or reversing a failed transition. |
| `COMPLETED` | The workflow reached a verified terminal success state. |
| `FAILED` | The workflow reached a terminal failure state with durable evidence. |

Allowed transition families:

- `PLANNING -> CHECKPOINTING -> EXECUTING`
- `PLANNING -> WAITING_APPROVAL -> CHECKPOINTING -> EXECUTING`
- `EXECUTING -> REVIEWING -> CHECKPOINTING -> EXECUTING`
- `EXECUTING -> RECOVERING -> RESUMING -> EXECUTING`
- `WAITING_APPROVAL -> RECOVERING -> RESUMING -> WAITING_APPROVAL`
- `REVIEWING -> COMPLETED`
- `RECOVERING -> ROLLING_BACK -> RESUMING`
- any non-terminal state may transition to `FAILED` only with blocker evidence

Unknown states are runtime governance failures. New states require updates to:

- `docs/durable-workflow-architecture.md`
- `core/schemas/durable-workflow.schema.json`
- `core/evaluations/durable-workflow-architecture.json`
- `core/scripts/durable-workflow-architecture-check.py`

## Checkpoint And Resume

Checkpointing is mandatory before transitions that can lose continuity or human
intent.

Checkpoint records must include:

- workflow id
- current state
- previous state
- phase, stage, and retry attempt
- role ownership
- approval status
- continuation cursor
- replay source event id
- state artifact paths
- modified file summary
- blocker list
- checkpoint hash

Resume behavior must be deterministic:

1. Load the latest valid checkpoint.
2. Validate schema and state transition compatibility.
3. Rehydrate role and approval ownership.
4. Replay only idempotent events after the checkpoint cursor.
5. Continue from the first incomplete safe transition.
6. Halt in `RECOVERING` when checkpoint integrity cannot be proven.

Partial replay is allowed only when the checkpoint marks the replay segment as
idempotent and no pending approval is bypassed.

## Role Contracts

Roles are more important than agent quantity.

Each role must have:

- explicit responsibilities
- execution boundaries
- input contract
- output contract
- state ownership rules
- failure handling policy
- tool capability boundary

Canonical role ownership:

| Role | Owns | Must not own |
|---|---|---|
| Planner | workflow decomposition, stage graph, role selection | production mutation, destructive tools |
| Designer | UX/system design artifacts and design constraints | approval state, deployment |
| Backend | backend implementation within assigned stage | recursive delegation, workflow state mutation |
| Frontend | frontend implementation within assigned stage | recursive delegation, workflow state mutation |
| Reviewer | validation, consistency, policy enforcement | production mutation, feature implementation |
| DevOps | approval-gated deployment, push, release, infrastructure steps | approval issuance, unsupervised destructive execution |

Worker roles must not recursively delegate or mutate workflow state. Reviewer
roles must remain validation-only. Planner roles must not directly implement
production code or execute destructive tools.

## Human-Supervised Approvals

Dangerous operations are human-supervised by default.

Examples:

- production deployment
- git push
- destructive migration
- infrastructure modification
- secret handling

Required approval flow:

```text
AI proposes
-> Human approves
-> AI executes
```

Approval gates must be:

- persistent
- replayable
- auditable
- tied to a command or action fingerprint
- integrated with pause and resume
- preserved across runtime restart

Approval state must never be inferred from free-form prose. Machine decisions
must consume structured approval state.

## Continuity Observability

Workflow observability is focused on continuity, not raw metric collection.

The observability system must answer:

- Can workflows survive interruption?
- Where does continuity break?
- Which workflows fail to recover?
- Which execution paths are unstable?
- Which roles repeatedly block or retry?

Required continuity metrics:

- lifecycle transition count
- checkpoint age
- checkpoint success rate
- resume success rate
- recovery duration
- retry count
- interruption count
- approval wait duration
- role execution duration
- token usage by role
- rollback count
- terminal state distribution

Observability must not mutate workflow state or introduce a second source of
truth. It reads durable state, progress events, tool events, delegation events,
checkpoint artifacts, and terminal result artifacts.

## Plugin And Runtime Extensions

Extensibility must never compromise workflow durability.

Plugins and runtime extensions must declare:

- plugin id
- runtime compatibility
- required capabilities
- granted capabilities
- state surfaces touched
- approval requirements
- isolation mode
- lifecycle hooks
- rollback behavior

Extensions are denied by default when they:

- mutate workflow state without a registered state surface
- bypass approval gates
- introduce untracked execution paths
- prevent replay or checkpoint serialization
- inject executable instructions from untrusted content
- hide tool calls from audit or telemetry

The extension system must prioritize controlled extensibility and operational
stability over feature count.

## Durable Workflow Protocol

The durable workflow protocol is the machine-readable contract for long-running
workflows.

Protocol records must support:

- workflow schema
- execution lifecycle events
- checkpoint semantics
- resume semantics
- recovery semantics
- orchestration events
- role contract schema
- approval event support
- memory reference protocol
- extension capability policy

The protocol favors operational recoverability over minimal generic
interoperability. A generic protocol that cannot preserve workflow continuity is
not sufficient for agent-crew.

Schema file:

```text
core/schemas/durable-workflow.schema.json
```

Evaluation fixture:

```text
core/evaluations/durable-workflow-architecture.json
```

Verifier:

```bash
python3 core/scripts/durable-workflow-architecture-check.py --format text
```

## Preservation Rules

Future changes must not compromise:

- workflow determinism
- execution continuity
- state durability
- human supervision capability
- approval guarantees
- recovery semantics
- operational stability

The key operating principle is:

```text
Long-running AI workflows must survive interruption and continue execution safely.
```
