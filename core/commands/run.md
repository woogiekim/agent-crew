# crew:run - Unified Task Orchestration

Run one or more tasks through the same execution engine.
Every task is executed by a `task-runner`. A single request spawns one
`task-runner`; multiple requests spawn multiple `task-runner` agents.

`crew:run` is the canonical workflow entry point.

```text
[orchestrator] crew:run "Task A" | "Task B" | "Task C"
      |
      v
normalize the input into one or more task entries
      |
      v
prepare one execution context per task
      |
      v
delegate one task-runner per task
      |
      v
collect results and provide merge guidance
```

## Core Principle

The orchestration engine should not run planner, designer, backend, or frontend
stages directly. It should always delegate a full task to `task-runner`.

This gives single-task and multi-task execution the same engine:

- Single request -> one `task-runner`
- Multiple requests -> multiple `task-runner` agents

## Parallel-First Rule

**Always prefer parallel fan-out over sequential execution.**

File overlap between parallel tasks is not a reason to serialize. If parallel
task-runners modify the same file, merge conflicts are resolved by the
**resolver agent** after all runners complete — that is its explicit purpose.

Sequential execution (`N == 1`) is only correct when tasks have a true
dependency (Task B cannot start until Task A's output exists).

```
# Correct — parallel even if tasks touch the same files
crew:run "Fix bug A" | "Fix bug B"

# Wrong — serializing to avoid a conflict the resolver handles
crew:run "Fix bug A"   # then wait...
crew:run "Fix bug B"
```

## Execution Steps

### 1. Collect Tasks

Use provided arguments as task descriptions. If none are provided, ask through
the host AI tool's structured input UI.

Accept:

- One task: `crew:run "implement order API"`
- Multiple tasks: `crew:run "Order API" | "Product API" | "User API"`

Normalize the input into a task list with cardinality `N >= 1`.

#### Input Normalization

If any task description contains Hangul characters, delegate to the
**korean-normalizer agent** before proceeding:

```text
RAW_TASK: {original Korean string}
Apply core/rules/korean-input.md normalization and return NORMALIZED_TASK.
```

Use the returned `NORMALIZED_TASK` as the canonical TASK for all downstream
agents and state files. See `core/rules/normalization-adapter.md` for the full
adapter contract.

> **Hard gate**: If Hangul is detected, do not proceed to Step 2 until
> `NORMALIZED_TASK` is confirmed. The original Korean string must not appear
> in any agent prompt, `pipeline.json`, or `result.md`.

### 2. Initialize State Paths

```bash
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
```

If `STATE_DIR` does not exist, stop with:

```text
Run crew:setup first.
```

### 3. Resume Detection

If `N > 1`, skip this step entirely — always start a new fan-out run and
proceed directly to Step 4.

If `N == 1`, check for the newest incomplete task under `STATE_DIR/tasks`.
An incomplete task is one that has a `pipeline.json` file but no `result.md`
with `STATUS: completed`.

```bash
# Fast check: find the most recent task directory without a completed result
RESUME_CANDIDATE=$(find "${STATE_DIR}/tasks" -maxdepth 1 -mindepth 1 -type d \
  -exec sh -c '[ -f "$1/pipeline.json" ] && ! grep -q "STATUS: completed" "$1/result.md" 2>/dev/null && echo "$1"' _ {} \; \
  | sort | tail -1)
```

If `RESUME_CANDIDATE` is non-empty, ask whether to resume it or start a new run.

If resuming:

- reuse the existing `TASK_ID`
- reuse the existing `TASK_DIR`
- reuse the recorded branch or worktree metadata if present
- continue through the same `task-runner`

### 4. Prepare Each Task Context

For each task index `i`:

```bash
TASK_ID="$(date +%Y%m%d-%H%M%S)-${i}"
TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"

branch_prefix_for_task() {
  python3 - "$1" <<'PYEOF'
import re
import sys

text = sys.argv[1].lower()
words = set(re.findall(r"[a-z0-9]+", text))

rules = [
    ("fix", {"fix", "fixes", "fixed", "bug", "bugs", "repair", "repairs", "broken", "error", "errors", "failing", "failure", "failures", "regression", "regressions"}, ()),
    ("docs", {"doc", "docs", "documentation", "readme", "guide", "guides", "instruction", "instructions", "manual"}, ()),
    ("refactor", {"refactor", "refactors", "refactoring", "restructure", "cleanup", "simplify", "reorganize"}, ("clean up",)),
    ("test", {"test", "tests", "testing", "spec", "specs", "coverage", "qa"}, ()),
    ("chore", {"chore", "chores", "build", "dependency", "dependencies", "deps", "config", "configuration", "setup", "tooling", "maintenance"}, ("continuous integration",)),
]

for prefix, tokens, phrases in rules:
    if words & tokens or any(phrase in text for phrase in phrases):
        print(prefix)
        break
else:
    print("feature")
PYEOF
}

task_slug_for_branch() {
  python3 - "$1" <<'PYEOF'
import re
import sys

text = sys.argv[1].lower()
words = re.findall(r"[a-z0-9]+", text)
stopwords = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "so", "that", "the",
    "to", "with", "instead", "only", "than", "rather"
}
slug_words = [word for word in words if word not in stopwords]
slug = "-".join(slug_words)[:48].strip("-")
print(slug or "task")
PYEOF
}

TASK_SLUG="$(task_slug_for_branch "${TASK}")"
BRANCH_PREFIX="$(branch_prefix_for_task "${TASK}")"
BRANCH="${BRANCH_PREFIX}/${TASK_SLUG}"
```

Branch prefixes must describe the work type rather than defaulting to
`feature/`. Use `fix/` for bug fixes, `docs/` for documentation, `refactor/`
for restructuring without behavior changes, `test/` for test-only work,
`chore/` for maintenance, build, dependency, setup, CI, and tooling work, and
`feat/` for new or improved product behavior. The task slug is derived from the
task description and provides sufficient uniqueness — no TASK_ID suffix is
appended. See `core/rules/branch-naming.md` for the full naming spec.

Execution context depends on cardinality:

- If `N == 1`, **do not create a worktree**. Use the current project worktree
  directly. Create the branch with a regular `git checkout -b ${BRANCH}` only
  (no `git worktree add`). This avoids `git worktree add` latency entirely for
  single-task runs.
- If `N > 1`, create one isolated git worktree per task. **Pre-create all
  worktrees before starting requirements collection** so that I/O-bound worktree
  setup overlaps with the user-facing requirement interview:

```bash
# Pre-create worktrees for all tasks up-front (before Step 5)
WORKTREE_PATH="${PROJECT_ROOT}/.crew-worktrees/${TASK_ID}"
mkdir -p "${TASK_DIR}/context"
git worktree add -b "${BRANCH}" "${WORKTREE_PATH}" HEAD
```

The orchestrator owns context preparation only. The execution engine remains the
same in both modes.

### 5. Collect Requirements Per Task

> **NEVER-SKIP RULE**: Step 5 is mandatory for every `crew:run` invocation without
> exception. Do NOT skip or abbreviate this step regardless of how obvious the task seems.
> The task argument is a description, not requirements.

**When `N == 1`:** Delegate to the requirements agent (blocking):

```text
TASK: {task description}
TASK_INDEX: 0
TASK_DIR: {TASK_DIR}

Run the 2-round AskUserQuestion interview, validate scope, detect ambiguities,
write {TASK_DIR}/context/requirements.md, and return the REQUIREMENTS block.
```

Wait for the agent to return. Extract the `REQUIREMENTS` block and record it.

**When `N > 1`:** Spawn all N requirements agents **simultaneously in a single
response** (one Agent tool call per task, all issued together). Do NOT send them
one at a time — parallel spawn is mandatory for N > 1:

```text
# Issue all N Agent calls in the same response (parallel fan-out):
For task 0:
  TASK: {task 0 description}
  TASK_INDEX: 0
  TASK_DIR: {TASK_DIR_0}
  Run the 2-round AskUserQuestion interview, write requirements.md, return REQUIREMENTS block.

For task 1:
  TASK: {task 1 description}
  TASK_INDEX: 1
  TASK_DIR: {TASK_DIR_1}
  Run the 2-round AskUserQuestion interview, write requirements.md, return REQUIREMENTS block.

... (one call per task, all in the same response)
```

Wait for **all** N requirements agents to complete before proceeding to Step 6.
Extract each task's `REQUIREMENTS` block from its agent's response and record it.
Do not run task-runners while requirements collection is still in progress for any task.

### 6. Run Task Runners

> **MANDATORY DELEGATION RULE — non-negotiable.** The orchestrator (the Claude
> instance loaded with this `run.md`) MUST spawn a `task-runner` subagent for
> every task via the host's Agent/Task tool. The orchestrator MUST NOT run
> planner, designer, backend, frontend, devops, or any other stage agent
> directly, and MUST NOT execute pipeline phases (Phase 0 through Phase 3)
> inline as itself. Doing so is what this section calls **inline execution**,
> and it is a workflow violation.
>
> Required behavior:
> - Call the host's Agent tool **once per task** with `subagent_type: task-runner`
>   (or the host's equivalent) and the input block defined below.
> - Wait for each `task-runner` to return its STATUS report. The orchestrator's
>   job is dispatch, health check (Task-Runner Health Check below), and result
>   collection — not implementation.
>
> Forbidden behaviors (each one is a bug):
> - Reading `task-runner.md` and "playing the role" of task-runner inline.
> - Invoking the planner agent directly from this orchestrator step.
> - Performing `touch ${AGENT_CREW_HOME}/state/${PROJECT_NAME}/tasks/active`
>   from the orchestrator — that marker is created by `task-runner` Phase 1c,
>   and creating it elsewhere masks the underlying delegation failure.
> - Editing project source files from the orchestrator. The orchestrator only
>   writes to `${TASK_DIR}` (state files) and to remotes during Step 11.
>
> Why this matters: `task-runner.md` Phase 1b+1c is the only place that creates
> the active task marker the `direct-edit-guard` PreToolUse hook checks for. If
> the orchestrator skips delegation, Phase 1b+1c never executes, the marker is
> never created, and every subsequent Edit/Write to project source is blocked by
> the hook. Every observed "hook blocked my edit" symptom in this repo traces back
> to a missing delegation here.

> **Plan Approval Gate (N == 1):** For single-task runs, the plan approval gate is
> handled **inside** the task-runner at Phase 1d. The task-runner reads `pipeline.json`
> and `analysis.md` after the merged analyst spawn, displays the full implementation
> plan, and fires AskUserQuestion before any stage agent executes. Do NOT add a
> separate plan approval gate here in the orchestrator for N == 1.
>
> **Plan Approval Gate (N > 1):** For parallel runs, each task-runner independently
> handles Phase 1d for its own pipeline. After all task-runners have finished Phase
> 1b+1c (merged analysis+planning), each will pause at Phase 1d awaiting user
> approval. The orchestrator does not consolidate these approvals — each
> task-runner's Phase 1d is independent.

Delegate one `task-runner` per task. The orchestrator chooses between two
delegation surfaces based on the `agent_background` capability flag:

```bash
HAS_AGENT_BACKGROUND=$(python3 -c "
import json
try:
    print('1' if json.load(open('${CAPABILITIES_PATH}')).get('agent_background') else '0')
except Exception:
    print('0')
" 2>/dev/null)
```

**P4 — Background fan-out (preferred when `HAS_AGENT_BACKGROUND == 1` AND `N > 1`).**
Spawn each task-runner as a host background agent pinned to a pre-created
parent host task. The orchestrator returns from the spawn step immediately and
collects results via `TaskList` / `TaskGet` / `TaskOutput` instead of waiting
for inline Agent calls to return:

```text
HAS_TASK_TOOLS=$(python3 -c "...task_tools...")  # already cached, see Step 7.5

for each task i:
    # Pre-create the parent host task that the runner will adopt in Phase 0
    # (the runner reads its HOST_TASK_ID from metadata instead of issuing
    # its own TaskCreate when this path is taken).
    HOST_TASK_ID = TaskCreate(
        subject=f"crew:run — {TASK truncated to 60 chars}",
        description=f"agent-crew task-runner pipeline for TASK_ID={TASK_ID}. "
                    f"File source of truth: {TASK_DIR}/progress.log",
        activeForm="Running crew:run pipeline (background)",
        metadata={
            "task_id": TASK_ID,
            "branch": BRANCH,
            "task_dir": TASK_DIR,
            "spawn_mode": "background",
        },
        status="in_progress",
    )
    write HOST_TASK_ID to ${TASK_DIR}/host-task-id.txt

    # Spawn the runner as a host background agent. Implementation depends on
    # the host's background-agent surface — for Claude Code this maps to the
    # background task-creation flow that captures stdout/stderr into
    # TaskOutput so crew:status can read it live (P5).
    spawn task-runner as background agent with:
        TASK, TASK_ID, TASK_DIR, PROJECT_ROOT, BRANCH,
        EXECUTION_MODE=parallel,
        HOST_TASK_ID=$HOST_TASK_ID,
        REQUIREMENTS=$REQUIREMENTS
```

Under this path, **each task-runner owns a per-task `direct-edit-guard`
marker** (`tasks/active.<TASK_ID>`) so concurrent teardown by one runner does
not strand another runner's edits. The hook accepts either layout — see
`core/hooks/direct-edit-guard.sh` and `core/rules/host-capabilities.md`
Layer 2.

**Legacy inline parallel fan-out** is used when `HAS_AGENT_BACKGROUND == 0`,
OR when `N == 1` (background mode has no benefit for a single task — keep the
inline path so the user sees the runner's response stream in the same
session):

- If `N == 1`, invoke one `task-runner` via the host's Agent/Task tool. Do not
  execute the pipeline inline.
- If `N > 1` AND `HAS_AGENT_BACKGROUND == 0`, invoke all `task-runner` agents
  concurrently in a single response containing N parallel Agent tool calls.

Both paths use the same task-runner agent definition. The runner detects
which surface spawned it by checking whether `HOST_TASK_ID` was passed in its
prompt (background) vs absent (inline) and adapts Phase 0 accordingly: when
`HOST_TASK_ID` is provided, skip the in-runner `TaskCreate` and use the
pre-created id; when absent, fall back to the legacy in-runner `TaskCreate`
path.

Each task-runner receives:

```text
TASK: {task description}
TASK_ID: {TASK_ID}
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {execution root for this task}
BRANCH: {BRANCH}
EXECUTION_MODE: single or parallel
REQUIREMENTS: |
  scope: {scope answer}
  target: {target answer}
  constraints: {constraints answer(s)}
  followup:
    {field_name}: {Round 2 answer A, if collected}
    {field_name}: {Round 2 answer B, if collected}

Complete this task autonomously through the full pipeline.
Write the completion report to {TASK_DIR}/result.md.
```

#### Task-Runner Health Check (Persistent Execution)

After each task-runner returns, the orchestrator must verify its output:

- If the task-runner returns **without a STATUS field** (crash, token limit,
  or interrupt):
  - Treat as a crash. Do **not** mark the task as failed.
  - Re-invoke the same task-runner with identical parameters.
  - The task-runner will resume from `pipeline.json` (Phase 0 resume check).
  - Retry up to **3 times** before marking the task as blocked.

**P7 — capability-gated crash classification (when `HAS_TASK_TOOLS == 1`).**
When the parent host task id is available at `${TASK_DIR}/host-task-id.txt`,
the orchestrator should consult `TaskGet(parent_taskId).status` to classify
the "no STATUS field" outcome before retrying:

```text
HOST_STATUS=$(TaskGet(taskId=$(cat "${TASK_DIR}/host-task-id.txt")).status)
```

| `TaskGet` status | Classification | Orchestrator action |
|---|---|---|
| `error` | True crash | Re-invoke (counts against 3-retry budget) |
| `completed` | Token-truncation tail | Re-invoke with resume hint pointing at `${TASK_DIR}/progress.log` and `pipeline.json`; this resume does **not** count against the 3-retry budget (one free token-truncation resume per task) |
| `blocked` | Task-runner reached BLOCKED but failed to write STATUS | Read `${TASK_DIR}/result.md`; if STATUS present treat as blocked, else re-invoke as crash |
| `in_progress` / `pending` | Host did not yet observe completion — likely runtime interrupt | Re-invoke (counts as crash) |
| `cancelled` | User cancelled at gate | Mark task blocked with reason "Cancelled by approval gate" — do not retry |

When `HAS_TASK_TOOLS == 0` or the parent host task id is absent: skip the
classification entirely and apply the legacy "every no-STATUS outcome is a
crash, retry up to 3 times" rule. Behavior is identical to pre-P7.

This "끈질기게 실행" (persistent execution) rule means the orchestrator never
gives up on a task-runner until it explicitly returns `STATUS: blocked` with a
real, substantive blocker.

Wait for all task-runners to finish (including any crash-retry cycles).

### 7.5. Parallel Action Gate (N > 1 only)

> **Skip this step entirely when N == 1.** For single-task runs, the task-runner
> itself acts as the local orchestrator for its own stage agents and issues the
> consolidated AskUserQuestion via its Phase 2.5 Stage Action Gate. Proceed
> directly to Step 7 (Collect Results).

When `N > 1`, all task-runners execute concurrently. Before any stage agent
executes a deploy, merge, push, or other destructive action, the orchestrator
must consolidate their plans and issue a **single** approval gate.

#### Protocol

**Phase A — Plan collection (task-runners block, waiting for approval.md)**

Each stage agent (devops, etc.) that would previously ask for approval must instead:
1. Write its planned actions to `{TASK_DIR}/context/action-plan.md`
2. Return a `PLAN:` block to its parent task-runner — do not execute yet
3. The task-runner writes `PLAN_READY` to `{TASK_DIR}/context/approval.md`
4. The task-runner polls `{TASK_DIR}/context/approval.md` for `APPROVED` or
   `CANCELLED` (up to 60s, 5s interval) before releasing execution

**Phase B — Centralized approval (orchestrator)**

After all task-runners have written `PLAN_READY` to their `approval.md`, the
orchestrator:

1. Reads `action-plan.md` from every `TASK_DIR`
2. Composes a consolidated approval summary:

   ```text
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Consolidated Action Plan
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Task 1 [{BRANCH_1}]:
     - deploy: push to staging via docker-compose up -d
     - merge: git merge --no-ff {BRANCH_1} into main

   Task 2 [{BRANCH_2}]:
     - deploy: run npm run build && rsync dist/ to server
     - merge: git merge --no-ff {BRANCH_2} into main
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ```

3. Issues a **single** AskUserQuestion:
   - header: "Approve All Actions"
   - question: "Review the consolidated action plan above. Approve to release all tasks, or cancel to hold."
   - options:
     - Approve all — release all task pipelines to execute
     - Cancel all — hold all tasks, no actions taken
     - Custom input (to approve selectively by task ID)

4. On **Approve all**: write `APPROVED` to `{TASK_DIR}/context/approval.md` for each task
5. On **Cancel all**: write `CANCELLED` to `{TASK_DIR}/context/approval.md` for each task, then stop

#### P2 — TaskList-based PLAN_READY detector (capability-gated)

The orchestrator reads
`${AGENT_CREW_HOME}/state/${PROJECT_NAME}/capabilities.json` once and caches
`HAS_TASK_TOOLS`. When `HAS_TASK_TOOLS == 1` the preferred fan-in path is a
single `TaskList()` round-trip filtered by `metadata.stage == "plan_ready"`
matching the run's task IDs. The file write is still the contract — the
`TaskList` call is only the fast convergence signal:

```text
HAS_TASK_TOOLS=$(python3 -c "
import json
try:
    print('1' if json.load(open('${CAPABILITIES_PATH}')).get('task_tools') else '0')
except Exception:
    print('0')
" 2>/dev/null)

if [ "${HAS_TASK_TOOLS}" = "1" ]; then
  # Preferred path: deterministic readiness check, one round-trip (no sleep).
  # P1 wrote TaskUpdate(status="blocked", metadata.stage="plan_ready") on each
  # task-runner's parent host task. We poll TaskList every 1s (long-poll if the
  # host supports wake-on-change) until every expected task is present.
  EXPECTED_TASK_IDS="{comma-separated list of TASK_IDs from this run}"
  ELAPSED=0
  while [ $ELAPSED -lt 120 ]; do
    READY=$(TaskList()
      | jq -r '.[] | select(.metadata.stage=="plan_ready") | .metadata.task_id'
      | sort -u)
    MISSING=$(comm -23 <(echo "$EXPECTED_TASK_IDS" | tr ',' '\n' | sort -u) \
                       <(echo "$READY"))
    if [ -z "$MISSING" ]; then
      break
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
  done
fi

# File-based fallback (always runs when HAS_TASK_TOOLS == 0, and as a safety
# backstop after the TaskList path when capability is enabled — the file is the
# source of truth, the host call is only the convergence signal).
for TASK_DIR in {all task dirs}; do
  until grep -q "PLAN_READY\|APPROVED\|CANCELLED" "${TASK_DIR}/context/approval.md" 2>/dev/null; do
    sleep 5
  done
done

# Read and consolidate all action plans
for TASK_DIR in {all task dirs}; do
  cat "${TASK_DIR}/context/action-plan.md"
done

# After AskUserQuestion decision, write result to each task. When the
# capability is enabled, ALSO transition each task-runner's parent host task —
# the TaskGet waiters inside P1 will wake on the next event without paying the
# 5-second file-poll cadence.
RESULT="APPROVED"  # or CANCELLED
for TASK_DIR in {all task dirs}; do
  echo "${RESULT}" > "${TASK_DIR}/context/approval.md"
  if [ "${HAS_TASK_TOOLS}" = "1" ]; then
    HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt" 2>/dev/null)
    if [ -n "$HOST_TASK_ID" ]; then
      # APPROVED → in_progress, CANCELLED → cancelled
      if [ "$RESULT" = "APPROVED" ]; then
        TaskUpdate(taskId=$HOST_TASK_ID, status="in_progress")
      else
        TaskUpdate(taskId=$HOST_TASK_ID, status="cancelled")
      fi
    fi
  fi
done
```

When `HAS_TASK_TOOLS == 0` the orchestrator runs only the legacy file-poll
loop above — identical behavior to pre-P2. The capability flag opts into a
faster wakeup; it never removes the file contract.

> **Orchestrator rule**: The orchestrator MUST NOT proceed to Step 7 until all
> task-runners have received their approval signal and resumed (or halted on
> CANCELLED). Task-runners that received CANCELLED must report STATUS: blocked
> with reason "Cancelled by consolidated approval gate."

---

### 7. Collect Results & Show Per-Task Summary

#### P4 — Background fan-out result collection

When task-runners were spawned as background host agents (Step 6 background
path, `HAS_AGENT_BACKGROUND == 1`), the orchestrator does NOT block on inline
Agent return values. Instead it polls each task's parent host task for
terminal status:

```text
# For every TASK_DIR in the run:
HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt")

# Wait for terminal status. TaskGet returns instantly on state change;
# the 2-second guard sleep bounds the busy-wait if the host returns
# synchronously. The total timeout matches the runner's worst-case
# pipeline duration (the orchestrator has no separate budget).
while true:
    STATUS = TaskGet(HOST_TASK_ID).status
    if STATUS in ("completed", "blocked", "cancelled"):
        break
    sleep 2
```

After all task-runners reach a terminal status, the orchestrator reads each
runner's `${TASK_DIR}/result.md` (canonical artifact) AND `TaskOutput` (live
event stream, when `HAS_MONITOR_TOOL == 1`) to assemble the Run Summary. When
both sources are available, `result.md` takes precedence — the host stream is
diagnostic only.

The crash-retry rule below applies identically: a runner whose
`TaskGet().status == "error"` (or whose `result.md` is missing after status
reached `completed`) is treated as a crash and re-spawned, up to 3 attempts.

When `HAS_AGENT_BACKGROUND == 0`: the orchestrator simply waits for the inline
Agent calls from Step 6 to return, as before. Behavior is identical to pre-P4.

#### Live Progress

Task-runners emit `[crew]`-prefixed lines throughout execution to surface
real-time lifecycle events. These lines appear inline as each phase and stage
boundary is crossed — the orchestrator does NOT suppress them. Example output
visible during a pipeline run:

```
[crew] 20260510-140000-0 | STARTED | implement order API
[crew] 20260510-140000-0 | PHASE | 1a — Requirement collection
[crew] 20260510-140000-0 | PHASE | 1b — Analysis
[crew] 20260510-140000-0 | PHASE | 1c — Planning
[crew] 20260510-140000-0 | PHASE | 1d — Plan approval
[crew] 20260510-140000-0 | STAGE | 1/2 — backend
[crew] 20260510-140000-0 | STAGE_DONE | backend — N/A
[crew] 20260510-140000-0 | STAGE | 2/2 — reviewer
[crew] 20260510-140000-0 | STAGE_DONE | reviewer — APPROVED
[crew] 20260510-140000-0 | COMPLETED | branch=feat/implement-order-api commits=3
```

In parallel runs (N > 1), each task-runner's TASK_ID prefix makes interleaved
lines from concurrent runners easy to distinguish.

**File-based progress log:** In addition to inline `[crew]` lines, every progress
event is written to `{TASK_DIR}/progress.log` as a timestamped line. Because
sub-agent inline output may be buffered until the agent completes, the progress
log provides a reliable source of truth for current pipeline state at any point
during execution. Run `crew:status` at any time to see the current pipeline state
read from this log. For N > 1, `crew:status` shows the most recently active task.

After all task-runners finish, the orchestrator prints the full Run Summary below.

**MANDATORY: Output the Run Summary block below to the user before proceeding to any next step. This cannot be skipped.**

For each task, read the result file to extract status and branch, and collect commits:

```bash
RESULT=$(cat "${TASK_DIR}/result.md" 2>/dev/null || echo "")
COMMITS=$(git -C "${PROJECT_ROOT_FOR_TASK}" log --oneline HEAD ^main 2>/dev/null || echo "N/A")
```

#### Missing or Incomplete Result Handling

If `result.md` is missing or the STATUS field is absent:

- Do **not** report "No result report found."
- Treat as a task-runner crash. Re-invoke the task-runner for that task.
- Pass the same `TASK_DIR` so the task-runner resumes from `pipeline.json`.
- Retry up to **3 times** per task.
- Only after all retries are exhausted: report the task as `blocked` with the
  reason "task-runner did not produce a result after 3 restart attempts."

In parallel runs (`N > 1`), apply this retry logic independently per task —
a crashed task-runner must not block result collection for other tasks.

Display a summary for every task. Do not proceed to Step 8 until the Run Summary has been printed to the user.

For each task, collect the per-file changes by reading the CHANGES section from
`result.md`. If CHANGES is absent, fall back to running git diff:

```bash
# List changed files for this task branch
git -C "${PROJECT_ROOT_FOR_TASK}" diff --name-only main...HEAD

# For each changed file, inspect the diff to write a Before/After description
git -C "${PROJECT_ROOT_FOR_TASK}" diff main...HEAD -- {file_path}
```

Write a one-line Before/After description for each changed file:
- Newly created file → Before: `(did not exist)`, After: brief description of purpose
- Deleted file → Before: brief description, After: `(removed)`
- Modified file → Before/After describe the key behavioral or structural change

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Run Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task 1: {description}
  Status : completed | blocked
  Branch : {branch}

  Changes:
    {file path 1}
      Before: {one-line description of what the file/section did before}
      After : {one-line description of what it does now}

    {file path 2}
      Before: {as-is}
      After : {to-be}

  Commits ({N}):
    {git log --oneline, up to 5 lines}

Task 2: {description}
  ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If any task has `STATUS: blocked`, do not proceed to deployment.
Report the blocker and stop.

---

### 8. Merge Branches (N > 1 only)

> **Skip this step entirely when N == 1.** For single-task runs, proceed directly
> to Step 9. The feature branch will be pushed as-is in Step 10.

When `N > 1`, merge all task feature branches into `main` locally before
showing the deployment plan:

```bash
git checkout main
for BRANCH in {all task branches}; do
  git merge --no-ff "${BRANCH}" -m "merge: ${BRANCH} into main"
done
```

If a merge conflict occurs during any merge, invoke the conflict resolver before
continuing:

```text
crew:run "resolve merge conflicts"
```

Do not proceed to Step 9 until all merges complete cleanly.

After all merges succeed, collect the combined commit log for the deployment plan:

```bash
git log --oneline HEAD ^origin/main | head -10
```

---

### 9. Implementation Summary

Always display the implementation summary for every completed run, regardless of
whether a devops stage was included in the pipeline:

**When N > 1 (after merge):**

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Implementation Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Merged branches into main (local):
  - {BRANCH_1}  ({N} commits)
  - {BRANCH_2}  ({N} commits)

Commits ready for push (origin/main..HEAD):
  {git log --oneline origin/main..HEAD, up to 10 lines}

Note: No remote push has occurred yet.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**When N == 1:**

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Implementation Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Branch with local commits:
  - {BRANCH}  ({N} commits)

Commits ready for review:
  {git log --oneline HEAD ^main, up to 5 lines}

Note: No remote push has occurred yet.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

> **Stop here.** Do not suggest any follow-up action (merge, push, PR creation,
> test runs, or anything else). The run is complete. If the user wants to deploy
> or push, they will request it explicitly — do not volunteer it.

---

### 10. Deployment Approval

> **Explicit deploy requests only.** Steps 10–11 execute only when the user
> explicitly requests deployment after Step 9 — never proactively. When
> deployment is requested, delegate to the **devops agent**. The orchestrator
> must not run `git push` directly. The devops agent owns the approval gate
> (AskUserQuestion) and execution.

**Only execute this step when the pipeline included a `devops` stage that will
run CI/CD (i.e., a stage whose agent is `devops`).**

If no `devops` stage was in the pipeline, skip this step entirely and stop after
Step 9. Branches remain local; the user can push manually.

When a `devops` stage is present, first compose and display the deployment plan:

**When N > 1:**

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Deployment Plan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Action: push main to origin (all task branches merged)

Commits to be published (origin/main..HEAD):
  {git log --oneline origin/main..HEAD}

Target remote: origin
Risk notes:
  - {any merge conflicts detected?}
  - {any blocked tasks?}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**When N == 1:**

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Deployment Plan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Branch to push:
  - {BRANCH}  ({N} commits)

Commits to be published:
  {git log --oneline HEAD ^main}

Target remote: origin
Risk notes:
  - {any merge conflicts detected?}
  - {any blocked tasks?}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Then use **AskUserQuestion** to request approval. Do not proceed without it.

**Plain-text approval is FORBIDDEN.** Never ask "Shall I merge and push?", "Should I deploy?", or any equivalent free-form question. The AskUserQuestion structured UI is the only permitted approval method for deployment, push, and merge operations.

**When N > 1:**

Question:
- header: "Deploy"
- question: "Review the deployment plan above. Approve to push main to remote, or cancel to hold."
- options:
  - Approve — push main to origin now
  - Cancel — hold, do not push (branches remain local)

**When N == 1:**

Question:
- header: "Deploy"
- question: "Review the deployment plan above. Approve to push to remote, or cancel to hold."
- options:
  - Approve — push the feature branch to origin now
  - Cancel — hold, do not push (branch remains local)

If **Approve**:
  - Proceed to Step 11.

If **Cancel**:
  - Print the branch name(s) so the user can push manually later.
  - Stop here. Do not push anything.

---

### 11. Execute Deployment

**When N > 1 (merged into main):**

```bash
git push origin main
```

**When N == 1 (feature branch only):**

```bash
git push origin "${BRANCH}"
```

Report result:

```text
Deployment complete.
Pushed: {main | branch name}
```

If a push conflict occurs, run:

```text
crew:run "resolve merge conflicts"
```

---

## Notes

- `crew:run` is the canonical workflow entry point.
- Use plain `crew:<intent>` syntax in user-facing guidance.
- Task dependencies still matter. If tasks depend on each other, pass them as a
  single request so one `task-runner` can sequence the work inside one pipeline.
- **task-runner never pushes to remote.** All remote operations happen here in
  Step 11, only after explicit user approval in Step 10.
- **Step 8 (merge) applies only to parallel runs (N > 1).** For single-task runs,
  the feature branch is pushed directly without merging to main.
