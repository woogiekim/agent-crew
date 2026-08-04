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

One independent linear unit may produce a single-task `crew:run` raw-input candidate. Multiple
independent units may produce a multi-task `crew:run` raw-input candidate only when the candidate
includes at least one real parallel group of two or more task entries, an explicit barrier, and a
result policy.

This command MUST NOT silently execute, self-approve, or create a Task or Workflow definition.
It produces candidate raw inputs, then asks the user what to do next. Any
selected execution continues through the explicit `crew:run` entry point (`$crew:run` in Codex,
`/crew:run` in Claude Code, or native `crew run`), where Registry resolution, Candidate Selection,
plan freezing, and Execution Approval occur.

## Post-Plan Next Step

After producing the implementation units, dependency plan, and raw-input candidates, ask the
user what to do next before stopping. This choice is part of the command's output contract; do
not leave the user with only a static plan unless the evidence gate failed or the user cancels.

```text
How would you like to proceed with this parity implementation plan?

1. Continue with `crew:run`
   - Use the selected `crew:run` raw input from this output.
   - Continue through `crew:run` registry resolution, plan freeze, and Execution Approval.
   - Do not mutate files directly from `parity-implement`.
2. Send to another AI session
   - Send the plan, evidence scope, raw-input candidates, and residual gaps to the chosen session.
   - Do not execute the plan in the current session.
3. Revise the plan
   - Ask for the requested changes, revise only the plan/candidates, then show these choices again.
   - Repeat until the user chooses execute, send, cancel, or no-op.
4. Stop here
   - Stop without execution, external handoff, file edits, issue changes, or remote mutation.
```

If the user selects option 3, preserve the original parity evidence and repository scope while
applying only the requested plan edits. If the requested revision would expand scope, require
new parity evidence or return to `parity-check`; do not silently widen the implementation plan.

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
CREW_RUN_CANDIDATES: <single-task or multi-task raw inputs, or none>
RESIDUAL_GAPS: <owner, reason, and follow-up, or none>
NEXT_EXPLICIT_COMMAND: crew:run | crew:interact | none
NEXT_STEP:
- 1 Continue with crew:run
- 2 Send to another AI session
- 3 Revise the plan and show this gate again
- 4 Stop here
ARTIFACTS: none
```

## Rules

- Read-only: never edit application code, repositories, issues, or external systems.
- Preserve the supplied parity scope and repository set; scope expansion requires new evidence.
- Existing partial implementations are inventory, not proof of completion.
- Generated artifacts are excluded unless the user explicitly requests generated output.
- Implementation completion criteria always include focused verification and a follow-up
  same-scope parity check, or an explicitly accepted residual gap.
- Use `crew:run` as the only execution entry point.
- Do not end a successful plan with output only; ask the user what to do next.
- If the user chooses revision, show the same choices again after the revised plan.
