# Agent Crew Brainstorming Integration Design

## Status

- Date: 2026-09-19
- Scope: `crew:run`
- Decision: Approved
- Implementation: Not started

## Context

Agent Crew already separates requirements collection, analysis and planning, execution approval, stage execution, and verification. It does not yet provide the complete pre-implementation design dialogue offered by the Superpowers brainstorming workflow: explicit task-size classification, adaptive questioning, alternative comparison, design approval, and approval invalidation when the design changes.

This design incorporates those principles into the provider-neutral `crew:run` lifecycle. It does not copy Superpowers as a separate execution system and does not change the direct-Agent contract of `crew:agent`.

## Goals

- Classify every `crew:run` task as `Spike`, `Bounded`, or `Architectural` and show the classification and evidence to the user.
- Use a lightweight design path for bounded work and a full interactive design path for architectural work.
- Preserve Agent Crew's centralized approval, resume, audit, and external-write safety contracts.
- Prevent planning and implementation from proceeding from an unapproved architectural design.
- Allow an informed user to downgrade an architectural classification without weakening unrelated safety approvals.
- Make classification, dialogue, design, and approval state durable and resumable.

## Non-goals

- Adding a public `crew:brainstorm` command.
- Changing `crew:agent` or making direct-Agent execution implicitly supervised.
- Replacing requirements collection, the analyst, the Approval Service, or the execution pipeline.
- Allowing Brainstorm Agent output to grant approval or mutate external systems.
- Treating file count, line count, test count, or isolated keywords as architectural proof.

## Chosen Approach

Add an independent Brainstorm Phase inside the `crew:run` Supervisor lifecycle.

The alternatives were:

1. Extend the existing requirements and analyst agents. This minimizes code changes but overloads the analyst, blurs design and execution planning, and may create a detailed plan before the design is accepted.
2. Add an independent Brainstorm Phase. This creates an explicit resumable boundary between requirements and planning and keeps approval ownership centralized. **Chosen.**
3. Add only a Brainstorm Agent. This separates model responsibilities but does not provide a reliable state machine for questions, approval, invalidation, and recovery.

## Lifecycle

```text
Phase 1a: Requirements Intake
  - preserve the raw input
  - compute preliminary classification
  - collect requirements at the required depth

Phase 1b: Brainstorm
  - compute final classification
  - disclose classification and evidence
  - ask questions and compare approaches
  - produce the design
  - obtain design approval for Architectural work

Phase 1c: Analysis and Planning
  - consume only an accepted or approved design
  - create analysis, PRD, pipeline, risks, and execution plan

Phase 1d: Execution Approval
  - Bounded: approve design and execution plan together
  - Architectural: approve the execution plan against the approved design

Phase 2: Execution
Phase 3: Verification and Reporting
```

`Spike` terminates with investigation findings and a recommendation. Keeping spike code or moving into implementation is a new classified task or an explicit transition that requires the appropriate approval.

## Classification Model

Classification order is:

```text
Spike < Bounded < Architectural
```

The system classifies twice:

1. Preliminary classification uses the immutable raw input and inexpensive repository evidence. It selects the interview depth and is not approval evidence.
2. Final classification uses the raw input, collected requirements, and verified repository evidence. Only this result is bound into design and execution approvals.

Each pass combines two independent results:

```text
final = max(deterministic_rule_result, semantic_agent_result)
```

The semantic classifier may raise the deterministic minimum but may not lower it. Conflicting or uncertain evidence resolves to the heavier classification or to additional requirements collection, never silently to `Bounded`.

### Deterministic minimum rules

The first implementation should limit hard rules to conditions where under-classification has material consequences:

- a new project or subsystem;
- a backward-incompatible public API, event, or schema change;
- a persistent data-model change or migration;
- an authentication, authorization, or security-boundary change;
- a multi-repository or external-system contract change;
- an Agent Crew execution, approval, or recovery-model change;
- a destructive, data-loss, or hard-to-reverse operation; or
- scope expansion discovered after approval.

File count, changed-line count, test count, implementation duration, programming language, framework, and isolated words such as `API` or `refactor` are advisory signals only.

### Semantic classification

The Brainstorm Agent evaluates whether:

- the change stays within an established flow;
- ownership or responsibility boundaries move;
- a product or technical policy choice exists between materially different approaches;
- a short design is sufficient to make implementation and verification unambiguous;
- consumer and operational impact are known; and
- multiple approaches must be compared to avoid a consequential hidden choice.

