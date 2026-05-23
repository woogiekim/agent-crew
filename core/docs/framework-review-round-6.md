# Framework Review Round 6

Date: 2026-05-23

Scope: follow-up review against the AI Agent Framework Review Guideline,
focused on live observability and deterministic retry/blocker taxonomy reuse.

## Findings

1. Round 5 added deterministic retry-chaos fixtures, but production telemetry
   still could not prove that real `progress.buffer.jsonl` retry and blocker
   events used the same failure vocabulary.
2. The telemetry aggregator counted retries and blockers, but it did not reject
   drift such as a new ad hoc retry reason that is absent from the governed
   retry-chaos fixture.
3. Runtime auto-refresh installed replay and chaos checkers, but did not yet
   install a live telemetry taxonomy checker for operator diagnostics.

## Changes

- Added `core/scripts/telemetry-taxonomy-check.py`, a read-only checker that:
  - loads the retry/blocker taxonomy from `core/evaluations/retry-chaos.json`;
  - scans real task `progress.buffer.jsonl` files;
  - classifies known retry/blocker labels;
  - fails on unknown explicit labels;
  - supports `--require-label` for focused production-run validation.
- Extended `crew doctor` static readiness with
  `observability.telemetry_retry_taxonomy_correlation`.
- Extended runtime auto-refresh and CLI smoke coverage so the checker is
  installed with other runtime assets.
- Added regression coverage for known labels, unknown explicit labels, required
  label enforcement, and invalid fixture handling.

## Remaining Work

- Surface taxonomy distributions in the human-facing `crew telemetry` command,
  not only through the checker.
- Compare taxonomy trends against SLO thresholds over time, so rising
  `host_blocked`, `quality_loop_exhausted`, or crash labels trigger action
  before they become user-visible reliability problems.
