# Supervisor — Retry, Recovery, Close-out

> This module is read by the `supervisor` agent at the start of Phase 2
> (so the Stage Retry Rule is available while stages dispatch) and again
> at Phase 3 close-out. It holds three concerns:
>
> 1. **Stage Retry Rule** — the validation 3x / crash 5x budget that
>    wraps every stage spawn, plus the P7 capability-gated crash
>    classifier.
> 2. **BLOCKED Recovery** — escalation contract when retry budgets are
>    exhausted or any agent returns `STATUS: BLOCKED`.
> 3. **Phase 3 close-out** — `result.md` write, host-task close, marker
>    cleanup, worktree teardown, final return value to the orchestrator.
>
> Phase names (Phase 0, Phase 1c, Phase 2, Phase 2.5) referenced below
> are defined in `supervisor-bootstrap.md` and `supervisor-stages.md`.

---

## Stage Retry Rule


Every stage invocation (single or parallel) is wrapped in a retry loop.
Retry limits follow the quality-loop rule (`QUALITY_RULE_PATH`):

- **Validation failure** (STATUS returned but criteria not met): up to **3 retries**.
- **Crash** (true agent failure, not a token-limit tail): up to **5 retries**.
- **Token-limit truncation** (run reached the end without a STATUS line but
  produced substantial output, P7): **1 resume** with a checkpoint hint, then
  fall through to the crash retry budget if still no STATUS line.

**Crash detection — two paths converge on the same decision.**

**P7 — preferred path when `HAS_TASK_TOOLS == 1` AND the per-stage host task id
is present** (populated by Phase 1c-bis under `pipeline.json.host_task_ids`):
read the host-detected termination status directly:

```text
STAGE_HOST_STATUS=$(TaskGet(taskId=host_task_ids[i-1][agent_name]).status)
# error    → real crash (no STATUS line in response AND host detected failure)
# blocked  → halt pipeline
# completed → success (re-check response for STATUS:; if absent → token-truncation)
# cancelled → treat as cancellation (halt with STATUS: blocked)
```

This distinguishes "agent died on a missing import in 30 s" (`error`) from
"agent ran 90 % of the way and ran out of tokens" (host says `completed`, but
no `STATUS:` line in the captured response). The latter is **token-limit
truncation**, not a crash — the response so far is preserved, so re-invoking
with a resume hint pointing at `${TASK_DIR}/progress.log` and the latest
`stage_{i}_progress.md` checkpoint usually completes the work in one extra
spawn instead of burning all 5 crash retries.

**Legacy fallback when `HAS_TASK_TOOLS == 0` or the host-task id is absent**:
Any agent invocation that returns without a `STATUS:` line in its response is
treated as a crash. There is no way to distinguish token-limit truncation
from a true crash on this path, so the full 5-retry budget applies uniformly.

Retry logic per agent:

```
# Phase F5: RETRY_ATTEMPT is set at the top of the Phase 2 stage loop
# (supervisor-stages.md). The Stage Retry Rule below bumps it on each
# retry path so log_progress emits carry the correct attempt index in
# the structured buffer (trace_id's 4th segment).
RETRY_ATTEMPT = 1
crash_attempts = 0
token_limit_resumes_used = 0
clarification_attempts = 0
while crash_attempts <= 5:
    invoke agent
    if response contains "STATUS: completed":
        break  # success
    elif response contains "STATUS: plan_ready":
        break  # agent submitted a plan — Phase 2.5 will handle approval
    elif response contains "STATUS: BLOCKED":
        halt pipeline — write blocker to result.md and return STATUS: blocked
    elif response contains "STATUS: needs_clarification":
        clarification_attempts += 1
        if clarification_attempts > 2:
            # fall through to standard BLOCKED path — bounce budget exhausted
            halt pipeline — write blocker to result.md
            BLOCKER: clarification_loop_exhausted
            return STATUS: blocked
        log_progress "RETRY" "attempt {clarification_attempts} — needs_clarification (analyst re-plan)"
        extract CLARIFICATION_REQUEST and CLARIFICATION_DETAIL from response
        spawn analyst agent with CLARIFICATION_REQUEST and the existing TASK_DIR;
          analyst updates pipeline.json / prd.md / handoff.md as needed
        append the analyst's clarification response to handoff.md
        continue   # re-spawn current stage agent — do NOT bump
                   # RETRY_ATTEMPT, do NOT bump crash_attempts
    else:  # no STATUS line — classify
        classification = "crash"
        if HAS_TASK_TOOLS == 1 AND host_task_ids[i-1][agent_name] is set:
            STAGE_HOST_STATUS = TaskGet(taskId).status
            if STAGE_HOST_STATUS == "completed":
                classification = "token_truncation"
            elif STAGE_HOST_STATUS == "blocked":
                halt pipeline — write blocker to result.md and return STATUS: blocked
            elif STAGE_HOST_STATUS == "cancelled":
                halt pipeline — write CANCELLED to result.md and return STATUS: blocked
            # else (error / pending / in_progress): treat as crash

        if classification == "token_truncation" AND token_limit_resumes_used < 1:
            token_limit_resumes_used += 1
            RETRY_ATTEMPT += 1
            log_progress "RETRY" "attempt {RETRY_ATTEMPT} — token_truncation resume"
            re-invoke agent with resume hint:
              "Resume from: {TASK_DIR}/context/stage_{i}_progress.md if present,
               else from {TASK_DIR}/progress.log tail. Continue prior work."
            continue  # do not increment crash_attempts
        else:
            crash_attempts += 1
            RETRY_ATTEMPT += 1
            log_progress "RETRY" "attempt {RETRY_ATTEMPT} — crash"
            if crash_attempts > 5:
                write crash details to {TASK_DIR}/result.md
                return STATUS: blocked (reason: agent crashed after 5 attempts)
            re-invoke agent (pass TASK_DIR/HANDOFF_PATH/QUALITY_RULE_PATH only)
```

Do not silently swallow a crash. After 5 crash failures on the same agent (the
single token-truncation resume does not count against this budget), report
BLOCKED with the agent name and stage index. When `HAS_TASK_TOOLS == 0` or the
host task id is absent, every "no STATUS line" outcome is classified as a
crash — identical to pre-P7 behavior.

