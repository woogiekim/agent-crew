# Framework Review Round 20

Date: 2026-05-24

Task ID: `20260524-042624-0`

Scope
: Operational review against architecture, performance, quality, reliability,
memory governance, security, observability, cost efficiency, developer
experience, and long-term scalability. This round focused on whether the
framework exposes the required quality metrics as operator-ready telemetry.

## Review Method

- Entered the review through `crew run` and recorded a resumable internal
  handoff.
- Ran static, runtime, and host doctor checks.
- Checked the framework review control set.
- Reviewed telemetry output against the guideline's required quality metrics.

## Finding

Telemetry exposed raw task counts, retry totals, blockers, token totals, and
tool failures, but it did not provide a compact operational-quality block for
the required metrics:

- success rate
- retry rate
- hallucination signal rate
- rollback frequency
- human intervention rate

This made the metrics available only indirectly, which weakens long-term
operational governance because operators must reconstruct the rates manually.

## Improvements Delivered

- Added `summary.operational_quality` to `telemetry-aggregate.py`.
- Added stable JSON fields for:
  - `success_rate`
  - `retry_rate`
  - `hallucination_signal_rate`
  - `rollback_frequency`
  - `rollback_rate`
  - `human_intervention_rate`
  - `tool_failure_rate`
- Added text telemetry rendering for the operational-quality summary.
- Added regression coverage for the new quality metrics.
- Added a framework review control so required operational quality metrics are
  not accidentally removed.

## Verification

- `python3 -m pytest -q tests/python/test_telemetry_aggregate.py`
- `python3 -m pytest -q tests/python/test_framework_review_check.py`
- `python3 core/scripts/framework-review-check.py --format text`
- `bash core/bin/crew doctor --mode all --format text`

## Residual Risk

`hallucination_signal_rate` is currently a signal-derived metric based on
recorded blocker/task labels. It does not claim to independently prove factual
hallucination. Stronger measurement should come from evaluator-labeled review
outcomes once the framework has a larger golden dataset of factuality failures.

