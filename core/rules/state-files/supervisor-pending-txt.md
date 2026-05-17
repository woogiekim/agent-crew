# supervisor-pending.txt

## Purpose

Written by the orchestrator immediately before spawning each supervisor as a
background agent. Signals to external observers (crew:status, crew:status
--collect) that a supervisor is booting but has not yet called TaskCreate and
written host-task-id.txt.

Deleted by the supervisor in Phase 0, immediately after writing
host-task-id.txt. When HAS_TASK_TOOLS == 0 (TaskCreate skipped), the
supervisor still deletes the sentinel — its purpose is "supervisor reached
Phase 0", not specifically "TaskCreate ran".

## File location

```
${TASK_DIR}/supervisor-pending.txt
```

## Format

Two-line plain text:

```
spawned_at=<ISO-8601 UTC timestamp, e.g. 2026-05-17T14:32:09Z>
session_id=<SESSION_ID>
```

## Lifecycle

| Event | Action |
|---|---|
| Orchestrator Step 6 P4 spawn | Written (one per task, before Agent call) |
| Supervisor Phase 0 after TaskCreate | Deleted (rm -f, idempotent) |
| crew:status / crew:status --collect | Read to classify boot window |

## Boot window classification (crew:status)

When host-task-id.txt is absent AND supervisor-pending.txt is present:

- age < AGENT_CREW_SUPERVISOR_BOOT_TIMEOUT_SECONDS (default 30): render task as **booting**
- age >= timeout: render task as **stalled — supervisor failed to register**

## Absence behavior

When supervisor-pending.txt is absent AND host-task-id.txt is absent: the
supervisor has either already completed Phase 0 (pre-sentinel install) or
the task directory is stale. Fall through to legacy file-poll behavior.

## Idempotency

rm -f is always safe — the supervisor deletes on every Phase 0 completion
regardless of whether the file exists. Re-running crew:update does not create
or remove this file (it is a runtime state file, not an installed asset).

## Related files

- ${TASK_DIR}/host-task-id.txt — written by supervisor Phase 0 after TaskCreate
- ${STATE_DIR}/session.json — written by orchestrator Step 4; contains spawned_at per task
- core/commands/run.md — Step 6 P4 spawn loop (writes this file)
- core/agents/supervisor-bootstrap.md — Phase 0 (deletes this file)
- core/commands/status.md — Step 1b / Step 3S (reads this file)
