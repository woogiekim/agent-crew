# task_tools Capability

## Purpose

The host exposes structured task lifecycle tools (TaskCreate, TaskList,
TaskGet, TaskUpdate). One flag powers two distinct things that share the
same surface:

- **Observability mirror.** The task-runner registers each pipeline (and
  each stage as a child task) so external observers — `crew:status`, the
  host's task UI — can see lifecycle state without parsing `pipeline.json`.
  The per-stage `blockedBy` DAG is the canonical home for stage-dependency
  state when this flag is true.
- **Approval-signal carrier.** Plan-approval and stage-action gates carry
  their wakeup through `updateTask(status="blocked")` rather than a
  5-second `approval.md` poll. `getTask` long-poll receives the
  approve/cancel transition. `approval.md` remains the contractual
  artifact; the host call is the wakeup signal only.

Both uses are gated by the same flag because they rely on the same
minimal tool quartet.

## Required Adapter Surface (flag=true)

Adapter MUST expose host tools that fulfill this abstract contract:

| Abstract call | Purpose |
|---|---|
| `createTask(name, metadata?) -> taskId` | Register a new task or child task in the host's surface |
| `listTasks(filter?) -> [{ taskId, status, blockedBy? }]` | Enumerate tracked tasks |
| `getTask(taskId) -> { status, output?, metadata? }` | Fetch current state and (optionally) the latest output tail |
| `updateTask(taskId, { status, metadata? })` | Transition a task's status and attach metadata |

Notes:

- Status vocabulary: `pending | in_progress | blocked | completed | cancelled`.
- `blockedBy` is used for the per-stage DAG mirror (pattern P3 — see
  `core/agents/task-runner.md` Phase 1c-bis).
- `metadata.action_plan_path` is the agreed key used by the
  approval-signal pattern (P1 + P6) to carry the path to a plan that
  needs user approval.
- `getTask` MUST distinguish token-truncation tails from real crashes
  (pattern P7 — `core/agents/task-runner.md` Stage Retry Rule). If the
  host cannot make this distinction natively, the adapter wraps the call
  so the contract still holds.

The adapter binds these abstract calls to its native tool names in
`adapters/{host}/invocation.md`.

## Consumer Contract (core)

Core reads `${STATE_DIR}/capabilities.json["task_tools"]` once at
lifecycle entry and passes the boolean to every later check. Concrete
call sites:

- **task-runner Phase 0** — capability bootstrap; loads the flag.
- **task-runner Phase 1c-bis** — per-stage `createTask` with `blockedBy`
  DAG (P3).
- **task-runner Phase 2** — `updateTask(in_progress | completed | blocked)`
  per stage emit.
- **task-runner Phase 2.5** — `updateTask(blocked)` carries plan-ready;
  `getTask` long-poll wakes the orchestrator on approval (P1 + P6).
- **task-runner Stage Retry Rule** — `getTask().status` classifies crash
  vs token-truncation (P7).
- **`core/commands/run.md` Step 6 Task-Runner Health Check** —
  `getTask`-based crash classification (P7).
- **`core/commands/run.md` Step 7.5** — `listTasks`-based PLAN_READY
  detector (P2); `updateTask(in_progress | cancelled)` releases waiters
  (P1 + P6).
- **`core/commands/status.md` Step 1b** — `listTasks` preferred for stage
  state when the flag is true.

Core's input shape is the boolean flag. The output shape from host calls
is `taskId` (string), status enum values, optional output text, and a
metadata dict.

## Absence Behavior (flag=false)

File-based fallback (always works in parallel — never replaced even when
the flag is true):

- `pipeline.json` + `progress.log` are the primary state; no host mirror.
- `crew:status` tails `progress.log`; no DAG mirror; no token-truncation
  classification (any non-zero exit is treated as a crash).
- Approval gates use the 5-second `approval.md` poll loop; no
  `updateTask` wakeup signal.

Canonical loader snippet, re-used by every capability:

```python
import json, os

def load_capabilities(agent_crew_home: str, project_name: str) -> dict:
    path = os.path.join(agent_crew_home, "state", project_name, "capabilities.json")
    try:
        return json.load(open(path))
    except Exception:
        return {}  # missing or unparseable → every flag is false
```

## Adapter Examples

| Adapter | task_tools | How it is implemented |
|---|---|---|
| claude  | true  | Native `TaskCreate` / `TaskList` / `TaskGet` / `TaskUpdate` tools |
| codex   | false | No equivalent tool surface today; uses `pipeline.json` + 5-second `approval.md` poll |
| generic | false | No host task surface; file-based fallback only |

## Related Files

Producer:

- `adapters/claude/setup.sh` (writes flag true)

Consumer:

- `core/agents/task-runner.md`
- `core/commands/run.md` (Step 6, Step 7.5)
- `core/commands/status.md` (Step 1b)
- `core/rules/task-injection.md` (TaskGet wakeup in the injection path)

Cross-flag:

- The approval lifecycle also touches `interactive_question` for the
  plan/cancel UX (which option the user picks); the two flags are
  independent. See `core/rules/capabilities/interactive-question.md`.
