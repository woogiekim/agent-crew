# Framework Review Round 22

Date: 2026-05-24

Task ID: `20260524-065135-0`

Scope
: Operational review against architecture, performance, quality, reliability,
memory governance, security, observability, cost efficiency, developer
experience, and long-term scalability. This round focused on closing the Round
21 residual risk: evaluator-labeled quality metrics existed for telemetry, but
review agents were not yet required to emit them.

## Review Method

- Entered the review through `crew run` and recorded a resumable internal
  handoff.
- Reviewed the reviewer contract, telemetry aggregation, state-schema
  validation, and framework readiness controls.
- Checked whether `context/quality-metrics.json` was only a passive telemetry
  input or a governed reviewer-stage artifact.

## Finding

Round 21 added `core/schemas/quality-metrics.schema.json` and made telemetry
prefer evaluator labels over text-signal fallbacks. However, the reviewer agent
contract did not yet require writing `context/quality-metrics.json`, and
`validate-state-schema.py` did not validate the artifact when present. That left
factual reliability metrics vulnerable to partial adoption: telemetry supported
labels, but workflows could complete without a reviewer-labeled quality surface.

## Improvements Delivered

- Added a reviewer Step 3.5 requiring
  `{TASK_DIR}/context/quality-metrics.json` before return.
- Added a `QUALITY_METRICS:` return line so supervisor logs and human operators
  can locate the evaluator-labeled quality artifact.
- Documented conservative label semantics for hallucination, rollback, human
  intervention, and factuality review status.
- Extended `validate-state-schema.py` with optional task-file validation:
  `context/quality-metrics.json` is ignored when absent but schema-validated as
  a hard error when present.
- Added regression tests for valid and invalid quality-metrics artifacts.
- Added a framework review control that fails if reviewer output, schema
  validation, or tests stop enforcing this quality-metrics emission contract.

## Verification

- `python3 -m pytest -q tests/python/test_validate_state_schema.py`
- `python3 -m pytest -q tests/python/test_framework_review_check.py`
- `python3 core/scripts/framework-review-check.py --format text`

## Residual Risk

The reviewer contract now requires the metrics artifact, but supervisor parsing
does not yet block a reviewer that omits `QUALITY_METRICS:`. A future hardening
round should make reviewer-loop parsing enforce the return line and verify that
the referenced file exists before accepting a reviewer stage as complete.
