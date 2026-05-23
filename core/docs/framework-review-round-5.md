# Framework Review Round 5

Date: 2026-05-23

Scope: follow-up review against the AI Agent Framework Review Guideline, focused
on retry chaos testing and simulated tool failure recovery.

## Findings

1. Earlier rounds added capability governance, replay fixtures, and memory
   lifecycle controls, but the framework still lacked a compact golden fixture
   for mixed failure recovery.
2. The retry policy existed in supervisor documentation and unit-level helper
   checks, but there was no operator-facing command proving that token
   truncation, crash retries, reviewer loop-back, host blocked, and host
   cancelled outcomes stay deterministic together.
3. Reviewer rejection handling was tested in isolation; it needed to be part of
   a retry-chaos fixture so quality-loop exhaustion is caught as a governed
   terminal blocker.

## Changes

- Added `core/evaluations/retry-chaos.json` with golden chaos cases for:
  - token truncation resume then success;
  - crash retry budget exhaustion;
  - reviewer retries followed by approval;
  - quality-loop exhaustion;
  - host blocked halt;
  - host cancelled halt.
- Added `core/scripts/retry-chaos-check.py`, which replays the fixture without
  calling an LLM and verifies retry counters, final status, blocker labels, and
  reviewer-loop classifier integration.
- Extended `crew doctor` with `reliability.retry_chaos_recovery`.
- Extended runtime auto-refresh and CLI smoke coverage so the checker and
  fixture are installed with other runtime assets.
- Added regression tests proving current chaos fixture success and failure on
  retry-budget or token-resume drift.

## Remaining Work

- Add richer live telemetry correlation between retry chaos fixture labels and
  real task `progress.buffer.jsonl` events, so production runs can be compared
  against the same golden failure taxonomy.
