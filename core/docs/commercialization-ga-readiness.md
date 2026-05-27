# Commercialization GA Readiness

This document defines the operational quality gates introduced after the Round
17 commercialization review. Private beta can proceed with these gates in
place; public GA should require the P0/P1 gates to pass consistently.

## Host Bridge Completion

`crew run` writes deterministic task state and a supervisor handoff. Host
adapters that can continue execution automatically may set
`AGENT_CREW_HOST_BRIDGE_COMMAND` or pass `--host-bridge-command`.

The bridge command receives:

- `AGENT_CREW_TASK_ID`
- `AGENT_CREW_TASK_DIR`
- `AGENT_CREW_HANDOFF_PATH`
- `AGENT_CREW_RESULT_PATH`
- `AGENT_CREW_PROJECT_ROOT`

A zero exit status marks the task as `host_bridge_status=auto_completed` and
writes `context/host-bridge-completion.json`. Manual fallback still uses
`crew repair`, which records `host_bridge_status=manual_fallback_completed`.
Telemetry reports both paths separately from true blocked tasks.

## Update Latency SLOs

Use `core/scripts/update-slo-benchmark.py` for update-mode budgets:

```bash
python3 core/scripts/update-slo-benchmark.py \
  --mode noop-local \
  --mode cold-local \
  --mode remote \
  --format json
```

Default budgets live in `core/evaluations/e2e-slo.json`:

- no-op local update: `update_noop_local_budget_ms`
- cold local update: `update_cold_local_budget_ms`
- remote update: `update_remote_budget_ms`

`core/scripts/e2e-slo-check.py --include-update-benchmark` runs no-op and cold
local checks. Add `--include-remote-update` only in CI jobs where network
variance is acceptable. `sync-local-install.sh` prints `update_phase:` lines so
slow updates identify fingerprint, copy, adapter setup, preservation, drift
verification, and fingerprint-write time.

## User Customization Preservation

Every update writes a preservation manifest under:

```text
${AGENT_CREW_HOME}/state/${PROJECT_NAME}/update-preservation/
```

The manifest records before/after hashes for:

- `user/agents`
- `user/skills`
- protected project `.codex/agents/*.toml`
- Claude/Codex settings and project instruction files

Protected project Codex agents exclude agent-crew generated system TOMLs, but
include user-authored TOMLs even when their filenames conflict with a system
agent name. Regression coverage lives in
`tests/python/test_update_preservation_matrix.py` and covers realistic custom
agents, skills, conflicting names, scribe preservation, project Codex TOMLs,
global/project settings, hooks, and instruction files without touching the real
home directory.

## Mnemos Evidence Quality

Repeated workflows should make memory reuse visible, not implicit. Use
`core/scripts/memory-evidence-trace.py` to write:

```text
context/memory-evidence.json
context/memory-evidence.md
```

The trace records retrieved IDs, accepted context IDs, successor memory IDs,
misses, noise, latency, and a compact `memory_quality` score. The answer-quality
gate fails when reusable memory context is present but no memory evidence trace
was produced, or when the final report does not reuse any available memory ID.

## Readiness Evidence Bundle

The 2026-05-27 readiness pass for issue #119 uses explicit generated evidence
under `dist/` instead of ad-hoc local task history:

- `dist/phase-1-validation.json` - phase-one validation report, `passed: true`
- `dist/phase-2-validation.json` - phase-two validation report, `passed: true`
- `dist/readiness-workload.json` - deterministic readiness workload evidence,
  `source: agent-crew-readiness-validation-workload`

Release review should run the readiness gate with those explicit inputs:

```bash
crew readiness gate \
  --validation-report dist/phase-1-validation.json \
  --validation-report dist/phase-2-validation.json \
  --workload-evidence dist/readiness-workload.json \
  --format text
```

The issue #119 evidence run returned `PASS: readiness gate`,
`evidence_mode=explicit_workload_evidence`, and `blockers=0`. Regenerate these
artifacts before publishing a release if source, adapter, or validation logic
changes.

## Implementation Quality Loop

Commercial implementation tasks must prove the quality loop ran before they are
marked complete:

1. TDD implementation
2. reviewer review
3. TDD refactor or remediation
4. reviewer re-review
5. repeat until approval

Manual fallback repair enforces this for mutating tasks. `crew repair --status
completed` requires both artifact evidence and pipeline-event evidence. TDD/test
evidence and reviewer evidence are discovered from standard artifacts such as:

```text
context/tdd_log.md
context/review.md
context/reviewer.md
context/quality-loop.md
context/quality-loop.json
```

Additional artifacts can be provided with `--quality-evidence`. The pipeline
trace is validated from `pipeline.json` and `progress.buffer.jsonl`: completed
mutating tasks must include a TDD-capable implementation stage, a later reviewer
stage, implementer/TDD completion events, and reviewer approval. When a reviewer
returns `STATUS: REJECTED`, `REVIEW: NEEDS_CHANGES`, or `reviewer_rejected`, the
trace must show a later implementer/TDD retry followed by reviewer re-approval.

If an operator must complete a mutating task without that evidence, they must
record an explicit `--quality-bypass-reason`; otherwise the repair is blocked
with `missing_quality_loop_evidence` or `missing_quality_loop_pipeline`.

The report-quality gate applies the same rule to completed implementation
reports and fails on `missing_tdd_evidence`, `missing_reviewer_evidence`, or
the `missing_pipeline_*` / `missing_rework_after_review_rejection` labels
reported by `core/scripts/quality-loop-check.py`.

Runtime auto-completion uses the same fail-closed contract. A fake-host
completion or zero-exit host bridge command cannot complete a mutating
implementation task by itself. For mutating tasks, the host bridge must leave
the provider-neutral quality-loop state in `pipeline.json` and
`progress.buffer.jsonl`; otherwise `crew run` stays blocked with
`missing_quality_loop_pipeline`. When the host bridge does leave valid loop
state, runtime completion preserves that state instead of replacing it with a
supervisor-only completion record.
