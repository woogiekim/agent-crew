# Framework Review Round 18

Date: 2026-05-24

Task ID: `20260524-024430-0`

Scope
: Operational review against architecture, performance, quality, reliability,
memory governance, security, observability, cost efficiency, developer
experience, and long-term scalability. This round specifically re-verifies
automatic issue reporting, no-bridge resumability, and the new issue-comment
ingestion workflow.

## Review Method

- Entered the review through `crew run` and recorded a resumable internal
  handoff.
- Checked open GitHub issues; none were open at the start of the round.
- Re-ran the static framework governance check.
- Re-ran native CLI regression coverage for normalization, issue ingestion,
  no-bridge handoff-ready behavior, trace, telemetry, update, and repair flows.
- Re-ran Python regression tests.
- Re-ran automatic issue reporter shell regressions.
- Re-ran runtime doctor and cleared stale historical host-bridge blocker state.

## Findings

1. The framework had a `crew issue-ingest` command, but `crew run "resolve #N"`
   did not automatically ingest issue body and comments before planning.
2. This left an operational gap: humans or agents could forget to run
   `crew issue-ingest`, even though issue comments may contain updated
   requirements.
3. Runtime doctor still reported three stale historical `host_bridge_not_invoked`
   tasks from before the handoff-ready fallback fixes.

## Improvements Delivered

- Added automatic issue comment ingestion for `crew run` tasks that reference
  GitHub issues with `#N` or `/issues/N`.
- Refactored issue ingestion so the manual `crew issue-ingest` command and
  automatic `crew run` path share the same evidence builder.
- Persisted ingestion evidence under:

```text
{TASK_DIR}/context/issue-{N}-ingestion.json
```

- Added `issue_comment_ingestion` pointers to `register.json` when referenced
  issues are detected.
- Extended CLI regression coverage for automatic issue comment ingestion before
  planning.
- Extended framework governance checks so comment ingestion must be automatic,
  not just manually invocable.
- Repaired stale historical host-bridge blocker task state after verifying the
  current no-bridge fallback behavior.

## Verification

- `python3 core/scripts/framework-review-check.py`
- `bash tests/shell/test_crew_cli.bash -n`
- `python3 -m pytest tests/python -q`
- `bash tests/shell/test_auto_issue_reporter.bash -n`
- `bash core/bin/crew doctor --mode runtime`
- `git diff --check`

Expected outcomes:

- `crew run "resolve #N"` records issue body/comment ingestion evidence before
  downstream planning.
- `crew issue-ingest N` still works as an explicit manual evidence command.
- Normal no-bridge execution remains resumable as `STATUS: handoff_ready`, not
  a silent stall.
- Automatic issue reporting records real infrastructure blockers while ignoring
  normal resumable handoffs.
- Runtime doctor reports no stale host-bridge blocker tasks.

## Residual Risk

- Automatic issue ingestion currently covers explicit issue references (`#N` or
  `/issues/N`). Broad natural-language phrases such as "all open issues" still
  require a higher-level issue enumeration step before each issue can be
  ingested.