`clarification_attempts` is independent of the validation (3) and crash (5)
budgets and has its own hard budget of **2 bounces** per stage. A
`STATUS: needs_clarification` return triggers an analyst re-plan and an
implicit re-spawn of the same stage agent — it never increments
`RETRY_ATTEMPT` or `crash_attempts`. Once two clarification bounces are
exhausted, the supervisor falls through to the standard BLOCKED path with
`BLOCKER: clarification_loop_exhausted`. This keeps a misclassified
ambiguous-plan failure from silently burning the validation budget that
should be reserved for true reviewer-driven re-loops.

### Pre-retry clean state for fan-out units

When the failed agent is a **sub-task fan-out unit** (i.e., the current
stage has `STAGE_UNITS_COUNT >= 2` and the crashing agent carries a
`UNIT_ID`), the supervisor MUST restore the unit's worktree to a clean
state **before** re-spawning. A crashed unit may have left partial
uncommitted changes in its git worktree; retrying against dirty state
risks incorrect behavior or a corrupt commit on the retry path.

Required steps (run immediately after incrementing `crash_attempts`,
before the next `invoke agent` call):

1. For each glob in `UNIT_FILES` (the unit's declared `files` array):
   - `git -C ${UNIT_WORKTREE_PATH} checkout HEAD -- <glob>` — restore tracked
     files that were modified.
   - `git -C ${UNIT_WORKTREE_PATH} clean -fd -- <glob>` — remove untracked
     files / directories that the crashed unit created.

2. Verify the worktree is clean:
   ```bash
   git -C "${UNIT_WORKTREE_PATH}" status --short
   ```
   A non-empty output is a warning (log to `progress.log`) but MUST NOT
   prevent the retry — the unit may have legitimately staged some work
   before crashing, and the glob-scoped cleanup above is best-effort.

These steps are idempotent. When `UNIT_WORKTREE_PATH` no longer exists
(e.g., it was removed by a concurrent cleanup step), skip silently and
proceed with the retry against `PROJECT_ROOT` as a fallback.

See `supervisor-stages.md` § Selective per-unit retry for the bash
implementation that encodes these steps in the fan-out dispatch section.

### Stage Timeout (Phase I11)

Before each stage spawn AND before each retry inside the loop above,
the supervisor checks elapsed wall-clock time for the current stage
against `STAGE_TIMEOUT_SECONDS` (resolved once in Phase 0 from
`AGENT_CREW_STAGE_TIMEOUT_SECONDS`).

The check is **gated on `STAGE_TIMEOUT_SECONDS != 0`**. When the env
var is unset or zero, this subsection is a no-op — the retry loop
above runs unchanged and pre-I11 pipelines see identical behavior.

When `STAGE_TIMEOUT_SECONDS != 0`, run the following block
**immediately before every `invoke agent` call** — once at the top of
the retry loop (covers the initial spawn) and inside both the
`token_truncation` resume branch and the `crash_attempts` retry
branch:

```bash
if [ "${STAGE_TIMEOUT_SECONDS}" != "0" ]; then
  STAGE_ELAPSED=$(( $(date +%s) - ${STAGE_START_EPOCH:-$(date +%s)} ))
  if [ "${STAGE_ELAPSED}" -gt "${STAGE_TIMEOUT_SECONDS}" ]; then
    log_progress "STAGE_TIMEOUT" \
      "stage ${STAGE_INDEX:-?} (${STAGE_AGENT:-?}) elapsed=${STAGE_ELAPSED}s > budget=${STAGE_TIMEOUT_SECONDS}s"
    register_update current_phase blocked
    register_update blocked_by --json '["stage_timeout"]'
    cat > "${TASK_DIR}/result.md" <<EOF
# {TASK}

STATUS: blocked
BLOCKER: stage_timeout
DETAIL: Stage ${STAGE_INDEX:-?} (${STAGE_AGENT:-?}) exceeded the per-stage
        wall-clock budget. elapsed=${STAGE_ELAPSED}s budget=${STAGE_TIMEOUT_SECONDS}s.
        Re-run with AGENT_CREW_STAGE_TIMEOUT_SECONDS adjusted (or unset to
        disable) if the work legitimately requires more time.
EOF
    # Skip BLOCKED Recovery — timeouts indicate the operating budget
    # is wrong, not the approach. Run Phase 3 close-out and return
    # STATUS: blocked to the orchestrator.
    return STATUS: blocked
  fi
fi
```

The hard stop **skips BLOCKED Recovery** for the same reason cost
overruns do (see § Cost Circuit Breaker below) — exhaustion of the
operating budget is not a failure of approach. The operator's correct
response is to escalate: raise `AGENT_CREW_STAGE_TIMEOUT_SECONDS`,
simplify the request, decompose the stage, or abort.

`log_progress` is the helper introduced by `supervisor-bootstrap.md`
Phase 0; `register_update` writes the terminal phase + blocker label
to `register.json` so external tooling can detect timeout without
parsing `result.md`. `STAGE_START_EPOCH` is set per stage in
`supervisor-stages.md` Phase 2 (see the loop variable convention
block); when absent (defensive default), the check measures from
"now" and never fires.

### Reviewer Loop-Back Rule (Issue #3)

When a reviewer stage follows a code implementation stage directly, or follows
a `qa-owner` verify stage that follows a code implementation stage, and returns
either `STATUS: REJECTED` or `REVIEW: NEEDS_CHANGES`, the supervisor MUST
re-loop to that implementation/TDD stage instead of advancing
`completed_stages`.
This is the core commercial quality loop: implement through TDD,
review, remediate/refactor through TDD, re-review, and repeat until
approval or budget exhaustion.

Both reviewer rejection forms are mandatory loop triggers:

| Reviewer return | Triggered when | Re-loop reason |
|---|---|---|
| `STATUS: REJECTED` + `REASON: tests_failed` | A discovered test runner failed. | `tests_failed` |
| `STATUS: REJECTED` + `REASON: tests_absent_for_code_change` | Code changed but no test runner was discoverable. | `tests_absent_for_code_change` |
| `STATUS: REJECTED` + `REASON: cross_process_path_mismatch` | Cross-process path agreement failed. | `cross_process_path_mismatch` |
| `REVIEW: NEEDS_CHANGES` + `REASON: spec_incomplete` | Reviewer found missing PRD acceptance criteria or core behavior. | `spec_incomplete` |
| `REVIEW: NEEDS_CHANGES` + `REASON: code_quality` | Reviewer found blocking maintainability, architecture, security, or quality issues after spec compliance passed. | `code_quality` |
| `REVIEW: NEEDS_CHANGES` | Static or streaming review found correctness, coverage, architecture, security, or quality issues classified as `CRITICAL` or `IMPORTANT`. | `review_needs_changes` |
| `REVIEW: APPROVED` without `QUALITY_METRICS:` | Reviewer omitted the required evaluator-labeled quality artifact pointer. | `quality_metrics_missing` |
| `REVIEW: APPROVED` with missing quality metrics file | Reviewer returned a `QUALITY_METRICS:` path that does not exist. | `quality_metrics_file_missing` |
| `REVIEW: NEEDS_CHANGES` in `verify-prior-must-only` with an unclassified or weakly evidenced new Must | Reviewer violated the re-review contract. | `review_contract_invalid` |

Loop-back fires only on `CRITICAL` or `IMPORTANT` findings. `MINOR`
findings never trigger `REVIEW: NEEDS_CHANGES` — they are auto-promoted
to `deferred-minor` by the reviewer's Step 4.5 flow and carried forward
in `handoff.md` instead. See the § MINOR auto-promotion subsection below
for the supervisor's handoff-append responsibility.

Reviewer re-runs are scoped by review mode:

- `REVIEW_MODE: verify-prior-must-only` is the default after
  `REVIEW: NEEDS_CHANGES` or `STATUS: REJECTED`. The reviewer first verifies
  prior Must findings and the remediation surface.
- `REVIEW_MODE: full-rescan` is used only for the first review, explicit
  operator request, or supervisor-recorded scope expansion.

When appending a retry directive to `handoff.md`, include the selected
`REVIEW_MODE`. In `verify-prior-must-only`, a newly raised Must must include
`NEW_MUST_CLASSIFICATION: regression | missed_existing | severity_escalation |
unclear_requirement` plus concrete first-party evidence. Weak or speculative
new findings remain Should/MINOR and must not consume another Must loop.

Run `core/scripts/reviewer-loop-decision.py --review-mode
verify-prior-must-only` for reviewer retry classification when a re-review is
being evaluated. If the classifier returns `reason=review_contract_invalid` and
`retry_target=reviewer`, re-run the reviewer with the same review mode; do not
return to the implementer and do not decrement the implementation retry budget.
Reviewer-contract retries have a separate hard budget of **2 bounces** per
reviewer stage. Exhaustion blocks with `review_contract_loop_exhausted`, not
`quality_loop_exhausted`, so a malformed reviewer cannot create an implementer
retry loop.

#### MINOR auto-promotion

When the reviewer returns `REVIEW: APPROVED` AND a `MINOR_DEFERRED:`
annotation line (emitted by the reviewer's Step 4.5 when every finding
was severity `MINOR`), the classifier maps the response to
`action=approve` — there is no loop-back. The pipeline proceeds to the
next stage / Phase 3 close-out, but the supervisor MUST append a
`DEFERRED_MINOR:` pointer block to `${TASK_DIR}/handoff.md` BEFORE
advancing `completed_stages` so the deferred entries are carried forward
into the next handoff:

```text
DEFERRED_MINOR:
  register: context/finding-register.json
  ids: F-NNN, F-NNN
  note: Auto-deferred by reviewer; carry into next handoff.
  count: {N}
```

The `ids` and `count` values are parsed from the reviewer's
`MINOR_DEFERRED: <count> ids=<comma_list>` return line. The reviewer's
Step 4.5 has already upserted each finding into
`context/finding-register.json` with `status: "deferred-minor"` and
`severity: "P3"` (see `core/agents/reviewer.md` § Step 4.5), so the
supervisor only writes the pointer block — it does not mutate the
register itself.

`deferred-minor` is a terminal, **owner-exempt** status per
`core/rules/quality-loop.md` § Confirmed Finding Register. No follow-up
owner or remediation issue is required for these entries; the next
handoff merely surfaces them so a future stage or task can address them
opportunistically. The Phase 3 quality-loop completion gate
(`core/scripts/quality-loop-check.py`) accepts `deferred-minor` as a
valid terminal status — see `FINDING_TERMINAL_STATUSES` in
`core/scripts/quality_loop_lib.py`.

When the reviewer returns `REVIEW: APPROVED` without a `MINOR_DEFERRED:`
line (the issue list was empty), behavior is unchanged: the supervisor
advances to the next stage with no handoff-append step. When the
reviewer returns `REVIEW: NEEDS_CHANGES`, the existing loop-back path
fires unchanged — the severity gate sits on the reviewer side, so
`NEEDS_CHANGES` already implies at least one `CRITICAL` or `IMPORTANT`
finding was present.

Use the provider-neutral classifier before deciding whether to advance
or re-loop:

```bash
REVIEW_DECISION=$(python3 "${AGENT_CREW_HOME}/scripts/reviewer-loop-decision.py" \
  --response "${TASK_DIR}/context/reviewer-response.txt" \
  --task-dir "${TASK_DIR}" \
  --review-mode "${REVIEW_MODE:-full-rescan}" \
  --format json)
REVIEW_ACTION=$(printf '%s' "${REVIEW_DECISION}" | python3 -c "import sys,json; print(json.load(sys.stdin)['action'])")
REVIEW_REASON=$(printf '%s' "${REVIEW_DECISION}" | python3 -c "import sys,json; print(json.load(sys.stdin)['reason'])")
REVIEW_DIRECTIVE=$(printf '%s' "${REVIEW_DECISION}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('directive',''))")
```

The classifier maps both `STATUS: REJECTED` and `REVIEW:
NEEDS_CHANGES` to `action=retry`. `REVIEW: APPROVED` maps to
`action=approve` only when the reviewer also returns `QUALITY_METRICS:` and
the referenced quality-metrics artifact exists.

Re-loop logic (executed by Phase 2's stage loop wrapper around the
reviewer stage spawn — runs at the same point in the dispatch flow as
the existing crash-retry path):

```python
# Initialize once before entering the reviewer retry wrapper for this stage:
reviewer_contract_retries = 0

# Inside the stage loop, after the reviewer agent returns:
decision = reviewer_loop_decision(reviewer_response)
if decision.action == "retry":
    reason = decision.reason
    if decision.retry_target == "reviewer":
        reviewer_contract_retries += 1
        log_progress(
            "RETRY",
            f"reviewer_contract attempt {reviewer_contract_retries} — reason={reason}",
        )

        if reviewer_contract_retries > 2:
            log_progress("BLOCKED", "review_contract_loop_exhausted")
            register_update current_phase blocked
            register_update blocked_by --json '["review_contract_loop_exhausted"]'
            write_blocker_to_result_md(
                blocker="review_contract_loop_exhausted",
                detail=f"Reviewer violated the re-review contract "
                       f"{reviewer_contract_retries} consecutive times "
                       f"(reason={reason}).",
            )
            return

        append_directive_to_handoff(decision.directive)
        pipeline.stage_agent_status.pop(str(reviewer_stage_index), None)
        save_pipeline_json()

        continue  # re-run reviewer

    quality_retries += 1                          # shares the validation budget (3)
    log_progress("RETRY", f"attempt {quality_retries} — reviewer_rejected reason={reason}")

    if quality_retries > 3:
        # Stage Retry Rule budget exhausted — terminal blocker.
        log_progress("BLOCKED", "quality_loop_exhausted")
        register_update current_phase blocked
        register_update blocked_by --json '["quality_loop_exhausted"]'
        write_blocker_to_result_md(
            blocker="quality_loop_exhausted",
            detail=f"Reviewer rejected 3 consecutive times "
                   f"(reason={reason}). See ${TASK_DIR}/context/review-tests.md "
                   f"for the most recent failure tail.",
        )
        return  # halts pipeline; Phase 3 close-out runs as normal

    # Append the directive matching `reason` to handoff.md and decrement
    # completed_stages back to the immediately preceding implementation stage
    # so the outer stage loop re-spawns it instead of advancing.
    impl_stage_index = find_preceding_implementation_stage_index()
    append_directive_to_handoff(decision.directive)
    pipeline.completed_stages = impl_stage_index - 1
    pipeline.stage_agent_status.pop(str(impl_stage_index), None)  # clear so retry re-runs
    save_pipeline_json()

    continue  # re-enter the stage loop at the implementer index
```

The `find_preceding_implementation_stage_index()` helper first checks the
stage immediately before the reviewer. If it is an implementation stage, that
stage is the retry target. If the immediately preceding stage is a `qa-owner`
verify stage, the helper checks the stage before QA and requires that stage to
be an implementation/TDD stage. The planner must emit either
`implementation -> reviewer` or `implementation -> qa-owner(verify) -> reviewer`
for every code implementation stage. If a reviewer rejects after multiple
implementation stages were batched, the supervisor must halt with
`BLOCKER: quality_loop_ambiguous_rework_target` rather than guessing. When no
implementer is found (degenerate pipeline of `[["reviewer"]]` only), the
supervisor halts with `BLOCKER: quality_loop_no_implementer_to_retry` —
re-running an empty pipeline cannot produce a different verdict.

The Stage Retry Rule's two pre-existing budgets remain unchanged:

| Budget | Scope | Behavior on exhaustion |
|---|---|---|
| `validation = 3` | Reviewer-driven re-loops (this rule) AND any explicit "validation failure" reported by a stage agent. | Hard stop, `BLOCKER: quality_loop_exhausted`. |
| `crash = 5`      | Stage agent crashes (no STATUS line, host-detected `error`). | Hard stop, crash details to result.md. |
| `clarification = 2` | Implementer-driven plan-clarify bounce (`STATUS: needs_clarification`). Each bounce routes the request to the analyst, then re-spawns the same stage agent. | Hard stop, `BLOCKER: clarification_loop_exhausted`. |

`quality_retries` and `reviewer_contract_retries` are initialized to 0 once
before entering the reviewer retry wrapper for that stage, alongside
`crash_attempts`. The counters are independent
— a reviewer rejection consumes a validation retry; a reviewer crash
consumes a crash retry; a reviewer contract violation consumes only the
reviewer-contract retry budget. They cannot cross-deplete each other.
`REVIEW: NEEDS_CHANGES` is no longer advisory-only; it is a hard quality-loop
retry signal unless the classifier identifies a reviewer-only contract retry.

### QA Verify Loop-Back Rule

When a `qa-owner` stage with `qa_mode=verify` returns
`QA_STATUS: needs_changes`, the supervisor MUST treat it as a validation
failure and loop back to the preceding implementation/TDD stage when the stage
contains `qa_loop_target: "previous_implementation"`.

QA verify loop triggers:

| QA return | Triggered when | Re-loop reason |
|---|---|---|
| `QA_STATUS: needs_changes` | Required TC failed, critical evidence is missing, or PRD behavior does not match the implementation. | `qa_needs_changes` |
| `QA_STATUS: blocked` or `STATUS: BLOCKED` | QA cannot execute meaningful verification because required artifacts or environment are missing. | `qa_blocked` |

Re-loop logic mirrors reviewer rejection and consumes the same validation budget
of 3 retries:

```python
# Inside the stage loop, after the qa-owner verify agent returns:
if qa_status == "needs_changes":
    quality_retries += 1
    log_progress("RETRY", f"attempt {quality_retries} — qa_needs_changes")

    if quality_retries > 3:
        log_progress("BLOCKED", "quality_loop_exhausted")
        register_update current_phase blocked
        register_update blocked_by --json '["quality_loop_exhausted"]'
        write_blocker_to_result_md(
            blocker="quality_loop_exhausted",
            detail="QA verify requested changes 3 consecutive times. "
                   "See ${TASK_DIR}/context/qa-defects.md and "
                   "${TASK_DIR}/context/qa-report.md.",
        )
        return

    impl_stage_index = find_preceding_implementation_stage_index_from_qa_verify()
    append_directive_to_handoff(
        "QA verify requested changes. Read context/qa-defects.md and "
        "context/qa-report.md, then remediate through the TDD implementation stage."
    )
    pipeline.completed_stages = impl_stage_index - 1
    pipeline.stage_agent_status.pop(str(impl_stage_index), None)
    pipeline.stage_agent_status.pop(str(current_qa_stage_index), None)
    save_pipeline_json()

    continue  # re-enter the stage loop at the implementer index
```

If `qa_loop_target` is absent or not `previous_implementation`, halt with
`BLOCKER: qa_loop_target_missing` instead of guessing. A QA verify stage must
be followed by a solo reviewer stage; otherwise planning should already have
failed with `missing_pipeline_reviewer_after_qa_verify`.

### Cost Circuit Breaker

Before each stage spawn AND before each retry inside the loop above,
the supervisor checks the running token total against the per-task
budget. Defined in `core/rules/quality-loop.md` § Cost Circuit Breaker.

The check is **gated on `cost_tracking == true`** (`HAS_COST_TRACKING`
is loaded once in Phase 0 alongside the other capability flags — see
`supervisor-bootstrap.md`). When `HAS_COST_TRACKING == 0`, this
subsection is a no-op: the breaker cannot fire because no cost data
is being recorded, and the retry loop above runs unchanged.

When `HAS_COST_TRACKING == 1`, run the following block **immediately
before every `invoke agent` call** — once at the top of the retry
loop (covers the initial spawn) and inside both the
`token_truncation` resume branch and the `crash_attempts` retry
branch:

```bash
COST_VERDICT=$(python3 "${AGENT_CREW_HOME}/scripts/cost-aggregate.py" \
  --state-dir "${STATE_DIR}" \
  --task-id "${TASK_ID}" \
  --check-breaker 2>/dev/null) || true

case "${COST_VERDICT}" in
  warn)
    if [ -z "${COST_WARNED:-}" ]; then
      COST_JSON=$(python3 "${AGENT_CREW_HOME}/scripts/cost-aggregate.py" \
        --state-dir "${STATE_DIR}" --task-id "${TASK_ID}" --format json)
      COST_TOTAL=$(echo "${COST_JSON}"  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['task']['total_tokens'])")
      COST_BUDGET=$(echo "${COST_JSON}" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['task']['task_budget'])")
      COST_PCT=$(echo "${COST_JSON}"    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['task']['pct_consumed'])")
      log_progress "COST_WARN" "${COST_PCT}% of budget (${COST_TOTAL} / ${COST_BUDGET} tokens)"
      COST_WARNED=1
    fi
    ;;
  exceeded)
    log_progress "COST_BLOCKED" "task token budget exceeded"
    register_update current_phase blocked
    register_update blocked_by --json '["cost_budget_exceeded"]'
    cat > "${TASK_DIR}/result.md" <<EOF
# {TASK}

STATUS: blocked
BLOCKER: cost_budget_exceeded
DETAIL: Per-task token budget reached. See ${STATE_DIR}/cost/${TASK_ID}.jsonl
        and re-run with AGENT_CREW_BUDGET_{TIER} adjusted if intentional.
EOF
    # Skip BLOCKED Recovery (quality-loop rule). Run Phase 3 close-out
    # and return STATUS: blocked to the orchestrator.
    return STATUS: blocked
    ;;
  ok|*)
    : # proceed
    ;;
esac
```

The `COST_WARNED` guard ensures only one soft warning fires per task
even if the loop runs many iterations after crossing 50%. The hard
stop (`exceeded`) **skips BLOCKED Recovery** — cost overruns are
exhaustion of the operating budget, not a failure of approach.
Decomposing into smaller sub-tasks would continue spending against the
same exhausted budget. The operator's correct response is to escalate
(raise `AGENT_CREW_BUDGET_{TIER}`, simplify the request, or abort).

`log_progress` is the helper introduced by `supervisor-bootstrap.md`
Phase 0 (mirrors to `progress.log` and stderr).

---

## BLOCKED Recovery

A `STATUS: BLOCKED` outcome (from validation exhaustion, crash
exhaustion, an explicit blocker reported by any stage agent, or a
devops failure in Phase 2.5) halts the pipeline. The supervisor MUST:

1. Write the blocker reason to `{TASK_DIR}/result.md` with
   `STATUS: blocked`.
2. Update the register with the blocker label so external tooling can
   read the terminal state without parsing `result.md`:

   ```bash
   register_update current_phase blocked
   register_update blocked_by --json '["<reason>"]'
   ```

   Where `<reason>` is one of: `validation_budget_exceeded`,
   `crash_budget_exceeded`, `agent_blocked`, `devops_failed`,
   `state_schema_invalid`, `plan_approval_cancelled`, etc.
3. Run the Phase 3 close-out below in full (Steps 1, 2, 2b, 3, 4, 5).
   The close-out's final `register_update current_phase completed`
   is conditional — it skips when `current_phase` is already `blocked`.
4. Return `STATUS: blocked` to the orchestrator with the same final
   return value contract used for completed runs.

The crash-exhaustion path (Stage Retry Rule budget reached) and the
explicit-BLOCKED path are identical from this point on — the close-out
is uniform.

### Architecture Recovery Before Quality-Loop Exhaustion

Before writing terminal `quality_loop_exhausted` after three reviewer or QA
rejections on the same implementation surface, the supervisor performs one
architecture recovery pass:

1. Load `core/agents/skills/systematic-debugging.md`.
2. Invoke analyst/planner recovery with the repeated rejection reason, PRD,
   handoff, pipeline, and review evidence paths.
3. Ask the recovery pass to decide whether to decompose the stage, restructure
   the contract, or confirm that the current design is still correct.
4. Retry once with the recovery directive. If that retry is rejected, then write
   `BLOCKER: quality_loop_exhausted`.

This mirrors the "three failures means question architecture" debugging rule
without bypassing TDD, reviewer approval, or evidence gates.

---

## Phase 3: Completion Handling

At Phase 3 entry, bump the register:

```bash
register_update current_phase phase_3
```

#### 1. Collect git log

```bash
git -C "${PROJECT_ROOT}" log --oneline -5
```

#### 1b. Runtime quality-loop gate

Before finalizing a completed mutating task, run the provider-neutral quality
loop validator against the task state. This is the completion-time backstop for
missing pipeline state, missing TDD evidence, missing reviewer approval, and
TDD stages that produced no test file and no explicit `context/tdd-exception.md`.
It also blocks invalid or unresolved `context/finding-register.json` entries
so QA/MR/reviewer/repair findings cannot disappear from completion output.

```bash
QUALITY_LOOP_OUTPUT=$(python3 "${AGENT_CREW_HOME}/scripts/quality-loop-check.py" \
  --task-dir "${TASK_DIR}" \
  --target-status completed \
  --format text 2>&1)
QUALITY_LOOP_RC=$?

if [ "${QUALITY_LOOP_RC}" -ne 0 ]; then
  log_progress "BLOCKED" "missing_quality_loop_pipeline: ${QUALITY_LOOP_OUTPUT}"
  register_update current_phase blocked
  register_update blocked_by --json '["missing_quality_loop_pipeline"]'
  printf '%s\n' "${QUALITY_LOOP_OUTPUT}" > "${TASK_DIR}/context/quality-loop-runtime-check.txt"
  cat > "${TASK_DIR}/result.md" <<EOF
STATUS: blocked
BLOCKER: missing_quality_loop_pipeline
DETAIL: Phase 3 quality-loop validation failed before completion.

${QUALITY_LOOP_OUTPUT}
EOF
  exit 1
fi
```

#### 2. Save concise result to `{TASK_DIR}/result.md`

(Do not re-quote contents)

All fields below are required. The orchestrator reads these fields to build
the Step 7 Run Summary — missing fields will cause the summary to be incomplete
or skipped.

Read `TASK_START_HEAD` from `${TASK_DIR}/context/start-head.txt` when writing the result:

```bash
TASK_START_HEAD=$(cat "${TASK_DIR}/context/start-head.txt" 2>/dev/null || echo "")
```

Collect the list of changed files and write a one-line description of what changed
for each:

```bash
git -C "${PROJECT_ROOT}" diff --name-only main...HEAD
```

For each changed file, describe the change semantically (not just a filename):
- Newly created file → `(did not exist) → {brief description of purpose}`
- Deleted file → `{brief description} → (removed)`
- Modified file → describe the key behavioral or structural change

```markdown
# {TASK}

DESCRIPTION: {TASK}
BRANCH: {BRANCH}
STATUS: completed
COMMITS: {commit count}
LOG:
{git log --oneline -5 output}

CHANGES:
  - {file path}: {one-line description of what changed}
  - {file path}: {one-line description of what changed}

DIFF_STAT:
{git diff $TASK_START_HEAD..HEAD --stat 2>/dev/null output}

DIFF_PREVIEW:
{git diff $TASK_START_HEAD..HEAD 2>/dev/null | head -200 output}
```

After writing result.md, immediately close out the host task (before any
further logging), then collect the commit count and emit the COMPLETED event.

#### 2b. Close out the host task (capability-gated)

**This step runs immediately after result.md is written — before
`log_progress "COMPLETED"` — so that a token-truncation or interrupt after
result.md is persisted still marks the host task as terminal.**

If `HAS_TASK_TOOLS == 1` from Phase 0 and `${TASK_DIR}/host-task-id.txt` exists,
update the host-side task to its terminal status. This is what unblocks
`run.md` Step 7's `TaskGet` poll loop, which waits for
`status in ("completed", "blocked", "cancelled")`.

```bash
if [ "${HAS_TASK_TOOLS}" = "1" ] && [ -f "${TASK_DIR}/host-task-id.txt" ]; then
  HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt")
  # Determine the terminal status from the result:
  #   STATUS: completed  → "completed"
  #   STATUS: blocked    → "blocked"   (unblocks orchestrator Step 7 loop)
  #   STATUS: CANCELLED  → "completed" (clean up stale task list)
  FINAL_HOST_STATUS="completed"
  if grep -q "^STATUS: blocked" "${TASK_DIR}/result.md" 2>/dev/null; then
    FINAL_HOST_STATUS="blocked"
  fi
  TaskUpdate(taskId=HOST_TASK_ID, status="${FINAL_HOST_STATUS}")
fi
```

The `FINAL_HOST_STATUS` mapping:
- `STATUS: completed` in `result.md` → `TaskUpdate(status="completed")`
- `STATUS: blocked` in `result.md` → `TaskUpdate(status="blocked")` so the
  orchestrator's Step 7 loop exits; the operator can inspect and close it manually.
- `STATUS: CANCELLED` in `result.md` (plan-approval gate cancel) → `TaskUpdate(status="completed")`
  so the host task list does not accumulate stale tasks.

##### Defensive per-stage sweep (issue #128)

Step 2b above transitions the supervisor's own parent host task. Per-stage
child host tasks (recorded under `pipeline.json.host_task_ids` by Phase
1c-bis) are normally transitioned at each stage's `STAGE_DONE` block in
`supervisor-stages.md`. Those per-stage transitions can be missed when the
stage was reached on the BLOCKED Recovery path, when a token-truncation
interrupted the supervisor between `STAGE_DONE` and Phase 3, or when the host
encountered a transient error on the per-stage call. Issue #128 reports this
as stale `in_progress`/`pending` host TaskList rows after the task is
actually terminal.

Run the planner script once after Step 2b's parent transition. It reads
`result.md` + `pipeline.json` + `host-task-id.txt` and emits a JSON plan
listing every `(host_task_id, target_status)` transition the host should
make. The supervisor then iterates **stage-scope** entries only (the parent
was already handled above) and issues an idempotent `TaskGet`-then-`TaskUpdate`
for each. The sweep is gated on `HAS_TASK_TOOLS == 1`; missing or non-terminal
`result.md` and host transient errors are absorbed silently — this is a
best-effort defensive sweep and must never block Phase 3 close-out.

```bash
if [ "${HAS_TASK_TOOLS}" = "1" ]; then
  RECONCILE_PLAN=$(python3 "${AGENT_CREW_HOME}/scripts/reconcile-host-tasks.py" \
    --task-dir "${TASK_DIR}" --format json 2>/dev/null) || RECONCILE_PLAN=""
  if [ -n "${RECONCILE_PLAN}" ]; then
    # Iterate stage-scope entries only — Step 2b already handled the parent.
    # python3 emits one TSV row per pending stage entry; the supervisor then
    # issues TaskGet + (conditional) TaskUpdate for each. Per-call failures
    # are tolerated silently (host race conditions must never block Phase 3).
    echo "${RECONCILE_PLAN}" | python3 -c "
import json, sys
plan = json.load(sys.stdin)
for a in plan.get('reconcile_plan', []):
    if a.get('scope') != 'stage':
        continue
    print(a['host_task_id'], a['target_status'], sep='\t')
" 2>/dev/null | while IFS=$'\t' read -r STAGE_TASK_ID TARGET_STATUS; do
      [ -z "${STAGE_TASK_ID}" ] && continue
      # CURRENT_STATUS=$(TaskGet(taskId=${STAGE_TASK_ID}).status)
      # if [ "${CURRENT_STATUS}" != "completed" ] && [ "${CURRENT_STATUS}" != "blocked" ] && [ "${CURRENT_STATUS}" != "cancelled" ]; then
      #   TaskUpdate(taskId=${STAGE_TASK_ID}, status="${TARGET_STATUS}")
      # fi
      :  # host tool calls are issued by the runtime — guard each one with TaskGet
    done
  fi
fi
```

The script never calls into the host itself — that separation keeps it
AI-agnostic and unit-testable. Tests live at
`tests/python/test_reconcile_host_tasks.py`. When `HAS_TASK_TOOLS == 0` or
the script returns non-zero (no parseable STATUS, missing `result.md`), the
sweep is a strict no-op.

After calling `TaskUpdate`, collect the commit count and emit:

```
[crew] {TASK_ID} | COMPLETED | branch={BRANCH} commits={n}
```

```bash
log_progress "COMPLETED" "branch=${BRANCH} commits=${n}"

# Phase F4: final register update — terminal state.
# Read existing register state so we don't overwrite a BLOCKED Recovery
# label with `completed`.
REG_PHASE=$(python3 -c "
import json
try:
    r = json.load(open('${TASK_DIR}/register.json'))
    print(r.get('current_phase', ''))
except Exception:
    print('')
" 2>/dev/null)
REG_VERIFY=$(python3 -c "
import json
try:
    r = json.load(open('${TASK_DIR}/register.json'))
    print(r.get('verification_status', 'not_started'))
except Exception:
    print('not_started')
" 2>/dev/null)
if [ "${REG_VERIFY}" = "not_started" ] || [ "${REG_VERIFY}" = "running" ]; then
  register_update verification_status skipped
fi
if [ "${REG_PHASE}" != "blocked" ]; then
  register_update current_phase completed
fi
```

The completion event is mirrored to stderr per the stderr-mirror rule
in Phase 0 via the `log_progress` helper.

If `HAS_TASK_TOOLS == 0` or the file is absent: skip this step entirely.

#### 2c. AAR debrief — close the learning loop (After-Action Review)

This step closes agent-crew's one open feedback loop: post-run signals
(retries, reviewer `NEEDS_CHANGES` loop-backs, blockers) already exist in
telemetry but never feed the NEXT plan. The debrief distills them into a
compact After-Action Review (AAR) memo and captures it to memory so the
analyst/planner can recall it as a deterministic **plan-time** hint on a
future task of similar shape (see `core/agents/analyst.md` and
`core/agents/planner.md` § plan-construction). This is a plan-time-feedback
loop only — it makes **no** change to verification, the reviewer stage, or
the quality loop. See `core/rules/memory-governance.md`
§ After-Action Review (AAR) Memo for the full contract.

Run this step after the `COMPLETED` event is emitted (so an interrupt before
it never blocks task close-out). It is **out of band** of stage retries and
**never** fails the pipeline.

```bash
# Distill the just-finished task into an AAR memo (reuses aggregate_task()).
AAR_JSON=$(python3 "${AGENT_CREW_HOME}/scripts/telemetry-aggregate.py" \
  --state-dir "${STATE_DIR}" \
  --task-id "${TASK_ID}" \
  --debrief --format json 2>/dev/null) || true

AAR_MEANINGFUL=$(printf '%s' "${AAR_JSON}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('meaningful', False))" 2>/dev/null || echo "False")
AAR_RECALL_HINT=$(printf '%s' "${AAR_JSON}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('recall_hint', ''))" 2>/dev/null || echo "")

# Guardrail-2 (cost): skip capture when the cost circuit breaker is exhausted,
# mirroring the handoff page-out precedent (Phase 3.5). A post-hoc capture must
# never push an already-over-budget task further over budget.
AAR_COST_OK=1
if [ "${HAS_COST_TRACKING}" = "1" ]; then
  AAR_COST_VERDICT=$(python3 "${AGENT_CREW_HOME}/scripts/cost-aggregate.py" \
    --state-dir "${STATE_DIR}" --task-id "${TASK_ID}" --check-breaker 2>/dev/null) || true
  if [ "${AAR_COST_VERDICT}" = "exceeded" ]; then
    AAR_COST_OK=0
  fi
fi

if [ "${AAR_COST_OK}" != "1" ]; then
  # Guardrail-2 skip.
  log_progress "AAR_DEBRIEF_SKIPPED" "reason=cost_exceeded"
elif [ "${AAR_MEANINGFUL}" = "True" ]; then
  # Guardrail-1 satisfied: meaningful signals present → capture to project layer.
  # mnemos is the existing AI-agnostic memory contract; capture is a no-op when
  # no memory backend is installed.
  MEMORY="${AGENT_CREW_HOME:-${HOME}/.agent-crew}/bin/memory"
  if command -v "${MEMORY}" >/dev/null 2>&1; then
    "${MEMORY}" capture \
      --content "AAR memo (task ${TASK_ID}): ${AAR_RECALL_HINT}" \
      --layer project 2>/dev/null || true
  fi
  log_progress "AAR_DEBRIEF" "meaningful=true captured recall_hint to project memory"
else
  # Guardrail-1 gate: clean run, no signals worth capturing → skip (no noise).
  log_progress "AAR_DEBRIEF_SKIPPED" "reason=not_meaningful"
fi
```

The two events are added to the Phase 0 event catalog
(`supervisor-bootstrap.md` Progress Mirroring):

| EVENT | When emitted | Detail |
|---|---|---|
| `AAR_DEBRIEF` | Phase 3 close-out — debrief ran, signals were meaningful (Guardrail-1), cost breaker not exhausted (Guardrail-2), and the AAR memo was captured to project memory | `meaningful=true captured recall_hint to project memory` |
| `AAR_DEBRIEF_SKIPPED` | Phase 3 close-out — debrief skipped without capture, either because no meaningful signals existed (Guardrail-1) or because the cost circuit breaker was exhausted (Guardrail-2) | `reason={not_meaningful\|cost_exceeded}` |

**Ship-threshold (user-visible delta).** Over repeated runs of similar task
shapes, the captured AAR memo is recalled by the analyst/planner and used to
proactively harden the next `pipeline.json` (enable `tdd_parallel`, retain the
reviewer stage, widen test coverage), **reducing repeat reviewer rejections and
quality-loop loop-backs** on recurring work.

If `telemetry-aggregate.py` is absent or the debrief crashes, this step is a
no-op — it logs nothing and never blocks close-out (out-of-band rule).

#### 3. Clear active task marker

Two marker layouts are supported by `core/hooks/direct-edit-guard.sh` (see
`core/rules/capabilities/agent-background.md`):

1. **Legacy singleton** `tasks/active` — used by single-task workflows and by
   adapters that have not adopted background fan-out.
2. **Per-task markers** `tasks/active.<TASK_ID>` — used when the orchestrator
   spawns supervisors as background host agents (`agent_background=true`)
   because each runner must own its own marker so concurrent teardown is safe.

Each supervisor removes only the marker it owns:

```bash
eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --ensure \
  --format shell)"
TASKS_DIR="${STATE_DIR}/tasks"

# Per-task marker: always safe to remove our own
rm -f "${TASKS_DIR}/active.${TASK_ID}"

# Legacy singleton: only clear when running in single mode AND no other
# per-task markers remain (otherwise a concurrent run would be stranded).
if [ "${EXECUTION_MODE}" != "parallel" ]; then
  # Count remaining per-task markers (active.* but not "active" itself)
  REMAINING=$(ls "${TASKS_DIR}"/active.* 2>/dev/null | wc -l | tr -d ' ')
  if [ "${REMAINING}" = "0" ]; then
    rm -f "${TASKS_DIR}/active"
  fi
fi
```

The Phase 1c create step (`touch ${TASKS_DIR}/active`) must also write the
per-task variant when running under background fan-out:

```bash
eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --ensure \
  --format shell)"
TASKS_DIR="${STATE_DIR}/tasks"
mkdir -p "${TASKS_DIR}"

# Always write the per-task marker — it is the canonical marker under P4.
touch "${TASKS_DIR}/active.${TASK_ID}"

# Legacy singleton: write it too for backward compatibility with hosts /
# tooling that has not yet learned the per-task layout. The cleanup step
# above only removes it when no per-task markers remain.
touch "${TASKS_DIR}/active"
```

The Phase 1c block earlier in this document writes the singleton marker
unconditionally; the per-task marker is created here as an additional layer
for adapters that have opted into background fan-out.

#### 4. Remove isolated worktree when applicable

Worktree teardown evaluates the harness-provenance guard before invoking
`git worktree remove` and unconditionally settles administrative state with
`git worktree prune` after a successful removal. Both guards use bash + git
only so the supervisor stays AI-agnostic.

```bash
# Shared realpath shim (matches core/commands/run.md and supervisor-stages.md).
crew_realpath() {
  if command -v realpath >/dev/null 2>&1; then
    realpath "$1" 2>/dev/null
  else
    ( cd "$1" 2>/dev/null && pwd -P ) || printf '%s' "$1"
  fi
}

if [ "${EXECUTION_MODE}" = "parallel" ] && [ "${PROJECT_ROOT}" != "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" ]; then
  # Guard 4: Provenance-based cleanup
  # Only remove worktrees whose realpath is a descendant of
  # `<harness-root>/.crew-worktrees/`. Reject (log STATE_WARN + skip) anything
  # outside that base so user-owned or external worktrees are never removed.
  CREW_HARNESS_ROOT="$(git -C "${PROJECT_ROOT}" rev-parse --show-superproject-working-tree 2>/dev/null || true)"
  if [ -z "${CREW_HARNESS_ROOT}" ]; then
    CREW_HARNESS_ROOT="$(git -C "${PROJECT_ROOT}" rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's@/\.git$@@' || true)"
  fi
  CREW_WORKTREES_BASE="${CREW_WORKTREES_BASE:-${CREW_HARNESS_ROOT%/}/.crew-worktrees}"
  CREW_WORKTREES_BASE_REAL="$(crew_realpath "${CREW_WORKTREES_BASE}")"
  CREW_CANDIDATE_REAL="$(crew_realpath "${PROJECT_ROOT}")"
  case "${CREW_CANDIDATE_REAL}/" in
    "${CREW_WORKTREES_BASE_REAL}/"*)
      git worktree remove "${PROJECT_ROOT}" --force 2>/dev/null || true
      # Guard 5: Post-remove prune
      # Reclaim stale administrative entries left behind by the removal.
      git -C "${CREW_HARNESS_ROOT:-.}" worktree prune 2>/dev/null || true
      ;;
    *)
      printf '[crew] STATE_WARN worktree-guard 4: refusing to remove non-harness path %s (base=%s)\n' \
        "${CREW_CANDIDATE_REAL}" "${CREW_WORKTREES_BASE_REAL}" >&2
      ;;
  esac
fi
```

#### 5. Final return value (to parent crew orchestrator)

```text
TASK_ID: {TASK_ID}
BRANCH: {BRANCH}
STATUS: completed
COMMITS: {N} commits
```

Return only this.
Do not include file contents, code, or long explanations.


---

After the final return, the supervisor exits. The crew orchestrator
(`core/commands/run.md` Steps 7+) takes over for parallel-fan-in and
the optional push gate.
