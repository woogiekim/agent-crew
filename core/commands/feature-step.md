# /feature-step - Step-gated feature implementation

## Purpose

Implement one complete feature through explicit, reviewable phases instead of a
single broad implementation pass. This command is for work where the user wants
requirements, architecture direction, domain logic, services, adapters, and
external integrations to be separated by reports, reflection time, and approval
gates.

Use this command as a workflow harness. It does not replace `crew:run`; it
structures the task that `crew:run` delegates to the supervisor and stage
agents.

## Trigger

- The user asks to implement a whole feature step by step.
- The feature crosses domain logic, application service, adapter, and external
  integration boundaries.
- The work needs user approval between phases, not only at destructive git or
  deploy operations.
- `/feature-step <feature description>` or `crew:feature-step <feature description>`.

## Skip

- The request is a small bug fix, review-only pass, parity check, or one-file
  refactor with no phase boundary value.
- The user explicitly asks for a single-shot implementation and accepts the
  risk.
- Requirements are too ambiguous to produce a requirements register after
  checking the provided sources; report `STATUS: blocked` and ask for the
  missing source instead of guessing.

## Inputs

- `FEATURE_REQUEST` - prompt input, issue key, file path, or free-text feature
  description.
- `REQUIREMENT_SOURCES` - any combination of:
  - Plane issue title/body/comments
  - GitLab issue title/body/comments
  - GitLab merge request notes when the feature is a follow-up
  - prompt input from the current user
  - local files such as PRD, README, handoff, API contract, design note, or test
    fixture
  - existing code and tests that define current behavior
- `PROJECT_ROOT` - repository root for the implementation.
- `TASK_DIR` - agent-crew task state directory.
- `APPROVAL_MODE` - host structured choice when available; otherwise write the
  requested approval to `context/approval.md` and wait for an explicit user
  response.

## State Files

Write phase state under `{TASK_DIR}/context/feature-step/`:

- `requirements-register.md`
- `implementation-direction.md`
- `phase-2-domain.md`
- `phase-3-application.md`
- `phase-4-adapters.md`
- `phase-5-external-integration.md`
- `phase-report.md`
- `retrospective.md`
- `approval.md`

Also link the current phase summary from `{TASK_DIR}/handoff.md` when the
workflow is paused for user approval.

## Flow

### Phase 0: Requirements Collection

Collect requirements from all available `REQUIREMENT_SOURCES`. Prefer source
evidence over memory or inference. If a source is named but unavailable, record
the gap explicitly.

Write `requirements-register.md` with:

- feature goal
- source list with file, issue, or prompt provenance
- functional requirements
- non-functional requirements
- constraints and skip scope
- acceptance criteria
- open questions
- inferred assumptions, clearly marked

If requirements are incomplete but still actionable, continue only for the
actionable slice and mark deferred scope. If the missing information would
change architecture or user-visible behavior, stop with `STATUS: blocked`.

### Phase 1: Requirements Analysis and Direction

Analyze the requirements and choose the implementation direction before writing
production code. Read existing architecture, current domain boundaries, tests,
and conventions first.

Write `implementation-direction.md` with:

- selected direction
- alternatives considered
- domain boundaries touched
- API, adapter, database, messaging, and external integration impact
- testing strategy
- documentation impact
- risk assessment
- phase plan

#### Implementation Direction Approval

Ask the user to approve the selected direction before implementation starts.
Use the host structured choice UI when available. Otherwise write:

```text
STATUS: approval_required
CURRENT_PHASE: 1
NEXT_APPROVAL: implementation_direction
ARTIFACTS:
  - {TASK_DIR}/context/feature-step/implementation-direction.md
```

Do not start implementation before this approval is recorded in
`context/approval.md`.

### Phase 2: Domain Design and Domain Logic

Implement only domain model, domain rules, invariants, value objects, entities,
domain events, and pure domain logic. Do not implement application services,
HTTP/GraphQL endpoints, message consumers, schedulers, or external API clients
in this phase unless they already exist only as compile-time seams required for
domain tests.

Use TDD for behavior changes:

