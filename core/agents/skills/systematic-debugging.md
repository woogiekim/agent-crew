# Skill: systematic-debugging

## Source

Adapted from the Superpowers systematic-debugging workflow and agent-crew's
provider-neutral evidence discipline.

## When to Apply

- A bug, failing test, integration mismatch, flaky behavior, or repeated review
  rejection needs diagnosis before another fix attempt.
- The same surface has failed three times and the next action may need an
  architectural change rather than another local patch.

## Core Rules

### Phase 1 — Root cause investigation

Collect first-party evidence before proposing a fix. Read the failing test,
error output, relevant code path, recent diff, and any task-local artifacts.
Write the observed failure in concrete terms.

### Phase 2 — Pattern analysis

Compare the failing path with nearby working paths. Identify whether the
failure is isolated, repeated across a boundary, or caused by a shared
contract such as path resolution, state shape, schema, routing, or lifecycle
ordering.

### Phase 3 — Hypothesis

State one narrow hypothesis that explains the evidence. Name the file,
function, contract, or workflow phase expected to change and the verification
that should prove the hypothesis.

### Phase 4 — Implement

Only after the hypothesis is explicit, implement the smallest change that
tests the hypothesis. Run the focused verification and update the task evidence.

### Three failures means question architecture

After 3 failed fix attempts on the same surface, stop local patching and
question the architecture. Ask whether the stage should be decomposed, the
contract should move, or the workflow should re-plan before the next patch.

## Anti-Patterns

- Guessing a fix from an error message without reading the failing code path.
- Repeating the same patch shape after multiple failed attempts.
- Treating reviewer rejection as style feedback when it names a missing PRD
  behavior or broken contract.

## References

- `core/rules/evidence-grounded-reasoning.md`
- `core/rules/quality-loop.md`