Every result includes the classification, evidence, reasoning, unresolved facts, and classifier version. Both preliminary and final results are shown to the user. If they differ, the system explains why.

## User Downgrade

A user may explicitly downgrade `Architectural` to `Bounded` after the system shows:

- the automatic classification and its evidence;
- the design steps that will be skipped;
- the expected risks and affected boundaries; and
- the consequences of proceeding with the shorter path.

The override records the original classifications, user decision, reason when provided, disclosed risks, classifier versions, and affected artifact hashes.

The downgrade reduces only the brainstorming ceremony. It never relaxes approvals for external writes, destructive operations, deployment, credentials, permissions, security-sensitive actions, or other independently governed risks. Newly discovered architectural impact invalidates the downgrade and dependent approvals.

## Interaction Model

### Spike

Present the investigation question and probe method in two or three sentences, obtain acknowledgement, investigate as cheaply as correctness allows, and report findings as a recommendation. Any generated probe remains explicitly disposable.

### Bounded

Ask only high-impact unanswered questions. Related questions may be grouped into one structured interaction. Then present a short design containing:

- classification and evidence;
- selected behavior and affected boundaries;
- changed scope;
- excluded alternative and reason;
- test and verification method;
- risks and side effects; and
- execution pipeline.

The short design and execution plan share one Phase 1d approval. This must not add an extra approval interaction compared with the existing bounded path.

### Architectural

Ask one question at a time. Each next question may depend on the previous answer. Do not ask for information already established by raw input, issue evidence, requirements, or repository inspection. Do not continue merely to reach a fixed question count.

After the questions, compare two or three materially distinct approaches when they exist. Do not manufacture variants to satisfy a quota. Each approach uses the same comparison fields:

- core method;
- affected components and boundaries;
- benefits;
- drawbacks;
- risks;
- reversibility; and
- verification method.

Present the recommended design in sections and collect feedback on each section. Section acknowledgement is not final design approval.

## Design Contract

An architectural design covers:

- goals and non-goals;
- architecture and responsibility boundaries;
- components and interfaces;
- principal data and control flows;
- error handling and recovery;
- compatibility and migration;
- security and operational impact;
- test and verification strategy;
- chosen approach and rejected alternatives; and
- unresolved facts, including whether each blocks implementation.

Before the final design approval surface opens, validate the design for placeholders, internal contradictions, excessive scope, and ambiguous requirements. Unfinished-marker tokens, conflicting constraints, or implementation-blocking unknowns return the task to design refinement.

The Approval Service binds final approval to the canonical design fields. Meaningful changes to goals, non-goals, public interfaces, responsibility boundaries, data model, affected repositories or modules, security or operational risk, implementation pipeline, classification, or downgrade status invalidate dependent approvals.

Display-only wording changes should not invalidate approval. The first implementation should use canonical structured fields rather than a model-based semantic-diff mechanism.

## Components and Ownership

### `crew:run` orchestrator

- Preserve the Root Input Snapshot.
- Coordinate user interactions across multiple tasks.
- Retain ownership of push, deployment, and other external-write approvals.

### Supervisor

- Own Brainstorm Phase transitions.
- Render questions and record answers.
- Own design and combined approval interactions.
- Validate artifact hashes and decide the resume point.

### Deterministic classifier

- Evaluate hard rules.
- Return a minimum classification, rule IDs, rule version, and evidence.
- Remain provider-neutral and independently testable.

### Brainstorm Agent

- Produce semantic classification and evidence.
- Recommend the next question.
- Compare approaches and draft the design.
- Report unresolved facts and blockers.
- Never grant approval or directly own the user approval surface.

### Analyst

- Consume the accepted or approved design.
- Create analysis, PRD, pipeline, and execution risks.
- Never silently reinterpret or expand the approved design.

### Approval Service

- Record user downgrades.
- Record architectural design approval.
- Bind bounded combined approval to both design and execution plan.
- Invalidate approval when a bound field changes.

## Durable Artifacts

```text
context/
├── brainstorm-classification.json
├── brainstorm-dialogue.json
├── brainstorm-design.md
├── brainstorm-approval.json
├── requirements.md
├── analysis.md
├── prd.md
└── approval.md
```

`brainstorm-classification.json` stores preliminary and final rule/Agent results, evidence, resolution, and versions. `brainstorm-dialogue.json` stores structured questions, options, responses, and idempotency keys. `brainstorm-design.md` stores the selected design and rejected alternatives. `brainstorm-approval.json` stores architectural design approvals and downgrade decisions. Existing `approval.md` remains the execution-approval protocol.

