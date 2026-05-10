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

If `N == 1`, check for the newest incomplete task under `STATE_DIR/tasks`.
If one exists, ask whether to resume it or start a new run.

If resuming:

- reuse the existing `TASK_ID`
- reuse the existing `TASK_DIR`
- reuse the recorded branch or worktree metadata if present
- continue through the same `task-runner`

If `N > 1`, always start a new fan-out run.

### 4. Prepare Each Task Context

For each task index `i`:

```bash
TASK_ID="$(date +%Y%m%d-%H%M%S)-${i}"
TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
BRANCH="feature/task-${TASK_ID}"
```

Execution context depends on cardinality:

- If `N == 1`, the orchestrator may use the current project worktree or a
  dedicated worktree, but it still delegates to exactly one `task-runner`.
- If `N > 1`, create one isolated git worktree per task:

```bash
WORKTREE_PATH="${PROJECT_ROOT}/.crew-worktrees/${TASK_ID}"
mkdir -p "${TASK_DIR}/context"
git worktree add -b "${BRANCH}" "${WORKTREE_PATH}" HEAD
```

The orchestrator owns context preparation only. The execution engine remains the
same in both modes.

### 5. Collect Requirements Per Task

Before confirming execution, collect requirements for each task using a **two-round deep interview** via **AskUserQuestion**.

#### Round 1 — Base Context

For each task `i`, invoke AskUserQuestion with three questions:

**Question 1 — Implementation scope:**
- header: "Task {i+1} — Scope"
- question: "What is the implementation scope for: {task description}?"
- options:
  - Backend API (Server-side logic, domain model, database)
  - Full-stack (Backend + Frontend UI)
  - UI only (Static pages, components, styling)
  - Analysis only (PRD / design, no implementation needed)

**Question 2 — Target users and feature purpose:**
- header: "Task {i+1} — Target"
- question: "Who are the target users, and what is the core purpose of this feature?"
- options:
  - Internal team / admin tooling
  - End-user product feature
  - Developer tooling or API
  - Other / not yet defined

**Question 3 — Technical constraints or MVP scope:**
- header: "Task {i+1} — Constraints"
- question: "Are there technical constraints or MVP scope limits to consider?"
- multiSelect: true
- options:
  - Use existing tech stack only (no new dependencies)
  - MVP — minimal feature set, defer polish
  - Performance or scalability requirements apply
  - Security or compliance constraints apply
  - No special constraints

Record the Round 1 answers: `scope`, `target`, `constraints`.

#### Round 2 — Domain-Specific Follow-up

Analyze the `scope` answer from Round 1 and ask 1–2 additional domain-specific questions.
Skip Round 2 entirely if scope is **"Analysis only"**.

**If scope is "Backend API":**

Question A — Database:
- header: "Task {i+1} — Database"
- question: "Which database or storage solution will this API use?"
- options:
  - PostgreSQL / MySQL (relational)
  - MongoDB / DynamoDB (document / NoSQL)
  - Redis (cache / key-value)
  - Existing DB — match the current stack
  - Not yet decided

Question B — Authentication:
- header: "Task {i+1} — Auth"
- question: "What authentication method will this API use?"
- options:
  - JWT (stateless token)
  - Session-based (server-side)
  - OAuth 2.0 / OpenID Connect
  - API key
  - No authentication required

**If scope is "Full-stack":**

Question A — State management:
- header: "Task {i+1} — State Management"
- question: "How should client-side state be managed?"
- options:
  - Local component state only (useState / hooks)
  - Global store (Redux, Zustand, Pinia, etc.)
  - Server state library (React Query, SWR, etc.)
  - Match the existing project pattern

Question B — Database:
- header: "Task {i+1} — Database"
- question: "Which database or storage solution will the backend use?"
- options:
  - PostgreSQL / MySQL (relational)
  - MongoDB / DynamoDB (document / NoSQL)
  - Redis (cache / key-value)
  - Existing DB — match the current stack
  - Not yet decided

**If scope is "UI only":**

Question A — State management:
- header: "Task {i+1} — State Management"
- question: "How should client-side state be managed?"
- options:
  - Local component state only (useState / hooks)
  - Global store (Redux, Zustand, Pinia, etc.)
  - Server state library (React Query, SWR, etc.)
  - Match the existing project pattern

Question B — Design system:
- header: "Task {i+1} — Design System"
- question: "Which design system or component library should be used?"
- options:
  - Follow the existing project design system
  - Tailwind CSS (utility-first)
  - Material UI / Ant Design / shadcn/ui
  - Plain CSS / CSS Modules
  - No design system — custom only

After Round 2 AskUserQuestion calls return, record the additional answers as `followup` fields.

#### Merge into REQUIREMENTS

Combine all Round 1 and Round 2 answers into a single REQUIREMENTS object for this task:

```text
REQUIREMENTS:
  scope: {answer to Question 1}
  target: {answer to Question 2}
  constraints: {answer(s) to Question 3}
  followup:
    {field_name}: {Round 2 answer A}
    {field_name}: {Round 2 answer B}
```

Where `{field_name}` matches the domain:
- Backend API: `database`, `auth`
- Full-stack: `state_management`, `database`
- UI only: `state_management`, `design_system`
- Analysis only: _(no followup fields)_

Repeat for each task. If `N > 1`, collect requirements for all tasks before proceeding.

### 6. Confirm Execution

Ask for structured approval and show:

```text
Tasks: {N}
Mode: single-run or parallel fan-out
Execution engine: task-runner
```

Options:

```text
[A] Start
[B] Cancel
[C] Custom input
```

If cancelled, clean up any worktrees or task directories created for the run.

### 7. Run Task Runners

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

### 8. Collect Results & Show Per-Task Summary

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

Display a summary for every task:

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Run Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task 1: {description}
  Status : {completed | blocked}
  Branch : {branch}
  Commits: {N}
  Log    : {git log --oneline, up to 5 lines}
  Review : {APPROVED | NEEDS_CHANGES | N/A}

Task 2: {description}
  ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If any task has `STATUS: blocked`, do not proceed to deployment.
Report the blocker and stop.

---

### 9. Merge Branches (N > 1 only)

> **Skip this step entirely when N == 1.** For single-task runs, proceed directly
> to Step 10. The feature branch will be pushed as-is in Step 12.

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

Do not proceed to Step 10 until all merges complete cleanly.

After all merges succeed, collect the combined commit log for the deployment plan:

```bash
git log --oneline HEAD ^origin/main | head -10
```

---

### 10. Implementation Summary

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

### 11. Deployment Approval

**Only execute this step when the pipeline included a `devops` stage that will
run CI/CD (i.e., a stage whose agent is `devops`).**

If no `devops` stage was in the pipeline, skip this step entirely and stop after
Step 10. Branches remain local; the user can push manually.

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
  - Proceed to Step 12.

If **Cancel**:
  - Print the branch name(s) so the user can push manually later.
  - Stop here. Do not push anything.

---

### 12. Execute Deployment

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
  Step 12, only after explicit user approval in Step 11.
- **Step 9 (merge) applies only to parallel runs (N > 1).** For single-task runs,
  the feature branch is pushed directly without merging to main.
