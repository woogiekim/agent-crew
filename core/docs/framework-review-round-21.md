# Framework Review Round 21

Date: 2026-05-24

Task ID: `20260524-063603-0`

Scope
: Operational review against architecture, performance, quality, reliability,
memory governance, security, observability, cost efficiency, developer
experience, and long-term scalability. This round focused on the factual
reliability metric residual risk from Round 20.

## Review Method

- Entered the review through `crew run` and recorded a resumable internal
  handoff.
- Ran static, runtime, and host doctor checks.
- Reviewed the Round 20 residual risk around hallucination/factuality metrics.
- Inspected telemetry aggregation and quality-metric test coverage.

## Finding

1. Round 20 exposed `hallucination_signal_rate`, but the metric still relied on
   task/blocker text signals. That is useful as a fallback, but it is too weak
   for factual reliability governance because text matching cannot distinguish:

   - a real hallucination found by a reviewer,
   - a task merely discussing hallucination prevention,
   - a false positive that was reviewed and cleared.

2. `crew cancel` and `crew repair --status cancelled` wrote
   `current_phase=cancelled` and `host_bridge_status=manual_fallback_cancelled`,
   but `register.schema.json` still lacked those enum values. That left
   cancelled handoffs as a runtime state that was not fully represented by the
   schema contract.

## Improvements Delivered

- Added optional evaluator-labeled quality metrics at
  `{TASK_DIR}/context/quality-metrics.json`.
- Added `core/schemas/quality-metrics.schema.json` with explicit fields:
  - `hallucination_detected`
  - `rollback_performed`
  - `human_intervention_required`
  - `factuality_review`
  - `evidence_paths`
- Updated telemetry aggregation to prefer evaluator labels before weaker
  task/blocker text-signal fallbacks.
- Added regression coverage proving evaluator labels can clear false-positive
  hallucination/rollback text signals while still recording human intervention.
- Added a framework review control so evaluator-labeled quality metrics remain
  part of the operational readiness gate.
- Updated `register.schema.json` so `cancelled` and
  `manual_fallback_cancelled` are first-class schema-valid terminal values.
- Added schema regression coverage for cancelled register state.

## Verification

- `python3 -m pytest -q tests/python/test_telemetry_aggregate.py`
- `python3 -m pytest -q tests/python/test_framework_review_check.py`
- `python3 -m pytest -q tests/python/test_validate_state_schema.py`
- `python3 core/scripts/framework-review-check.py --format text`
- `bash core/bin/crew doctor --mode all --format text`

## Residual Risk

The framework now has a structured place for evaluator labels, but stage agents
must still be taught to emit `context/quality-metrics.json` consistently during
review/factuality workflows. Until that rollout is complete, telemetry falls
back to task/blocker text signals when labels are absent.
