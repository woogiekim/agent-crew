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

## Execution Steps

### 1. Collect Tasks

Use provided arguments as task descriptions. If none are provided, ask through
the host AI tool's structured input UI.

Accept:

- One task: `crew:run "implement order API"`
- Multiple tasks: `crew:run "Order API" | "Product API" | "User API"`

Normalize the input into a task list with cardinality `N >= 1`.

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
BRANCH="feature/task-${TASK_ID}"
```

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

For each task `i`, delegate to the **requirements agent** (blocking):

```text
TASK: {task description}
TASK_INDEX: {i}
TASK_DIR: {TASK_DIR}

Run the 2-round AskUserQuestion interview, validate scope, detect ambiguities,
write {TASK_DIR}/context/requirements.md, and return the REQUIREMENTS block.
```

Wait for the requirements agent to return. Extract the `REQUIREMENTS` block from its
response and record it for this task.

Repeat for each task. If `N > 1`, collect requirements for all tasks **before** proceeding
to Step 6 (run task-runners). Do not run task-runners while requirements collection is
still in progress for any task.

### 6. Run Task Runners

Delegate one `task-runner` per task.

- If `N == 1`, invoke one `task-runner`.
- If `N > 1`, invoke all `task-runner` agents concurrently when supported.

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

This "끈질기게 실행" (persistent execution) rule means the orchestrator never
gives up on a task-runner until it explicitly returns `STATUS: blocked` with a
real, substantive blocker.

Wait for all task-runners to finish (including any crash-retry cycles).

### 7. Collect Results & Show Per-Task Summary

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

---

### 10. Deployment Approval

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
