# Framework Review Round 18 - Claude Performance Follow-Up

Date: 2026-05-24
Scope: Operational review follow-up for Claude execution slowness, with focus on
hook overhead, installed Claude asset size, update latency, observability, and
deterministic guardrails.

## Findings

1. `crew update --local` already fast-skips a true no-op update through the
   fingerprint path. Measured locally, the no-op path completed in about 0.54s
   wall time while reporting a 1s phase due to shell `SECONDS` granularity.
2. Claude host diagnostics previously had no direct budget check for installed
   `~/.claude/agent-crew`, `~/.claude/agents`, largest agent prompt size, file
   count, or registered hook timeout total. This made "Claude is slow" hard to
   diagnose from `crew doctor`.
3. The automatic issue reporter hook ran the native `crew report auto` path even
   for unrelated prompts. On the measured machine, an unrelated prompt cost about
   0.10s before the change. Because Claude runs hooks frequently, that idle-path
   cost adds up.

## Changes

- Added `core/scripts/claude-performance-check.py` to enforce Claude-specific
  performance budgets for installed assets and hook timeout total.
- Added `crew doctor --mode host` integration for Claude performance budgets.
- Added Claude budget fields to `core/evaluations/e2e-slo.json`.
- Extended `framework-review-check.py` so Claude performance diagnostics are a
  static operational readiness control.
- Added a fast reject in `auto-issue-report.sh` so unrelated prompts return
  before starting the crew CLI or Python reporter.

## Current Measurements

- `auto-issue-report.sh` unrelated prompt: about 0.01s after fast reject.
- Claude installed asset budget check:
  - `~/.claude/agent-crew`: about 1619.6KB
  - `~/.claude/agents`: about 610.0KB
  - installed files: 241
  - largest agent file: about 63.5KB
  - agent-crew hook timeout total: 75s

## Verification

- `python3 -m pytest -q tests/python/test_crew_diagnostics.py tests/python/test_framework_review_check.py`
- `bash tests/shell/test_auto_issue_reporter.bash`
- `python3 core/scripts/framework-review-check.py --format text`
- `bash core/bin/crew doctor --mode host --format text`
- `python3 core/scripts/claude-performance-check.py --format text`

