# Phase 2 Validation Framework

This document defines the second validation pass for agent-crew. It builds on
the phase-one framework and keeps the same five validation levels:

- Unit: deterministic Python coverage for validation runners, validators,
  routing, telemetry, memory safeguards, cost aggregation, and maintainability.
- Smoke: shell-level CLI, hook, setup, guard, status, and memory-wrapper checks.
- Integration: fake-host and end-to-end repository scenarios.
- Alpha: deterministic workflow replay, retry-chaos, and framework-review
  simulations.
- Beta: local SLO, telemetry, memory retrieval, and cost-readiness checks.

The framework lives in `core/evaluations/phase-2-validation.json`. The runner is
`core/scripts/phase-2-validation.py`.

## Evaluation Dimensions

Phase 2 preserves the baseline dimensions:

- Performance
- Quality
- Usability/progress confidence
- Reusability/memory

It also adds:

- Reliability
- Observability
- Regression safety
- Cost efficiency
- Compatibility
- Security/privacy
- Maintainability

Each dimension has a threshold plus recommended follow-up text. The runner
records structured `findings`, `gaps`, and `recommended_follow_up_actions` in
its JSON output.

## Running

Define the next pass without executing commands:

```bash
python3 core/scripts/phase-2-validation.py --plan-only --format text
```

Run the fast unit-level pass:

```bash
python3 core/scripts/phase-2-validation.py \
  --level unit \
  --output /tmp/phase-2-validation-unit.json \
  --format text
```

Run all configured phase-two levels:

```bash
python3 core/scripts/phase-2-validation.py \
  --output /tmp/phase-2-validation.json \
  --format text
```

Optional beta evidence, such as memory retrieval against a populated local
memory store, is recorded as provisional when it fails. Required command
failures make the overall run fail and appear in both `gaps` and
`recommended_follow_up_actions`.

## Evidence Policy

Each command record includes command, return code, elapsed milliseconds, and
trimmed stdout/stderr tails. Keep the JSON report under the task context when
running inside a supervisor workflow.

Canonical downstream task text must be normalized before it is written into
pipeline state. The phase-two validation report should refer to the normalized
task statement, not raw Korean input.
