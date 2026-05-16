---
name: quality-loop
description: >
  Apply to all implementation stages.
  Enforces a validate → fix → re-validate loop until the stage output meets
  the acceptance criteria defined in the PRD, or until the retry limit is reached.
applies-to: backend, frontend, designer, devops, reviewer, supervisor
---

# Quality Loop Rule

Every implementation stage must iterate until its output is verified correct.
Completing once and moving on is not acceptable.

## Loop Protocol

For each stage, repeat the following until **all acceptance criteria pass** or
the retry limit is reached:

- **Validation failure** (criteria checked, output incorrect): retry up to **3 times**.
- **Agent crash** (no STATUS returned at all): retry up to **5 times** before BLOCKED.

```
1. Implement (or review) the assigned work.
2. Verify against acceptance criteria (see below).
3. If any criterion fails → fix the issue, then return to step 2.
   (Validation failure retry counter increments here.)
4. If all criteria pass → report completion.
5. If the stage returns no STATUS → treat as crash, increment crash retry counter,
   and re-invoke the stage from step 1.
6. If the validation retry limit (3) is reached without passing →
   attempt BLOCKED Recovery (see below) before reporting BLOCKED.
7. If the crash retry limit (5) is reached → report BLOCKED with details.
```

## Acceptance Criteria

Treat all of the following as required before a stage is considered complete:

- All items listed in the PRD for this stage are present in the output.
- No obvious regressions introduced (run existing tests / checks if available).
- Expected artifact files exist at their specified paths.
- No TODO, placeholder, or stub left in implementation output.

## Reporting

Include the iteration count in the stage completion report:

```text
STATUS: completed | BLOCKED
ITERATIONS: {n}
ARTIFACTS: {paths}
ISSUES_RESOLVED: {brief list, or "none"}
```

If `BLOCKED`, include:
```text
BLOCKER: {what failed after all retry attempts}
```

## Cost Circuit Breaker

In addition to the validation 3x / crash 5x retry budgets, the supervisor
enforces a **per-task token budget** before every stage spawn and every
retry attempt.

### Budget defaults (overridable)

| Tier      | Default budget (tokens) | Env override                  |
|-----------|------------------------:|-------------------------------|
| `deep`    |                 200,000 | `AGENT_CREW_BUDGET_DEEP`      |
| `balanced`|                 150,000 | `AGENT_CREW_BUDGET_BALANCED`  |
| `light`   |                 100,000 | `AGENT_CREW_BUDGET_LIGHT`     |

The **task-level budget** is `max(tier_budget)` over the tiers of all
agents that have been invoked for the task so far. A pipeline running
`analyst (deep) + backend (balanced) + reviewer (deep)` therefore gets
the deep budget (200,000). Rationale: a small backend stage should not
shrink the headroom of the surrounding deep analysis and review work.

### Thresholds

| Condition (running total / budget) | Action |
|---|---|
| `< 50%` | proceed normally. |
| `≥ 50%` AND not yet warned | **soft warning** — emit one progress line, continue. |
| `≥ 100%` | **hard stop** — return `STATUS: blocked`, `BLOCKER: cost_budget_exceeded`. Skip BLOCKED Recovery. |

The breaker fires **before every stage spawn and before every retry**
(both validation and crash retries). It does **not** fire mid-stage;
once an agent is dispatched, it runs to completion.

The breaker is gated on `cost_tracking == true`. When the capability
is false (or the per-task cost file is missing), the breaker is a
no-op and behavior is identical to the retry-count-only discipline
above.

### Cost data source

Per-call token usage is captured by the adapter via the contract in
`core/rules/capabilities/cost-tracking.md` and aggregated by
`core/scripts/cost-aggregate.py --task-id $TASK_ID --check-breaker`.
The script returns one of `ok` / `warn` / `exceeded` on stdout with
exit code `0` / `1` / `2`, which the supervisor branches on.

### Why "skip BLOCKED Recovery" on a cost overrun

BLOCKED Recovery decomposes a failing requirement into smaller sub-tasks
and retries. A cost overrun is *not* a failure of approach — it is
exhaustion of the operating budget. Splitting into sub-tasks would
continue spending against the same exhausted budget. The correct
operator response is to escalate (raise the env var, simplify the
request, or abort), not to retry smaller.

## Page-Out As Hygiene Operation (Phase 3.5)

The supervisor may invoke the documenter in `MODE=page-out` between
stages when `AGENT_CREW_HANDOFF_AUTO_PAGEOUT == 1` and `handoff.md`
exceeds `AGENT_CREW_HANDOFF_PAGEOUT_THRESHOLD` (default 8000
characters). This is a working-set hygiene operation, not a stage in
the pipeline. It is governed by a relaxed cost and retry policy:

- **Cost accounting.** The page-out invocation IS a real LLM call
  (light tier) and IS counted against the per-task token budget by
  the cost circuit breaker. If the breaker is already at `exceeded`
  when a page-out would otherwise fire, the supervisor SKIPS the
  page-out (logging `HANDOFF_PAGEOUT_SKIPPED | reason=cost_exceeded`)
  and continues with the un-paged handoff. The breaker is not
  re-evaluated specifically for page-out — it uses the same per-stage
  check.
- **Retry budget.** Page-out is **not retried**. If the documenter
  returns `STATUS: BLOCKED` or crashes during a page-out, the
  supervisor logs `HANDOFF_PAGEOUT_FAILED` and continues. Page-out
  does NOT consume validation (3) or crash (5) retries from the
  next stage's budget. Rationale: page-out is hygiene — if it fails,
  the pipeline can still finish with a larger handoff (potentially
  slower or more expensive per-stage prompts, but functionally
  correct).
