# Framework Review Round 24

Date: 2026-05-24

Task ID: `20260524-074458-0`

Scope
: Operational review against architecture, performance, quality, reliability,
memory governance, security, observability, cost efficiency, developer
experience, and long-term scalability. This round focused on closing the Round
23 residual risk: reviewer approval classification required `QUALITY_METRICS:`,
but completed-task quality-loop evidence still counted reviewer approval from
plain `REVIEW: APPROVED` progress events.

## Review Method

- Entered the review through `crew run` and recorded a resumable internal
  handoff.
- Reviewed reviewer approval classification, pipeline quality-loop validation,
  repair completion gates, and host-bridge quality-loop fixtures.
- Tested whether completed mutating tasks could still pass quality-loop checks
  with reviewer approval text but no quality-metrics artifact.

## Finding

`reviewer-loop-decision.py` blocked missing `QUALITY_METRICS:` in direct
reviewer responses, but `quality_loop_lib.py` still treated any reviewer
`REVIEW: APPROVED` progress event as approval evidence. That left manual repair,
host bridge completion, and report quality checks able to accept completed
mutating tasks without a concrete evaluator-labeled quality metrics artifact.

## Improvements Delivered

- Added `QUALITY_METRICS:` parsing to `quality_loop_lib.py`.
- Changed reviewer approval evidence so a progress event counts only when it
  includes a `QUALITY_METRICS:` pointer and the referenced file exists.
- Added explicit failure signal
  `missing_reviewer_quality_metrics_artifact`.
- Added diagnostic count
  `reviewer_approved_without_quality_metrics_count`.
- Updated Python and integration quality-loop fixtures to create
  `context/quality-metrics.json`.
- Added regression coverage proving a reviewer approval pointing at a missing
  metrics artifact fails completed-task quality-loop validation.
- Added framework readiness control
  `pipeline_quality_metrics_completion_gate`.

## Verification

- `python3 -m pytest -q tests/python/test_quality_loop_pipeline_check.py`
- `python3 -m pytest -q tests/python/test_quality_loop_gate.py`
- `python3 -m pytest -q tests/python/test_memory_reporting_safeguards.py`
- `python3 -m pytest -q tests/python/test_framework_review_check.py`
- `python3 core/scripts/framework-review-check.py --format text`

## Residual Risk

Progress events now require a resolvable quality-metrics artifact, but the
artifact contents are validated by `validate-state-schema.py`, not by
`quality_loop_lib.py` itself. A future hardening round should make the
completion gate call the schema validator or directly validate the quality
metrics payload before counting approval evidence.
