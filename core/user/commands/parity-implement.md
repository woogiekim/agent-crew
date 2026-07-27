# /parity-implement — Evidence-gated parity implementation planning

## Purpose

Transform a completed deep `crew:parity-check` report into bounded implementation units without
crossing the Task or Workflow execution boundary. This command plans from verified cross-repo
evidence; it does not treat endpoint names, ticket labels, imported skill origins, or repository
proximity as implementation scope.

This command is fully general-purpose. It never hardcodes a project, ticket prefix, repository,
endpoint, menu, UI technology, or workflow shape.

## Trigger

- The user supplies a completed deep parity report or its readable local artifact path and asks
  for implementation units or execution-ready raw-input candidates.
- `$parity-implement <parity evidence or local report path>`
- `/parity-implement <parity evidence or local report path>`

## Inputs

- `PARITY_EVIDENCE` — the completed parity report body or a readable local report path.
- `TARGET_REPOS` — repository roots named by the report. Do not add repositories from memory.
- `MODE` (optional) — `plan-only` or a caller-described output format. This command has no
  direct execution mode.
- `ACCEPTED_RESIDUAL_GAPS` (optional) — gaps the user explicitly accepts, each with owner,
  reason, and follow-up. Silence is not acceptance.

If the evidence or repository paths are missing, ask only for the missing values. Never infer a
completed parity result from a ticket number, endpoint list, previous session, or absence of a
reported mismatch.

## Evidence Gate

Before reading implementation files or generating units, validate all of the following:

1. The report contains `TARGET_DISCOVERY: completed` for the same scope and repository set.
2. `IN_SCOPE_OPERATIONS` lists every reachable operation with source evidence.
3. `DEPENDENCY_GRAPH` contains repository, `file:line`, symbol or method, and call direction for
   every in-scope node and edge.
4. `UI_COVERAGE` is `completed`, or it is `not_applicable` with evidence identifying the
   relevant non-UI entrypoints. `incomplete` fails the gate.
5. `COVERAGE_GAPS` is explicitly `none`, or every remaining gap has explicit user acceptance
   with owner, reason, and follow-up. Any unaccepted gap fails the gate.
6. Every `MISMATCH` contains evidence from each involved repository and an `IMPACT` or concrete
   failure scenario.
7. Every proposed actionable `UNVERIFIABLE` gap has an explicit source-of-truth contract and
   explicit user approval to implement it despite incomplete parity evidence.
8. Every discovered operation and atomic assertion is represented by `MATCH`, `MISMATCH`, or
   `UNVERIFIABLE`; no item disappears between discovery and the final report.

Endpoint-name-only parity is insufficient. A route list, DTO list, document checklist, grep hit,
or report without reachable-operation coverage fails the gate.

On failure, do not create implementation units. Return:

```text
STATUS: blocked
EVIDENCE_GATE: failed
MISSING_OR_INVALID_EVIDENCE: <specific fields and operations>
PARITY_RERUN_SCOPE: <same scope and repository set>
PARITY_RERUN_RAW_INPUT: <copy/paste-ready crew:parity-check raw input>
NEXT_EXPLICIT_COMMAND: none
```

## Existing Implementation Inventory

After the evidence gate passes, inspect every target repository before proposing changes:

1. Resolve and record each repository's current root, branch or detached state, revision, and
   working-tree status.
2. Trace the report's in-scope graph against current production source and focused tests.
3. Inventory every existing partial implementation, including already migrated routes, methods,
   transformations, error mappings, feature flags, tests, and generated boundaries.
4. Pin every still-valid `MATCH` as a preserve constraint. A proposed unit must not replace,
   regress, or duplicate it.
5. If the current repository revision or graph differs materially from the parity evidence,
   block and request a same-scope parity refresh rather than adapting stale findings silently.

## Implementation Units

Generate units only for evidence-backed `MISMATCH` items and user-approved actionable gaps.
Each unit must include:

- Stable unit identifier and target repository.
- Exact in-scope graph segment and `file:line` evidence.
- Contract discrepancy or approved target behavior.
- Existing partial implementation inventory and preserve constraints.
- Files or modules to inspect; do not invent exact edit paths before verifying them locally.
- Producer, consumer, UI/client, data, and shared-helper dependencies that affect ordering.
- Focused Red → Green → Refactor test target and regression checks.
- Acceptance criteria and follow-up parity assertions for the same scope.
- Any accepted residual gap with owner, reason, and follow-up.

Do not create a unit for a `MATCH`, an out-of-scope operation, an unaccepted coverage gap, or an
unverified behavior without an approved source-of-truth contract.

## Dependency And Candidate Planning

Build a dependency DAG from the verified call graph:

- A producer or source-of-truth contract change precedes consumers that depend on that change.
- Consumer and UI/client units follow only when their required producer contract is available.
- Truly independent units may share a parallel group even when files overlap.
- A dependency is semantic, not inferred solely from repository ordering or file overlap.

One independent linear unit may produce a `crew:task` raw-input candidate. Multiple independent
units may produce a `crew:workflow` candidate only when the candidate includes at least one real
parallel group of two or more Task Invocations, an explicit barrier, and a result policy.

This command MUST NOT execute, select, approve, or create a Task or Workflow definition. It only
returns candidate raw inputs. The user must continue with a separate explicit `crew:task` or
`crew:workflow` command, where Registry resolution, Candidate Selection, plan freezing, and
Execution Approval occur. `crew:run` remains a deprecated candidate-only compatibility alias and
is never an execution path.

## Output

```text
STATUS: completed | blocked | cancelled
EVIDENCE_GATE: passed | failed
SOURCE_PARITY_SCOPE: <scope and evidence artifact>
TARGET_REPOS: <verified repo roots and revisions>
PRESERVE_CONSTRAINTS: <existing MATCH behavior and tests>
IMPLEMENTATION_UNITS:
- UNIT: <stable id>
  REPO: <verified path>
  GRAPH_SEGMENT: <evidence-backed node and edges>
  TARGET: <MISMATCH or approved actionable gap>
  PRESERVE: <existing partial implementation and MATCH items>
  DEPENDS_ON: <unit ids or none>
  TESTS: <focused Red, Green, Refactor, and regression targets>
  ACCEPTANCE: <observable completion criteria>
DEPENDENCIES: <DAG and ordering rationale>
TASK_CANDIDATES: <raw inputs or none>
WORKFLOW_CANDIDATES: <raw inputs or none>
RESIDUAL_GAPS: <owner, reason, and follow-up, or none>
NEXT_EXPLICIT_COMMAND: crew:task | crew:workflow | none
ARTIFACTS: none
```

## Rules

- Read-only: never edit application code, repositories, issues, or external systems.
- Preserve the supplied parity scope and repository set; scope expansion requires new evidence.
- Existing partial implementations are inventory, not proof of completion.
- Generated artifacts are excluded unless the user explicitly requests generated output.
- Implementation completion criteria always include focused verification and a follow-up
  same-scope parity check, or an explicitly accepted residual gap.
- Never present `crew:run` as an execution command.
