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

### 5. Confirm Execution

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

Complete this task autonomously through the full pipeline.
Write the completion report to {TASK_DIR}/result.md.
```

Wait for all task-runners to finish.

### 7. Collect Results

For each task:

```bash
RESULT=$(cat "${TASK_DIR}/result.md" 2>/dev/null || echo "No result report found.")
```

Report:

```text
Run complete.

Task 1: {description}
Branch: {branch}
Status: {status}
Commits: {git log summary}

Task 2: {description}
Branch: {branch}
Status: {status}
Commits: {git log summary}
```

If a merge conflict occurs, run:

```text
crew:run "resolve merge conflicts"
```

## Notes

- `crew:run` is the canonical workflow entry point.
- `@crew:run` may be exposed as a compatibility alias on hosts that support it.
- Task dependencies still matter. If tasks depend on each other, pass them as a
  single request so one `task-runner` can sequence the work inside one pipeline.
