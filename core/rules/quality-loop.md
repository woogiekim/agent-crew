---
name: quality-loop
description: >
  Apply to all implementation stages.
  Enforces a validate → fix → re-validate loop until the stage output meets
  the acceptance criteria defined in the PRD, or until the retry limit is reached.
applies-to: backend, frontend, designer, devops, qa-owner, reviewer, supervisor
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
- Any analysis, judgment, review, or planning artifact satisfies
  `core/rules/evidence-grounded-reasoning.md`: it cites first-party evidence
  with `file:line`, task-artifact paths, or `tool-output` where applicable, and
  shows an explicit evidence-to-inference-to-conclusion flow.

## 100% Test Coverage Ownership

For mutating code work, "100% test coverage" means every new or modified
executable behavior introduced by the stage is covered by automated tests before
the stage can be considered complete.

Coverage has three distinct owners:

- **Planner / analyst** owns pipeline shape. It must emit
  `tdd_parallel: true` for every code implementation stage and keep a
  deterministic quality gate after that stage: either a solo reviewer, or
  QA verify followed by a solo reviewer. This keeps coverage gaps and QA
  defects tied to one remediation target.
- **Test-writer** owns coverage planning and test creation. It must write or
  update `{TASK_DIR}/context/test-coverage.md` with a changed-surface coverage
  matrix mapping each PRD acceptance criterion, entry point, public method,
  branch, and documented failure mode to one or more test cases.
- **Implementation agents** (`backend`, `frontend`, or custom implementers)
  own keeping implementation code inside that coverage matrix. If they add a
  behavior, branch, public method, error path, or edge case that is not covered
  by the test-writer's tests, they must add the missing test before committing.
- **Reviewer** owns enforcement. It must reject code changes when the changed
  executable surface is not fully covered, when the coverage matrix is missing,
  or when an exception is asserted without justification.

When the project has line or branch coverage tooling, use it and require 100%
coverage for changed executable files and changed branches. Whole-repository
coverage may be lower because of legacy code, but the changed surface for this
task must be fully covered.

When no coverage tooling exists, the fallback is the reviewer-verified
traceability matrix in `{TASK_DIR}/context/test-coverage.md`. The matrix must
prove changed-surface coverage by listing:

- PRD acceptance criterion or documented behavior.
- Changed entry point / public method / component / CLI flag / endpoint.
- Success path test.
- Failure, boundary, or branch test.
- Test file and test case name.

Permitted exceptions are narrow: generated code, dead compatibility shims,
unreachable defensive branches, or external side effects that cannot be tested
without unsafe credentials or infrastructure. Every exception must appear in
`context/test-coverage.md` and in the review report with
`COVERAGE_EXCEPTION: {path_or_case} — {reason}`.

Reviewer rejection signals:

| Reviewer signal | Triggered when | Supervisor action |
|---|---|---|
| `STATUS: REJECTED REASON: coverage_below_100` | Coverage tooling or the matrix shows an uncovered changed executable behavior. | Re-loop to the target implementation/TDD stage with the missing coverage item. |
| `STATUS: REJECTED REASON: missing_coverage_evidence` | Code changed but neither coverage report nor `context/test-coverage.md` proves full changed-surface coverage. | Re-loop with directive to add coverage evidence and tests. |
| `STATUS: REJECTED REASON: coverage_exception_unjustified` | A coverage exception is claimed without a narrow, auditable reason. | Re-loop with directive to test the case or document a valid exception. |

## Confirmed Finding Register

When any agent records a confirmed defect, review finding, QA defect,
resolver concern, or repair finding, it must persist that item in
`{TASK_DIR}/context/finding-register.json`. Markdown reports are not the
source of truth for finding lifecycle; they should cite the register ids.

The register accepts this shape:

```json
{
  "schema_version": 1,
  "findings": [
    {
      "id": "F-001",
      "title": "short stable title",
      "severity": "P1",
      "status": "open",
      "source": {"artifact": "context/review.md"},
      "affected": [{"file": "path", "function": "optional"}],
      "recommended_fix": "specific remediation",
      "verification": {
        "test_targets": ["tests/path.py::test_case"]
      },
      "owner": "backend"
    }
  ]
}
```

