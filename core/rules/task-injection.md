# Task Injection Protocol

## Purpose

Task injection allows new tasks to be submitted and appended to an active
parallel `crew:run` execution fan-out while existing task-runners are still in
progress. Injected tasks join the live session, run in their own worktrees, and
participate in the final result collection, resolver, and approval gates
alongside the original tasks.

## Canonical Entry Point

Task injection is handled entirely within `core/commands/run.md` Step 1.5
(Injection Detection). This file is the protocol reference; `run.md` is the
authoritative implementation spec.

## Session File

The session registry is stored at:

```
${AGENT_CREW_HOME}/state/${PROJECT_NAME}/session.json
```

### Schema

```json
{
  "session_id": "20260515-140000",
  "status": "running",
  "pre_run_head": "<SHA>",
  "tasks": [
    {
      "task_id": "20260515-140000-0",
      "task_dir": "/path/to/task/dir",
      "branch": "feat/implement-order-api",
      "task": "implement order API",
      "status": "running",
      "injected": false
    },
    {
      "task_id": "20260515-141500-0",
      "task_dir": "/path/to/injected/task/dir",
      "branch": "feat/implement-product-api",
      "task": "implement product API",
      "status": "running",
      "injected": true
    }
  ]
}
```

### Status values

| `session.status` | Meaning |
|---|---|
| `running` | Live session accepting injections |
| `completed` | All tasks finished; session closed |
| `blocked` | One or more tasks blocked the session |

| `task.status` | Meaning |
|---|---|
| `running` | Task-runner in progress |
| `completed` | Task-runner wrote `result.md` with STATUS: completed |
| `blocked` | Task-runner terminated with STATUS: blocked |

## Lifecycle

### Normal parallel run (N > 1, no injection)

```
crew:run "Task A" | "Task B"
    └─► Step 4: create TASK_DIR, worktree per task
    └─► Step 4 session init: write session.json {status: running, tasks: [A, B]}
    └─► Step 6: spawn task-runners for A and B
    └─► Step 7: collection loop polls session.json; marks each task completed
    └─► Step 7 session close: write session.json {status: completed}
    └─► Step 8: merge all branches from session.json[tasks]
```

### Injection into live run

```
crew:run "Task C"  (while A and B are still running)
    └─► Step 1.5: detect session.json {status: running}
    └─► Inject path: create TASK_DIR, worktree for C
    └─► Step 5: collect requirements for C
    └─► Step 6: spawn task-runner for C
    └─► Append C to session.json tasks with injected: true
    └─► Original orchestrator's Step 7 loop picks up C on next poll
    └─► C participates in merge (Step 8) and summary (Step 9)
```

## Detection Rules

The injection path is entered when **all** of these conditions hold:

1. `session.json` exists at `${STATE_DIR}/session.json`.
2. `session.json.status == "running"`.
3. `session.json` file mtime is less than 24 hours ago (not abandoned).
4. Either `--inject` flag was passed, OR the user confirms injection when
   prompted (N > 1 without `--inject`).

If any condition fails, `crew:run` starts a fresh session normally.

## Injection Guard

The following conditions MUST prevent injection (treated as IS_LIVE_SESSION=0):

- `session.json` is absent (no active session exists).
- `session.json.status` is `"completed"` or `"blocked"` (stale).
- `session.json` file is older than 24 hours (abandoned — stale marker).
- `STATE_DIR` does not exist (`crew:setup` not yet run).

## Progress Events

Injection emits the following `[crew]` progress line:

```
[crew] INJECT | session={SESSION_ID} | {N} new task(s) joining live run
```

This is written to the injecting process's stdout but not to any single
`progress.log` (injected tasks write to their own `TASK_DIR/progress.log`).

## Session Ownership

The session is owned by the orchestrator that created it (the original
`crew:run` invocation). The injecting `crew:run` call acts as a thin
dispatcher: it prepares context, collects requirements, spawns the task-runner,
registers the task in `session.json`, and returns. It does NOT run its own
result collection loop or its own merge/approval gates for the injected tasks.

The original orchestrator's collection loop (Step 7) detects injected tasks by
re-reading `session.json` on each iteration, and includes them in the final
merge (Step 8) and summary (Step 9) automatically.

## Concurrent Write Safety

Both the original orchestrator and the injecting `crew:run` write to
`session.json`. To prevent data corruption from concurrent writes:

1. Each write is performed by a single `python3 -c` call that reads, modifies,
   and atomically re-dumps the file. Python's `json.dump` is not atomic on
   POSIX, but the window for corruption is microseconds wide. For MVP scope,
   this level of risk is acceptable.
2. All writes append to the `tasks` array — they do not overwrite existing
   entries. The only mutation to existing entries is updating `task.status`,
   which is idempotent.
3. The session-status write (`status: completed`) is performed only by the
   original orchestrator after it has confirmed all tasks are terminal.

If a future release requires stronger guarantees (e.g., for 10+ concurrent
injectors), a file-locking protocol using `flock` or a SQLite-backed store
should replace the JSON file.

## Relationship to Existing Pipeline

Task injection is an extension of the existing parallel fan-out model. It
reuses:

- Step 4 context preparation (TASK_ID, TASK_DIR, branch, worktree)
- Step 5 requirements collection
- Step 6 task-runner spawn (background or inline, same capability path)
- Step 7 result collection (extended to monitor `session.json`)
- Step 8 merge (reads branch list from `session.json`)
- Step 9 summary (shows `[injected]` tag for injected tasks)
- Task-runner Phase 0–3 (unchanged; EXECUTION_MODE=parallel)

No changes are required to `task-runner.md`. Injected tasks run identically to
original tasks from the task-runner's perspective.

## Related Files

- `core/commands/run.md` — authoritative implementation (Step 1.5, Step 4, Step 7, Step 8)
- `core/agents/task-runner.md` — unchanged; handles injected tasks the same as original tasks
- `core/rules/capabilities/agent-background.md` — `agent_background` flag
  for background fan-out used by the injection path
- `core/rules/capabilities/task-tools.md` — `task_tools` flag for TaskGet
  wakeup used by the injection path
