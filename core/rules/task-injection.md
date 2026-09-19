# Task Injection Protocol

## Purpose

Task injection allows new tasks to be submitted and appended to an active
parallel `crew:run` execution fan-out while existing supervisors are still in
progress. Injected tasks join the live session, run in their own worktrees, and
participate in the final result collection, resolver, and approval gates
alongside the original tasks.

## Canonical Entry Point

Task injection is handled entirely within `core/commands/run.md` Step 1.5
(Injection Detection). This file is the protocol reference; `run.md` is the
authoritative implementation spec.

## Operator-Facing Messages

Active-work messages are concise by default. When a live session, duplicate
task, injected task, or stale session is detected, show only the useful
coordinates: session id, task id, current phase or status, and the next command
when one exists. Do not include long policy narration, repeated workflow
explanations, or troubleshooting detail unless the operator explicitly asks for
verbose output.

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
  "execution_policy": "background",
  "pre_run_head": "<SHA>",
  "tasks": [
    {
      "task_id": "20260515-140000-0",
      "task_dir": "/path/to/task/dir",
      "branch": "feat/implement-order-api",
      "task": "implement order API",
      "task_hash": "implement order api",
      "status": "running",
      "injected": false
    },
    {
      "task_id": "20260515-141500-0",
      "task_dir": "/path/to/injected/task/dir",
      "branch": "feat/implement-product-api",
      "task": "implement product API",
      "task_hash": "implement product api",
      "status": "running",
      "injected": true,
      "background_id": "host-background-invocation-id"
    }
  ]
}
```

### `task_hash` field

Added in Phase B0 to support Step 1.6 (Duplicate Task Detection) in
`core/commands/run.md`. The value is the **normalized form** of the task
description string — not a cryptographic hash, just a deterministic
canonicalization. Equality of `task_hash` is the duplicate signal.

Normalization algorithm (must match the producer in `run.md` Step 1.6):

1. Convert the task description to lowercase.
2. Collapse internal whitespace (any run of spaces / tabs / newlines → one
   space).
3. Strip leading and trailing whitespace.
4. Strip trailing ASCII punctuation `. , ; : ! ?` (any number of repeats).

Concretely:

```python
def task_hash(task: str) -> str:
    import re
    h = re.sub(r"\s+", " ", task).strip().lower()
    h = re.sub(r"[.,;:!?]+$", "", h)
    return h
```

Examples:

| Raw task | task_hash |
|---|---|
| `"Implement order API"` | `"implement order api"` |
| `"implement order API."` | `"implement order api"` |
| `"  implement   order API!  "` | `"implement order api"` |

### Backward compatibility

Pre-B0 `session.json` files do not have `task_hash`. Step 1.6 consumers MUST
treat a missing `task_hash` on any tasks[] entry as "cannot dedupe; assume
unique" — never as an empty-string match. The new field is additive; the
rest of the schema is unchanged and tolerant of mixed pre/post-B0 entries
within the same array.

Pre-execution-policy session files omit `execution_policy`. Consumers must not
guess that such a running session is injectable. New default foreground
sessions record `foreground`; only `background` is eligible for injection.
An operator may finish an already known legacy background session only through
an explicit recovery/migration decision.

> **Note**: `task_hash` is NOT mirrored to the per-task
> `{TASK_DIR}/register.json` (Phase F4). session.json is the sole
> dedup source — `register.json` carries per-task pointer state, not
> session-level identity. Duplicating the hash there would create two
> writers for the same field with no consensus rule.

### Status values

| `session.status` | Meaning |
|---|---|
| `running` | Session has active work; injection additionally requires `execution_policy=background` |
| `completed` | All tasks finished; session closed |
| `blocked` | One or more tasks blocked the session |

| `task.status` | Meaning |
|---|---|
| `running` | Task-runner in progress |
| `completed` | Task-runner wrote `result.md` with STATUS: completed |
| `blocked` | Task-runner terminated with STATUS: blocked |

Every new explicit-background task records the host-returned `background_id`.
The finalizer observes that id so a terminal host error or a terminal invocation
with a missing `result.md` consumes bounded retry/resume budgets and becomes an
explicit blocker instead of an unbounded file poll.

## Lifecycle

### Explicit background parallel run (N > 1, no injection)

```
crew:run --background "Task A" | "Task B"
    └─► Step 4: create TASK_DIR, worktree per task
    └─► Step 4 session init: write session.json {status: running, tasks: [A, B]}
                              (each task gets a task_hash field — see Schema above)
    └─► Step 6: spawn supervisors for A and B
    └─► Starting turn returns after supervisors are registered
    └─► crew:status monitors session.json without finalizing it
    └─► Explicit finalizer collects terminal results and closes the session
