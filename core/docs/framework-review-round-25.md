# Framework Review Round 25

Date: 2026-05-24

Task ID: `20260524-211532-0`

Scope
: Operational review against architecture, performance, quality, reliability,
memory governance, security, observability, cost efficiency, developer
experience, and long-term runtime direction. This round focused on the Round
24 residual risk: completed-task quality-loop gating required a referenced
`QUALITY_METRICS:` artifact, but counted reviewer approval when the referenced
file merely existed.

## Review Method

- Entered the work through the `crew:run` supervisor workflow using the
  supplied task directory and branch.
- Reviewed the static framework readiness gate, prior Round 24 evidence,
  quality-loop completion checks, quality metrics schema, and focused tests.
- Verified the current readiness gate was already green before selecting a
  scoped improvement.

## Finding

`core/scripts/quality_loop_lib.py` checked whether a reviewer approval event
included `QUALITY_METRICS:` and whether the referenced file existed. It did not
parse the artifact or enforce the `core/schemas/quality-metrics.schema.json`
contract before counting approval evidence. That left completed mutating tasks
able to satisfy the completion gate with malformed JSON or schema-invalid
quality labels, while schema validation happened only through a separate
diagnostic path.

## Improvements Delivered

- Added quality metrics artifact parsing and schema-field validation to
  `quality_loop_lib.py`.
- Changed reviewer approval evidence so malformed or schema-invalid metrics
  artifacts no longer count as valid approval.
- Added diagnostic failure signal
  `invalid_reviewer_quality_metrics_artifact`.
- Preserved the existing missing-artifact failure signal
  `missing_reviewer_quality_metrics_artifact`.
- Added regression coverage for malformed JSON and schema-invalid metrics
  payloads.
- Added framework readiness control
  `pipeline_quality_metrics_schema_gate`.

## Verification

- `python3 -m pytest -q tests/python/test_quality_loop_pipeline_check.py`
- `python3 -m pytest -q tests/python/test_framework_review_check.py`
- `python3 core/scripts/framework-review-check.py --format text`

## Residual Risk

The completion gate now validates the quality metrics fields it consumes without
adding a runtime dependency. If the JSON schema grows more complex, the helper
and `validate-state-schema.py` must stay aligned or share a common validator.