For bounded work, there is no separate design approval. Phase 1d binds the canonical design hash and execution-plan hash in the combined approval record. PRD and pipeline artifacts reference the accepted or approved design hash.

## Resume and Invalidation

- A task waiting for an answer resumes at its single unanswered question.
- A task reviewing design sections resumes after the last acknowledged section.
- A task awaiting final design approval re-renders the same canonical design hash.
- An approved design without PRD or pipeline resumes at Phase 1c.
- A PRD or pipeline with a mismatched design hash is invalid and must be regenerated.
- A changed bound field returns the task to Phase 1b or Phase 1c according to the change.
- Duplicate answer and approval events are ignored by idempotency key.
- Resume does not recompute a pinned classification unless the raw input, requirements, verified evidence, or classifier version changed.

Only one question may be active per task. The orchestrator may display interactions for multiple tasks together, but each architectural dialogue retains its internal ordering.

## Failure Handling

- Deterministic classifier failure is surfaced as `DEGRADED`; it cannot silently lower the classification. The task uses the safe heavier path or stops when a defensible classification is unavailable.
- Brainstorm Agent failure receives bounded retries with the same pinned input. Exhaustion reports a concrete blocker.
- Conflicting evidence is displayed and resolves to the heavier classification.
- Missing required user input produces `WAITING_FOR_INPUT`, not an inferred answer.
- Artifact schema or parsing failure preserves the last valid state and blocks forward transition.
- Placeholder, contradiction, scope, or ambiguity validation failure returns to design refinement.
- Repeated unresolved implementation-blocking ambiguity results in `BLOCKED` without starting implementation.
- No failure fallback may bypass external-write, destructive-action, security, or deployment approval.

## Verification Strategy

### Classifier unit tests

- Each hard rule returns the required minimum classification.
- Overlapping rules select the heaviest result.
- A semantic result cannot lower the hard-rule minimum.
- A semantic result may raise the classification.
- Classifier failure and `Unknown` fail safely.
- Results include rule IDs and versions.
- File count and keywords alone do not force an architectural result.

### State and approval contract tests

- Preliminary classification cannot authorize execution.
- Only final classification is bound to approvals.
- Bounded work uses a design-and-plan combined approval.
- Architectural planning cannot start before design approval.
- Downgrade disclosures and decisions are durable.
- Bound-field changes invalidate dependent approvals.
- Display-only changes preserve approvals.
- Downgrade does not weaken independent risk approvals.

### Resume and failure integration tests

- Resume from question, section review, final design approval, and planning boundaries.
- Duplicate responses and approvals remain idempotent.
- Corrupt artifacts block forward transition without destroying the last valid state.
- Design, PRD, and pipeline hash mismatches are detected.
- Classifier and Brainstorm Agent failures stop safely.
- `Bounded` to `Architectural` promotion invalidates prior approvals.
- Parallel tasks do not mix dialogue or approval state.

### Scenario fixtures

- A limited change inside an existing function flow resolves to `Bounded`.
- A clear request for a new subsystem resolves to `Architectural`.
- An ambiguous small request is interviewed and reclassified.
- A backward-compatible public API field may remain `Bounded` when evidence supports it.
- A backward-incompatible API change is forced to `Architectural`.
- Authentication responsibility movement is raised to `Architectural` semantically.
- Analysis-only work resolves to `Spike`.
- Multi-repository impact discovered during execution promotes the task and invalidates approval.

## Completion Criteria

- All three classifications are visible and behaviorally distinct in `crew:run`.
- Users can inspect and correct classification before implementation.
- Bounded work does not add another approval interaction.
- Architectural work cannot create implementation PRD or pipeline artifacts before design approval.
- Resume returns to the exact pending question or approval boundary.
- Existing `crew:agent` and external-write approval contracts remain unchanged.
- Focused new tests and the existing `crew:run` regression suite pass offline.
- Provider-neutral core documentation and installed adapter mirrors remain consistent.

## Implementation Constraints

- Preserve the immutable Root Input Snapshot.
- Keep candidate selection, design approval, execution approval, and external-action approval as distinct decisions.
- Use the centralized structured interaction surface; stage agents do not ask free-form approval questions.
- Follow Red → Green → Refactor before production-code mutation.
- Do not add an LLM call to technical lifecycle hooks.
- Do not create or advertise unavailable `crew task`, `crew workflow`, or `standalone` commands.
- Prefer additive schema and state transitions over destructive migration of existing task artifacts.