Valid statuses:

- `open` — nonterminal; completion must not pass while this remains.
- `fixed`, `accepted-risk`, `moved-to-issue`, `out-of-scope`,
  `false-positive` — terminal. Terminal findings still need focused test
  targets or an explicit `test_exception`, `verification_exception`, or
  `coverage_exception`.
- `deferred-minor` — terminal, **auto-promoted**, **owner-exempt**. The
  reviewer assigns this status from its Step 4.5 MINOR auto-promotion flow
  (see `core/agents/reviewer.md` § Step 4.5) when every finding in the
  current review is severity `MINOR`. Pipeline proceeds (no loop-back),
  the supervisor appends a `DEFERRED_MINOR:` pointer block to `handoff.md`,
  and the finding is carried forward into the next handoff. No follow-up
  owner or remediation issue is required — `deferred-minor` is a
  by-design parking status. The entry still needs focused
  `verification.test_targets` OR
  `verification.verification_exception: "deferred-minor"`.

The canonical allowed-status set is the Python set
`FINDING_TERMINAL_STATUSES` in `core/scripts/quality_loop_lib.py`. This
markdown list mirrors that set (single source of truth = the Python set;
this documentation must be kept in lock-step with it).

Reviewer severity gate (cross-reference): the reviewer emits
`REVIEW: NEEDS_CHANGES` only when at least one finding is severity
`CRITICAL` or `IMPORTANT`. When every finding is `MINOR`, the reviewer
emits `REVIEW: APPROVED` plus a `MINOR_DEFERRED: <count> ids=<...>`
annotation and upserts each MINOR finding into `finding-register.json`
with `status: "deferred-minor"` before returning. See
`core/agents/reviewer.md` § Step 4.5 and
`core/agents/supervisor-retry.md` § Reviewer Loop-Back Rule for the
end-to-end contract.

Completion and repair gates reject:

| Failure label | Trigger |
|---|---|
| `invalid_finding_register` | Present register has invalid schema, missing required fields, or unknown statuses. |
| `unresolved_finding_register_entries` | Any finding remains `open`. |
| `missing_finding_test_mapping` | A finding lacks focused test targets and lacks an explicit verification exception. |
| `missing_finding_owner_or_followup` | Accepted-risk, moved-to-issue, or out-of-scope finding lacks owner/follow-up/resolution metadata. |

Completion output must distinguish **new findings in this stage** from
**existing unresolved findings**. Text such as "No new P0/P1 findings" is not
approval when `finding-register.json` still has `open` entries.

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
| `xhigh`   |                 300,000 | `AGENT_CREW_BUDGET_XHIGH`     |
| `deep`    |                 200,000 | `AGENT_CREW_BUDGET_DEEP`      |
| `balanced`|                 150,000 | `AGENT_CREW_BUDGET_BALANCED`  |
| `light`   |                 100,000 | `AGENT_CREW_BUDGET_LIGHT`     |

The **task-level budget** is `max(tier_budget)` over the tiers of all
agents that have been invoked for the task so far. A pipeline running
`analyst (xhigh) + backend (deep) + reviewer (xhigh)` therefore gets
the xhigh budget (300,000). Rationale: a lower-tier implementation stage
should not shrink the headroom of the surrounding highest-impact analysis
and review work.

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
- If `STATUS: REJECTED` or `REVIEW: NEEDS_CHANGES` (reviewer-only)
  → re-loop to the target implementation/TDD stage per
  the Reviewer Loop-Back Rule below.
- If `QA_STATUS: needs_changes` (qa-owner verify only)
  → re-loop to the preceding implementation/TDD stage per the QA Verify
  Loop-Back Rule.

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

Reviewer rejection signals include:

