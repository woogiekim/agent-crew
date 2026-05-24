# Phase 1 Validation Framework

This document defines the first-phase validation program for agent-crew. It is
intended to be repeatable, repository-local, and non-destructive: it runs
existing tests and deterministic simulations, then records evidence in a JSON
report.

## Scope

Phase 1 covers five test levels:

- Unit: Python validators, parsers, routing helpers, telemetry, memory, and cost
  logic.
- Smoke: shell-level CLI, hook, setup, guard, status, and memory wrapper checks.
- Integration: fake-host and end-to-end repository scenarios.
- Alpha: deterministic workflow replay and retry-chaos simulations.
- Beta: local SLO, telemetry, memory retrieval, and cost-readiness checks.

The framework is stored in `core/evaluations/phase-1-validation.json`. The
runner is `core/scripts/phase-1-validation.py`.

## Evaluation Criteria

Phase 1 evaluates:

- Performance: command latency, SLO budgets, and startup/runtime overhead.
- Quality: quality gates, reviewer-loop behavior, and workflow replay outcomes.
- Usability: progress reporting, `crew status` rendering, and operator confidence.
- Reusability/memory: memory wrapper behavior, retrieval, and reuse evidence.
- Reliability: repeatability across unit, smoke, integration, and replay checks.
- Observability: progress buffers, register files, telemetry, and diagnostics.
- Recovery behavior: retry budgets, blocker classification, repair/cleanup paths.
- Compatibility: supported host/adapter paths that can be exercised in-repo.
- Security: dangerous-command guards, direct-edit guard, and approval text checks.
- Cost: token/cost aggregation and measurable overhead.

## Running

Run the full phase-one framework:

```bash
python3 core/scripts/phase-1-validation.py \
  --output /tmp/phase-1-validation.json \
  --format text
```

Run only fast planning output:

```bash
python3 core/scripts/phase-1-validation.py --plan-only
```

Run a single level:

```bash
python3 core/scripts/phase-1-validation.py --level alpha --format json
```

The command exits non-zero when any required command fails. Optional commands,
such as memory retrieval against the local long-term memory store, are recorded
as evidence but do not fail the overall run by themselves.

## Evidence Policy

Each command record includes the command, return code, elapsed milliseconds, and
trimmed stdout/stderr tails. The criterion summary maps command outcomes back to
the requested readiness dimensions.

Use the generated JSON report as the durable evidence artifact for a run. If a
check fails, keep the JSON report with the task state and use the command tail to
choose the next focused investigation.
