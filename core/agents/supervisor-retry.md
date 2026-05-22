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
while crash_attempts <= 5:
    invoke agent
    if response contains "STATUS: completed":
        break  # success
    elif response contains "STATUS: plan_ready":
        break  # agent submitted a plan — Phase 2.5 will handle approval
    elif response contains "STATUS: BLOCKED":
        halt pipeline — write blocker to result.md and return STATUS: blocked
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

When the reviewer stage returns either `STATUS: REJECTED` or
`REVIEW: NEEDS_CHANGES`, the supervisor MUST re-loop to the **most
recent implementer/TDD stage** instead of advancing `completed_stages`.
This is the core commercial quality loop: implement through TDD,
review, remediate/refactor through TDD, re-review, and repeat until
approval or budget exhaustion.

Both reviewer rejection forms are mandatory loop triggers:

| Reviewer return | Triggered when | Re-loop reason |
|---|---|---|
| `STATUS: REJECTED` + `REASON: tests_failed` | A discovered test runner failed. | `tests_failed` |
| `STATUS: REJECTED` + `REASON: tests_absent_for_code_change` | Code changed but no test runner was discoverable. | `tests_absent_for_code_change` |
| `STATUS: REJECTED` + `REASON: cross_process_path_mismatch` | Cross-process path agreement failed. | `cross_process_path_mismatch` |
| `REVIEW: NEEDS_CHANGES` | Static or streaming review found correctness, coverage, architecture, security, or quality issues. | `review_needs_changes` |

Use the provider-neutral classifier before deciding whether to advance
or re-loop:

```bash
REVIEW_DECISION=$(python3 "${AGENT_CREW_HOME}/scripts/reviewer-loop-decision.py" \
  --response "${TASK_DIR}/context/reviewer-response.txt" \
  --format json)
REVIEW_ACTION=$(printf '%s' "${REVIEW_DECISION}" | python3 -c "import sys,json; print(json.load(sys.stdin)['action'])")
REVIEW_REASON=$(printf '%s' "${REVIEW_DECISION}" | python3 -c "import sys,json; print(json.load(sys.stdin)['reason'])")
REVIEW_DIRECTIVE=$(printf '%s' "${REVIEW_DECISION}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('directive',''))")
```

The classifier maps both `STATUS: REJECTED` and `REVIEW:
NEEDS_CHANGES` to `action=retry`. `REVIEW: APPROVED` maps to
`action=approve`.

Re-loop logic (executed by Phase 2's stage loop wrapper around the
reviewer stage spawn — runs at the same point in the dispatch flow as
the existing crash-retry path):

```python
# Inside the stage loop, after the reviewer agent returns:
decision = reviewer_loop_decision(reviewer_response)
if decision.action == "retry":
    reason = decision.reason
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
    # completed_stages back to the most recent implementer stage so the
    # outer stage loop re-spawns it instead of advancing.
    impl_stage_index = find_most_recent_implementer_stage_index()
    append_directive_to_handoff(decision.directive)
    pipeline.completed_stages = impl_stage_index - 1
    pipeline.stage_agent_status.pop(str(impl_stage_index), None)  # clear so retry re-runs
    save_pipeline_json()

    continue  # re-enter the stage loop at the implementer index
```

The `find_most_recent_implementer_stage_index()` helper walks
`pipeline.stages` backwards from the reviewer stage's index and
returns the first non-reviewer / non-devops / non-resolver index.
When no implementer is found (degenerate pipeline of `[["reviewer"]]`
only), the supervisor halts with
`BLOCKER: quality_loop_no_implementer_to_retry` — re-running an empty
pipeline cannot produce a different verdict.

The Stage Retry Rule's two pre-existing budgets remain unchanged:

| Budget | Scope | Behavior on exhaustion |
|---|---|---|
| `validation = 3` | Reviewer-driven re-loops (this rule) AND any explicit "validation failure" reported by a stage agent. | Hard stop, `BLOCKER: quality_loop_exhausted`. |
| `crash = 5`      | Stage agent crashes (no STATUS line, host-detected `error`). | Hard stop, crash details to result.md. |

`quality_retries` is initialized to 0 at the top of the reviewer stage
iteration, alongside `crash_attempts`. The two counters are independent
— a reviewer rejection consumes a validation retry; a reviewer crash
consumes a crash retry; they cannot cross-deplete each other. `REVIEW:
NEEDS_CHANGES` is no longer advisory-only; it is a hard quality-loop
retry signal.

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
PROJECT_NAME=$(basename "${PROJECT_ROOT}")
TASKS_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}/tasks"

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
PROJECT_NAME=$(basename "${PROJECT_ROOT}")
TASKS_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}/tasks"
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

```bash
if [ "${EXECUTION_MODE}" = "parallel" ] && [ "${PROJECT_ROOT}" != "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" ]; then
  git worktree remove "${PROJECT_ROOT}" --force 2>/dev/null || true
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