```

### Injection into live run

```
crew:run --inject "Task C"  (while explicit-background A and B are running)
    └─► Step 1.5: detect session.json {status: running}
    └─► Inject path: create TASK_DIR, worktree for C
    └─► Step 5: collect requirements for C
    └─► Step 6: spawn supervisor for C
    └─► Append C to session.json tasks with injected: true
    └─► Explicit background finalizer picks up C from session.json
    └─► C participates in terminal collection and finalization
```

## Detection Rules

The injection path is entered when **all** of these conditions hold:

1. `session.json` exists at `${STATE_DIR}/session.json`.
2. `session.json.status == "running"`.
3. `session.json` file mtime is less than 24 hours ago (not abandoned).
4. Either `--inject` flag was passed, OR the user confirms injection when
   prompted.

If any condition fails, `crew:run` starts a fresh session normally.

> **Related: duplicate-task disambiguation.** When the live session
> detector finds a running session, `run.md` Step 1.6 additionally
> compares the new task's `task_hash` against the `task_hash` of every
> running tasks[] entry. A match routes through
> `core/rules/disambiguation.md` for a user choice; it does NOT bypass
> these detection rules. See `run.md` Step 1.6 for the full flow.

## Host-Capability Guard

Before evaluating the Detection Rules below, check whether the current host
supports background agents. Task injection requires an existing session that
was started with explicit `--background`, so the orchestrator's turn ended
after spawning supervisors (the P4 background fan-out path). Default
foreground runs never create an injection window. On hosts where
`HAS_AGENT_BACKGROUND=0` (Codex, generic adapters), the orchestrator runs inline
and its turn does not yield a supported injection window while supervisors are
running. A host UI may accept interrupting user input during a foreground wait,
but that interruption does not provide task injection and must not be
misclassified as background execution.

When `HAS_AGENT_BACKGROUND=0`, treat `IS_LIVE_SESSION` as `0` regardless of
`session.json` state:

```bash
if [ "${HAS_AGENT_BACKGROUND}" = "0" ] && [ "${IS_LIVE_SESSION}" = "1" ]; then
  # Inline hosts block during execution — mid-run injection is impossible.
  # Warn the user and fall through to a fresh session.
  echo "[crew] WARN: Task injection is not supported on this host (agent_background=false)."
  echo "       Inline hosts block during execution — no mid-run injection possible."
  echo "       Tip: queue all tasks upfront: crew:run \"Task A\" | \"Task B\" | \"Task C\""
  IS_LIVE_SESSION=0  # treat as fresh run
fi
```

This guard runs in `run.md` Step 1.5 before any injection routing. The
`HAS_AGENT_BACKGROUND` flag is loaded once at Phase 0 from `capabilities.json`
(see `core/rules/capabilities/agent-background.md`).

**Affected hosts:** Codex (`agent_background=false`), generic adapter
(`agent_background=false`). For a per-adapter summary, see
`adapters/codex/invocation.md` § Limitations.

## Injection Guard

The following conditions MUST prevent injection (treated as IS_LIVE_SESSION=0):

- `HAS_AGENT_BACKGROUND=0` (host does not support background agents — see Host-Capability Guard above).
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
explicit-background `crew:run --background` invocation). The injecting
`crew:run --inject` call acts as a thin
dispatcher: it prepares context, collects requirements, spawns the supervisor,
registers the task in `session.json`, and returns. It does NOT run its own
result collection loop or its own merge/approval gates for the injected tasks.

The explicit background finalizer detects injected tasks by re-reading
`session.json`, and includes them in terminal collection and finalization.
`crew:status` is read-only monitoring and never substitutes for finalization.

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
- Step 6 supervisor spawn (background or inline, same capability path)
- Step 7 result collection (extended to monitor `session.json`)
- Step 8 merge (reads branch list from `session.json`)
- Step 9 summary (shows `[injected]` tag for injected tasks)
- Task-runner Phase 0–3 (unchanged; EXECUTION_MODE=parallel)

No changes are required to `supervisor.md`. Injected tasks run identically to
original tasks from the supervisor's perspective.

## Related Files

- `core/commands/run.md` — authoritative implementation (Step 1.5, Step 4, Step 7, Step 8)
- `core/agents/supervisor.md` — unchanged; handles injected tasks the same as original tasks
- `core/rules/capabilities/agent-background.md` — `agent_background` flag
  for background fan-out used by the injection path
- `core/rules/capabilities/task-tools.md` — `task_tools` flag for TaskGet
  wakeup used by the injection path
