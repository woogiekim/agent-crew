# Framework Review Round 19

Date: 2026-05-24

Task ID: `20260524-025906-0`

Scope
: Operational review against architecture, performance, quality, reliability,
memory governance, security, observability, cost efficiency, developer
experience, and long-term scalability. This round focused on user-interrupted
handoffs and whether they remain visible as noisy `running` work after being
superseded.

## Review Method

- Entered the review through `crew run` and recorded a resumable internal
  handoff.
- Checked framework governance controls and runtime doctor output.
- Reviewed recent task telemetry after the user intentionally interrupted a
  superseded review turn.
- Re-ran shell and Python regression coverage.
- Re-ran automatic issue reporting regressions.

## Finding

`crew repair` supported `completed` and `blocked`, while telemetry already
understood `cancelled` as a terminal non-running state. This mismatch meant an
intentionally superseded handoff, such as a user-aborted review retry, could
remain visible as `running` unless it was incorrectly marked completed or
blocked.

That is operationally noisy and weakens user trust because it looks similar to
the prior "agent-crew is stuck" class of failures.

## Improvements Delivered

- Added `cancelled` as a supported `crew repair --status` value.
- Added `manual_fallback_cancelled` host bridge status for intentionally
  superseded handoffs.
- Added `CANCELLED` progress-buffer terminal events.
- Updated `crew repair --help` to document the cancellation use case.
- Added CLI regression coverage proving a superseded handoff can be marked
  cancelled and no longer appears as a running task.
- Marked the interrupted `20260524-025839-0` handoff as cancelled.

## Verification

- `python3 core/scripts/framework-review-check.py`
- `bash tests/shell/test_crew_cli.bash -n`
- `python3 -m pytest tests/python -q`
- `bash tests/shell/test_auto_issue_reporter.bash -n`
- `bash core/bin/crew doctor --mode runtime`
- `git diff --check`

Expected outcomes:

- User-aborted or superseded handoffs have a first-class terminal state.
- Runtime status no longer needs to misuse completed or blocked for intentional
  cancellation.
- Doctor remains clean: no stale state markers and no stale host-bridge blocker
  tasks.

## Residual Risk

- Resolved in follow-up: added `crew cancel [--note TEXT] TASK_ID` as the
  operator-facing wrapper for `crew repair --status cancelled`, with CLI
  regression coverage. Superseded handoffs no longer require operators to know
  the lower-level repair command.