1. Add or update focused domain tests.
2. Run the test and capture RED when feasible.
3. Implement the smallest complete domain change.
4. Run focused tests to GREEN.
5. Refactor only within the domain boundary.

Write `phase-2-domain.md`, update `phase-report.md`, and pause for user
retrospective and approval before Phase 3.

### Phase 3: Domain Services and Use Cases

Implement application orchestration around the domain:

- domain services
- use cases
- application services
- command/query handlers
- transactions and boundary-level policies
- ports/interfaces required by adapters or external systems

Do not expose new REST, GraphQL, message queue, WebSocket, scheduler, or external
API integration behavior in this phase unless the interface is needed as an
internal port.

Write `phase-3-application.md`, update `phase-report.md`, and pause for user
retrospective and approval before Phase 4.

### Phase 4: Adapters

Implement inbound and outbound adapters after the domain and application layers
are stable:

- REST API
- GraphQL
- message queue producer/consumer
- WebSocket
- scheduler
- CLI or batch adapter
- persistence adapter

Adapters should translate protocol concerns into application service calls.
Keep protocol validation, serialization, error mapping, auth checks, and
transport-specific behavior at the adapter boundary.

Write `phase-4-adapters.md`, update `phase-report.md`, and pause for user
retrospective and approval before Phase 5.

### Phase 5: External System Integration

Implement external API, SDK, producer/consumer, or module integration after the
internal contract is stable. Confirm local/offline constraints first. Do not
call mutating external systems without the centralized approval gate.

Write `phase-5-external-integration.md`, update `phase-report.md`, and pause
for final user retrospective and completion approval.

## Phase Gate Rules

- Do not implement all phases in one pass.
- Each phase must end with a concise final report.
- Each phase must leave time for user retrospective before the next phase.
- Each next phase requires explicit approval.
- Approval for destructive actions such as merge, push, deploy, reset, or branch
  cleanup still goes through the central orchestrator approval gate.
- Missing phase-note artifacts are not proof by themselves; real tests, diffs,
  reviews, and tool events remain the primary evidence.
- If a later phase reveals a requirement or direction flaw, stop and return to
  Phase 1 instead of patching around the decision silently.

## Retrospective Prompt

At the end of each phase, report:

```text
STATUS: approval_required
CURRENT_PHASE: <0|1|2|3|4|5>
PHASE_RESULT: <summary>
EVIDENCE: <tests, diffs, review, or artifact paths>
OPEN_QUESTIONS: <none|list>
NEXT_PHASE: <name>
NEXT_APPROVAL: <approval requested>
ARTIFACTS:
  - {TASK_DIR}/context/feature-step/phase-report.md
  - {TASK_DIR}/context/feature-step/retrospective.md
```

The user may approve, request changes, cancel, or provide retrospective notes.
Treat retrospective notes as new requirements input and update the relevant
phase artifact before continuing.

## Output

```text
STATUS: completed | blocked | cancelled | approval_required
CURRENT_PHASE: <0|1|2|3|4|5|done>
NEXT_APPROVAL: <none|implementation_direction|phase_2|phase_3|phase_4|phase_5|completion>
ARTIFACTS:
  - {TASK_DIR}/context/feature-step/requirements-register.md
  - {TASK_DIR}/context/feature-step/implementation-direction.md
  - {TASK_DIR}/context/feature-step/phase-report.md
```

## Verification

- Focused tests for each changed phase boundary.
- Regression test for the user-visible acceptance criteria.
- Review after each phase when the phase changes public behavior, architecture,
  domain language, or external integration.
- Documentation synchronization when public behavior, commands, setup/update
  flow, domain language, architecture, or long-lived agent guidance changes.
- `git diff --check` before completion.

## Rules

- Source evidence beats inference.
- User approval between phases is part of the workflow, not optional ceremony.
- Keep the diff for each phase as small as possible while still complete.
- Preserve existing architecture and boundaries unless Phase 1 approval explicitly
  selects a migration direction.
- Do not relax TDD, review, documentation CI, or destructive-action approval
  requirements.