- **No BLOCKED Recovery.** Decomposition does not apply. There is no
  smaller sub-task that recovers a failed summary — either the
  documenter produced a usable digest or it did not.
- **Out of band of stage retries.** Page-out invocations occur
  between stage spawns, so failures NEVER leak into the
  just-completed or next-to-spawn stage's retry counters.

The default is OFF. When `AGENT_CREW_HANDOFF_AUTO_PAGEOUT` is unset,
none of this section applies — no page-out ever fires.

## BLOCKED Recovery

Before reporting BLOCKED to the orchestrator, the agent must attempt one
decomposition pass:

1. Break the failing requirement into the **smallest possible sub-task** that
   can be verified independently.
2. Implement and verify that sub-task only.
3. If the sub-task passes → continue with the remaining work, resetting the
   validation retry counter.
4. If the sub-task still fails → report BLOCKED with full detail, including
   what was attempted during decomposition.

This decomposition attempt does **not** count toward the validation retry limit.
It is a single additional recovery pass performed only after the primary retry
limit is exhausted.

## Supervisor Enforcement

The supervisor must pass the path to this rule to every stage agent:

```text
QUALITY_RULE_PATH: ~/.agent-crew/rules/quality-loop.md

Read and apply the quality loop rule before reporting stage completion.
```

After each stage returns, the supervisor checks:

- If `STATUS: completed` → continue to next stage.
- If no STATUS returned → treat as crash. Re-invoke the stage (up to 5 crash
  retries). After all crash retries are exhausted, report BLOCKED.
- If `STATUS: BLOCKED` → halt the pipeline and report the blocker to the
  orchestrator.
- If `STATUS: REJECTED` (reviewer-only — Issue #3) → re-loop to the
  most recent implementer stage per the Reviewer Loop-Back Rule below.

## Quality Loop Enforcement (Issue #3)

> **Why this section exists.** A branch was merged with a latent bug a
> proper test run would have caught: `core/bg.py` used
> `tempfile.gettempdir()` (returns `/var/folders/...` on macOS) while
> `hooks/PostToolUse.sh` hardcoded `/tmp/mnemos-bg-check-{uid}.ts`.
> The two paths never matched — the Python ↔ bash throttle silently
> never communicated. The reviewer approved on static analysis alone,
> never running the test suite. This section makes the test-execution
> requirement explicit and the cross-process path check automatic.

### Test execution requirement

The reviewer agent (`core/agents/reviewer.md` § Phase 0 + Phase 1)
MUST execute the project's discovered test suite before approving any
change that touches code files (`*.py`, `*.ts`, `*.tsx`, `*.js`,
`*.jsx`, `*.kt`, `*.java`, `*.go`, `*.rs`, `*.sh`). Static review
alone is no longer sufficient. The reviewer's return block carries a
mandatory `TEST_RUN_RESULT:` line so the supervisor can confirm tests
actually ran (or were intentionally skipped) rather than silently
omitted.

Three rejection signals are part of the reviewer's contract:

| `STATUS: REJECTED REASON:` | Triggered when | Supervisor action |
|---|---|---|
| `tests_failed`                  | A discovered runner returned non-zero exit. | Re-loop to most recent implementer with the failing tail in handoff.md. |
| `tests_absent_for_code_change`  | No runner discovered AND the diff touches code files. | Re-loop with directive to add a runner config + tests, OR mark the reviewer stage `requires_test_execution: false` with a justification. |
| `cross_process_path_mismatch`   | The diff touches BOTH `*.sh` AND `*.py / *.ts / *.tsx / *.js / *.jsx`, and the two sides disagree on filesystem path literals. | Re-loop with the conflicting path pair in handoff.md. |

### Cross-process path agreement check

When the diff touches BOTH a shell script and a Python/JS/TS module
that writes filesystem paths, the reviewer grep-compares path literals
on both sides and asserts they agree (literal equality OR proven-
equivalent — both sides bound to the same well-known location).
`tempfile.gettempdir()` / `os.tmpdir()` / `os.environ['TMPDIR']` /
`mktemp` are NOT considered provably equivalent to a hard `/tmp/...`
literal — that exact mismatch is the canonical Issue #3 bug.

### Loop-back semantics

The Reviewer Loop-Back Rule (see `core/agents/supervisor-retry.md` §
Reviewer Loop-Back Rule) wires the three rejection reasons above into
the existing **Stage Retry Rule budget**:

- Validation retry budget: **3** (shared with any other validation
  failure path).
- After exhaustion: terminal blocker `quality_loop_exhausted` written
  to `result.md`; no further automatic recovery.
- The re-loop target is the **most recent implementer stage** —
  reviewer, devops, and resolver stages are skipped when walking
  backwards. When no implementer exists (degenerate pipeline of
  `[["reviewer"]]` only) the supervisor halts with
  `BLOCKER: quality_loop_no_implementer_to_retry`.

### Planner opt-out (`requires_test_execution: false`)

The planner MAY set `requires_test_execution: false` on the reviewer
stage's object form for tasks with no testable surface (pure
documentation, `.gitignore` / config-only, comment-only edits). The
supervisor passes this as `REQUIRES_TEST_EXECUTION` to the reviewer,
which skips Phase 0 / Phase 1 / Phase 1.5 entirely and runs only the
static review.

The field defaults to `true` (test execution required) — existing
pipeline.json files without the field continue to work and now opt
their reviewer stage into the test-execution path automatically. See
`core/agents/planner.md` § Reviewer opt-out for the strict criteria
on when the opt-out is appropriate.
