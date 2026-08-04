---
name: systematic-debugging
description: Diagnose bugs, failing tests, integration mismatches, incidents, and repeated fix failures from first-party evidence before proposing causes or fixes.
loaded_by: backend,frontend,devops,analyst,planner,reviewer
axis: evidence-diagnosis
profile_type: review-policy
detection: bug OR exception OR stack trace OR failing test OR build failure OR integration failure OR flaky OR incident OR root cause OR diagnose OR mismatch OR error OR 오류 OR 장애 OR 실패 OR 원인 OR 불일치 OR 분석
---

# Skill: systematic-debugging

## Purpose

Diagnose bugs, failed checks, integration mismatches, and repeated fix failures
from first-party evidence before proposing root causes or implementation
changes. The skill keeps facts, hypotheses, and fixes separate so agents do not
guess from symptoms.

## Source

Adapted from the Superpowers systematic-debugging workflow and agent-crew's
provider-neutral evidence discipline.

## When to Apply

- A bug, failing test, integration mismatch, flaky behavior, or repeated review
  rejection needs diagnosis before another fix attempt.
- The same surface has failed three times and the next action may need an
  architectural change rather than another local patch.
- The `debugger` agent is selected for a concrete failure signal and must
  diagnose the root cause without mutating the target project source.

## Core Rules

### Phase 1 — Root cause investigation

Collect first-party evidence before proposing a fix. Read the failing test,
error output, relevant code path, recent diff, and any task-local artifacts.
Write the observed failure in concrete terms.

For `debugger`, keep this phase read-only. Existing tests, safe reproduction
commands, log lookups, `git diff`, `git log`, and static analysis are allowed.
Source edits, temporary debugging code, external system or DB changes, deploys,
commits, pushes, merges, and destructive commands are forbidden.

When `TASK_DIR` is present, write structured diagnostic evidence under
`context/debug`, especially `context/debug/reproduction.md` and
`context/debug/evidence.json`. Do not dump raw logs wholesale; record only the
minimum lines, paths, timestamps, and command outputs needed to support the
diagnosis.

### Phase 2 — Pattern analysis

Compare the failing path with nearby working paths. Identify whether the
failure is isolated, repeated across a boundary, or caused by a shared
contract such as path resolution, state shape, schema, routing, or lifecycle
ordering.

### Phase 3 — Hypothesis

State one narrow hypothesis that explains the evidence. Name the file,
function, contract, or workflow phase expected to change and the verification
that should prove the hypothesis.

Record hypotheses separately from facts in `context/debug/hypotheses.md`.
Unverified hypotheses are never memory material.

### Phase 4 — Implement

Only after the hypothesis is explicit, implement the smallest change that
tests the hypothesis. Run the focused verification and update the task evidence.

For `debugger`, Phase 4 is diagnostic close-out, not implementation. Write the
verified root cause to `context/debug/root-cause.md` and the final report to
`context/debug/report.md`. Include a non-mutating recommended next step for an
implementation agent when appropriate, but do not make the fix.

### Three failures means question architecture

After 3 failed fix attempts on the same surface, stop local patching and
question the architecture. Ask whether the stage should be decomposed, the
contract should move, or the workflow should re-plan before the next patch.

## Memory Contract for Debugger

Capture only a verified root cause, and only through the stable agent-crew
memory wrapper at `${AGENT_CREW_HOME}/bin/memory`. Use project Memory:

```bash
MEMORY="${AGENT_CREW_HOME:-${HOME}/.agent-crew}/bin/memory"
"${MEMORY}" capture --layer project --content "<verified root cause summary>"
```

Do not capture raw logs, stack traces, scratch reproduction output, unverified
hypotheses, or one-off noise. Record the capture result in
`context/debug/memory-capture.json`, including the capture ID when present.
If the backend is unavailable or the wrapper times out, report
`backend_unavailable` or `timeout` and do not claim that Memory stored the root
cause.

## Anti-Patterns

- Guessing a fix from an error message without reading the failing code path.
- Repeating the same patch shape after multiple failed attempts.
- Treating reviewer rejection as style feedback when it names a missing PRD
  behavior or broken contract.

## References

- `core/rules/evidence-grounded-reasoning.md`
- `core/rules/quality-loop.md`

## Checklist

- [ ] Failure signal, command, path, and observed behavior are recorded.
- [ ] Relevant code path and nearby working path are compared.
- [ ] Facts and hypotheses are labeled separately.
- [ ] Proposed fix is the smallest change that can test the hypothesis.
- [ ] Verification command and result are captured before claiming resolution.
