# Framework Review Round 23

Date: 2026-05-24

Task ID: `20260524-070857-0`

Scope
: Operational review against architecture, performance, quality, reliability,
memory governance, security, observability, cost efficiency, developer
experience, and long-term scalability. This round focused on hardening the
Round 22 residual risk: reviewer quality metrics were required by the reviewer
contract, but approval classification still accepted `REVIEW: APPROVED` without
verifying the metrics artifact.

## Review Method

- Entered the review through `crew run` and recorded a resumable internal
  handoff.
- Reviewed reviewer output parsing, supervisor retry-loop guidance, retry-chaos
  fixtures, and workflow replay fixtures.
- Tested whether `REVIEW: APPROVED` without `QUALITY_METRICS:` could still be
  classified as approved.

## Finding

`reviewer-loop-decision.py` treated any `REVIEW: APPROVED` line as approval.
That bypassed the Round 22 contract requiring
`{TASK_DIR}/context/quality-metrics.json`. As a result, factual reliability
telemetry could still silently fall back to text signals even when the reviewer
stage claimed approval.

## Improvements Delivered

- Added `QUALITY_METRICS:` parsing to `reviewer-loop-decision.py`.
- Changed approval classification so `REVIEW: APPROVED` is accepted only when
  the reviewer returns a `QUALITY_METRICS:` artifact pointer.
- Added optional `--task-dir` validation so the classifier can reject approvals
  whose quality-metrics path does not resolve to an existing file.
- Added explicit retry reasons:
  - `quality_metrics_missing`
  - `quality_metrics_file_missing`
- Updated supervisor retry-loop guidance to pass `--task-dir` and treat missing
  quality metrics as a quality-loop retry.
- Updated retry-chaos and workflow-replay fixtures so approved reviewer outputs
  include `QUALITY_METRICS: context/quality-metrics.json`.
- Added framework readiness control
  `reviewer_quality_metrics_approval_gate`.

## Verification

- `python3 -m pytest -q tests/python/test_reviewer_loop_decision.py`
- `python3 -m pytest -q tests/python/test_framework_review_check.py`
- `python3 -m pytest -q tests/python/test_retry_chaos_check.py`
- `python3 -m pytest -q tests/python/test_workflow_replay_check.py`
- `python3 core/scripts/framework-review-check.py --format text`

## Residual Risk

The classifier now rejects missing or unresolved quality-metrics artifacts when
`--task-dir` is provided. A future hardening round should make the runtime
stage wrapper persist the raw reviewer response and pass `--task-dir` in every
host adapter path, then add an end-to-end fixture proving a reviewer omission
blocks completion in the full supervisor stage loop.