| Reviewer signal | Triggered when | Supervisor action |
|---|---|---|
| `STATUS: REJECTED REASON: tests_failed` | A discovered runner returned non-zero exit. | Re-loop to the target implementation/TDD stage with the failing tail in handoff.md. |
| `STATUS: REJECTED REASON: tests_absent_for_code_change` | No runner discovered AND the diff touches code files. | Re-loop with directive to add a runner config + tests, OR mark the reviewer stage `requires_test_execution: false` with a justification. |
| `STATUS: REJECTED REASON: cross_process_path_mismatch` | The diff touches BOTH `*.sh` AND `*.py / *.ts / *.tsx / *.js / *.jsx`, and the two sides disagree on filesystem path literals. | Re-loop with the conflicting path pair in handoff.md. |
| `STATUS: REJECTED REASON: missing_verification_evidence` | An implementer stage (`backend`, `frontend`, `test-writer`, generic implementer) returned `STATUS: completed` but its return block lacks a `VERIFIED:` line, OR the line does not match the grammar in `core/rules/self-verification.md`, OR the line uses a `skipped:*` form with no matching `{TASK_DIR}/context/tdd-exception.md`. | Re-loop to the target implementation/TDD stage with directive to re-run the test/build command and emit a valid `VERIFIED:` line. |
| `STATUS: REJECTED REASON: coverage_below_100` | Coverage tooling or the coverage matrix shows uncovered changed executable behavior. | Re-loop with the missing coverage item in handoff.md. |
| `STATUS: REJECTED REASON: missing_coverage_evidence` | Code changed but no coverage report or `context/test-coverage.md` proves full changed-surface coverage. | Re-loop with directive to add coverage evidence and tests. |
| `STATUS: REJECTED REASON: coverage_exception_unjustified` | A coverage exception is broad, unauditable, or not tied to a concrete changed path/case. | Re-loop with directive to test the case or document a valid exception. |
| `REVIEW: NEEDS_CHANGES` | Static or streaming review found correctness, coverage, architecture, security, or quality issues. | Re-loop to the target implementation/TDD stage with the issue list from `context/review.md`. |

### Implementer self-verification gate (cross-reference)

The `missing_verification_evidence` signal above enforces the
implementer-side discipline defined in `core/rules/self-verification.md`.
Every non-reviewer implementer (`backend`, `frontend`, `test-writer`,
and any generic implementer) MUST emit a `VERIFIED:` line on its
completion report:

```text
VERIFIED: tests=<RESULT> cmd=<CMD> exit=<CODE>
```

where `<RESULT>` is `<N>/<M>` (passing/total integers) or
`skipped:<reason>` with `<reason>` ∈ `{no_runnable_harness, opt_out}`.

The reviewer treats a stage as exempt from this gate when either of
the following holds:

1. **Planner opt-out.** The reviewer stage was passed
   `REQUIRES_TEST_EXECUTION: false` (planner set
   `requires_test_execution: false` on the reviewer stage object).
   `VERIFIED: tests=skipped:opt_out cmd=none exit=0` is automatically
   valid.
2. **Skip form with recorded exception.** The implementer emitted
   `VERIFIED: tests=skipped:<reason> cmd=none exit=0` AND
   `{TASK_DIR}/context/tdd-exception.md` exists and records the
   reason for the skip.

The optional enforcement script
`core/scripts/check-verification-evidence.py` (stdlib-only Python 3)
mechanically validates the `VERIFIED:` line's shape and is invoked by
the reviewer during its quality-loop pass.

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
Reviewer Loop-Back Rule) wires the rejection signals above into the
existing **Stage Retry Rule budget**:

- Validation retry budget: **3** (shared with any other validation
  failure path).
- After exhaustion: terminal blocker `quality_loop_exhausted` written
  to `result.md`; no further automatic recovery.
- For code-review stages, the re-loop target is the implementation/TDD stage
  immediately before the reviewer, or the implementation/TDD stage immediately
  before a `qa-owner` verify stage when the reviewer follows QA. The planner
  must emit `implementation -> reviewer` or
  `implementation -> qa-owner(verify) -> reviewer` for every code stage;
  batching multiple implementation stages before one gate is a pipeline
  composition error because it makes remediation target selection ambiguous.
  When no implementation stage exists before the gate, the supervisor halts
  with `BLOCKER: quality_loop_no_implementer_to_retry`.

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
