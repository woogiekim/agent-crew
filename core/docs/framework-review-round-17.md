# Framework Review Round 17

Date: 2026-05-23

Task ID: `20260523-140213-0`

Scope
: Operational review against architecture, performance, quality, reliability,
memory governance, security, observability, cost efficiency, developer
experience, and long-term scalability. This round specifically verifies
automatic issue reporting for user-visible issues and verifies that missing host
bridge configuration no longer creates sudden stalled runs.

## Review Method

- Re-ran the static framework governance check.
- Re-ran full Python regression tests.
- Re-ran native CLI integration tests.
- Re-ran automatic issue reporting hook tests.
- Manually reproduced no-bridge `crew run` behavior and Korean input
  normalization behavior.

## Findings

1. Direct-agent Korean normalization was fixed in Round 16 follow-up, but
   native `crew run "Korean task"` still had a separate path that could write
   raw Korean into `register.json`, `pipeline.json`, `result.md`, and
   progress state.
2. Missing `AGENT_CREW_HOST_BRIDGE_COMMAND` no longer blocks the runtime after
   the handoff-ready change, but this needed to be captured as an explicit
   governance control so future changes cannot reintroduce the stall pattern.
3. Automatic issue reporting already captured user-reported and structured
   infrastructure failures, but `handoff_ready` needed an explicit regression
   case so normal resumable handoffs are not reported as bugs.

## Improvements Delivered

- Added a `crew run` Korean normalization hard gate:
  - Hangul task input creates a `korean-normalizer` handoff first.
  - `register.json`, `pipeline.json`, `result.md`, and progress state use an
    English normalization instruction.
  - Raw Korean is retained only as `RAW_TASK` for the normalizer contract.
- Extended framework governance checks with:
  - `no_bridge_handoff_ready_fallback`
  - `korean_input_gate_all_entrypoints`
- Extended automatic issue reporting regression coverage so
  `STATUS: handoff_ready` with `HOST_BRIDGE: internal_handoff_ready` is ignored
  as a normal resumable state.

## Verification

- `bash tests/shell/test_crew_cli.bash -n`
- `bash tests/shell/test_auto_issue_reporter.bash -n`
- `python3 -m pytest tests/python -q`
- `python3 core/scripts/framework-review-check.py`

Expected outcomes:

- Korean input is normalized before downstream `crew run` or `crew agent`
  handoff.
- Missing external host bridge command produces `STATUS: handoff_ready`, not a
  blocked/stalled failure.
- Automatic issue reporting records real agent-crew issues and infrastructure
  blockers while ignoring normal resumable handoffs.

## Residual Risk

- The native fallback creates a normalizer handoff and requires the host runtime
  to produce `NORMALIZED_TASK` before the downstream task is re-run. That is
  intentional until the framework has a deterministic local Korean translation
  engine.
- Hosted execution still depends on host prompt compliance after the
  normalization handoff, but raw Korean is no longer written as the canonical
  downstream task.
