# Framework Review Round 4

Date: 2026-05-23

Scope: follow-up review against the AI Agent Framework Review Guideline, focused
on deterministic replay and golden workflow testing.

## Findings

1. Prior rounds added SLO, quality, capability, and security gates, but there
   was no compact golden fixture proving that the same workflow input produces
   the same validator tool flow, expected blocker/failure labels, and state
   transitions.
2. The existing tests verified individual controls, while deterministic replay
   needed a single operator-facing check that ties schema validation, TDD
   planning, capability preflight, and terminal state together.
3. Negative cases were especially important: missing TDD metadata and recursive
   delegation should be expected blocked outcomes, not ad hoc failures.

## Changes

- Added `core/evaluations/workflow-replay.json` with golden happy-path and
  blocked-path workflow cases.
- Added `core/scripts/workflow-replay-check.py`, which replays the fixture
  without an LLM and verifies:
  - expected validator tool flow and return codes;
  - expected quality/capability failure labels;
  - allowed explicit state transitions;
  - expected terminal workflow outcome.
- Extended `crew doctor` readiness checks with
  `reliability.deterministic_workflow_replay`.
- Extended runtime auto-refresh and CLI smoke coverage so the checker and
  fixture are installed with the rest of the runtime assets.
- Added regression tests that prove replay passes the current fixture and fails
  on tool-flow or state-transition drift.

## Remaining Work

- Add a memory GC/eviction command that operationalizes the memory lifecycle
  beyond policy and retrieval SLO checks.
- Consider a richer custom-agent capability declaration format so user-owned
  agents can opt into explicit non-default capability profiles.
