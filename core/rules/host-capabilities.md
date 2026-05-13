# Host Capabilities Contract

## Purpose

Some host adapters (notably Claude Code) expose richer task-tracking surfaces
than the file-based progress.log + pipeline.json model the core pipeline depends
on. To stay provider-neutral, the core pipeline depends on a small capability
contract instead of any specific host API. Host adapters declare their
capabilities at setup time; the core pipeline reads them and opts into the
richer surfaces only when the capability is advertised.

This file documents the full progressive-adoption ladder. All three layers are
now implemented; each is gated by a different capability flag and falls back to
the file-based source of truth when the flag is `false`.

- **Layer 1** — capability detection + observability mirror (TaskCreate for the
  parent task, TaskList preferred for `crew:status` stage state). Gated by
  `task_tools`.
- **Layer 2** — background fan-out (orchestrator spawns task-runners as host
  background agents) and TaskOutput consumption in `crew:status`. Gated by
  `agent_background` and `monitor_tool` respectively. Both keep
  `progress.log` / `pipeline.json` as the canonical artifact.
- **Layer 3** — approval-signal carrier on `TaskUpdate` (status=blocked → user
  decides → status=in_progress|cancelled). Gated by `task_tools`.
  `approval.md` remains the contractual artifact; the host call is the wakeup
  signal only.

## File Location

```
${AGENT_CREW_HOME}/state/${PROJECT_NAME}/capabilities.json
```

- Written by the host adapter's `setup.sh` (e.g., `adapters/claude/setup.sh`).
- Read by the core pipeline (task-runner, `crew:status`) at runtime.
- Per-project: a `crew:setup` reset wipes the project state directory, which
  removes `capabilities.json` along with it — the next setup re-creates it.

## Schema

```json
{
  "host": "<adapter name>",
  "task_tools":      true | false,
  "agent_background": true | false,
  "monitor_tool":    true | false
}
```

| Field | Type | Meaning |
|---|---|---|
| `host` | string | Adapter name that wrote the file (informational; not used for gating). |
| `task_tools` | bool | Host exposes `TaskCreate`, `TaskList`, `TaskGet`, `TaskUpdate`. Powers Layer 1 (observability mirror) AND Layer 3 (approval-signal carrier and per-stage DAG mirror via `blockedBy`). |
| `agent_background` | bool | Host can run subagent invocations in the background (Layer 2 background fan-out — `crew:run` Step 6 spawns task-runners as host background agents instead of inline parallel Agent calls). Requires the per-task `direct-edit-guard` marker. |
| `monitor_tool` | bool | Host exposes a streaming output surface (e.g. Claude Code's `TaskOutput`) over background processes (Layer 2 `crew:status` event stream — replaces `tail -20 progress.log`). |

All flags default to `false` from the consumer's point of view if the field is
missing.

## Absence Contract

> **If `capabilities.json` does not exist, every flag is treated as `false`.**

Pre-existing installations that predate Layer 1 must continue to work unchanged.
Consumers MUST therefore treat a missing file exactly like an all-false file.
This is the single rule that makes the rollout safe across hosts.

```python
import json, os

def load_capabilities(agent_crew_home: str, project_name: str) -> dict:
    path = os.path.join(agent_crew_home, "state", project_name, "capabilities.json")
    try:
        return json.load(open(path))
    except Exception:
        return {}  # treat every flag as false

caps = load_capabilities(AGENT_CREW_HOME, PROJECT_NAME)
if caps.get("task_tools"):
    ...  # use TaskCreate
else:
    ...  # legacy behavior (progress.log only)
```

## Producer Contract (host adapter)

A host adapter's `setup.sh` MUST:

1. Compute `${STATE_DIR}` as
   `${AGENT_CREW_HOME}/state/$(basename "${PROJECT_ROOT}")`.
2. `mkdir -p "${STATE_DIR}"` (idempotent).
3. Overwrite `${STATE_DIR}/capabilities.json` with the adapter's truthful flags.
   - Writing the file on every setup keeps the flags in sync with the installed
     adapter version.
   - The adapter MUST only set a flag to `true` when the host genuinely exposes
     the corresponding tool surface — never speculatively.
4. Print a `CAPABILITIES: <path>` line on stdout for operator visibility.

Adapters that do not have a richer surface (e.g., `generic`) MAY skip writing
the file entirely. The absence contract above ensures the pipeline still works.

## Consumer Contract (core pipeline)

A consumer of the capability surface (task-runner, `crew:status`, future
orchestrator code) MUST:

1. Resolve `capabilities.json` via the location above.
2. Treat any I/O or JSON parse error as "all flags false".
3. Gate every host-specific code path behind a capability check. Direct,
   ungated calls to host-specific tools (e.g., `TaskCreate`) are forbidden.
4. Continue to write the file-based source of truth (`pipeline.json`,
   `progress.log`, `result.md`, `approval.md`) regardless of any capability
   flag. The capability layer is **observability-only** at Layer 1.

## Flag Usage by Layer

| Layer | Status | Flag(s) consumed | Behavior |
|---|---|---|---|
| 1 | implemented | `task_tools` | task-runner registers via TaskCreate; `crew:status` prefers TaskList output; per-stage child tasks form a `blockedBy` DAG (P3); `TaskGet` distinguishes token-truncation tails from real crashes (P7). |
| 2 | implemented | `agent_background`, `monitor_tool` | `crew:run` Step 6 spawns task-runners as host background agents (P4); `crew:status` prefers `TaskOutput` for the event stream (P5). Per-task active markers in `direct-edit-guard` make concurrent runs safe. |
| 3 | implemented | `task_tools` | Approval signal carried over `TaskUpdate` (P1 + P6). Plan-ready: `TaskUpdate(status="blocked")` with `metadata.action_plan_path`. Approve: `TaskUpdate(status="in_progress")`. Cancel: `TaskUpdate(status="cancelled")`. `approval.md` remains the contractual artifact. |

### Absence contracts per layer

Every layer's host-tool path has a file-based fallback that ALWAYS runs:

- Layer 1 absent (`task_tools=false`): `pipeline.json` / `progress.log` are the
  primary state. `crew:status` tails the file. No DAG mirror.
- Layer 2 absent (`agent_background=false` or `monitor_tool=false`): orchestrator
  uses the inline-parallel-Agent path (`crew:run` Step 6 legacy branch);
  `crew:status` tails `progress.log` for events. The legacy singleton
  `tasks/active` marker remains the gate.
- Layer 3 absent: approval gates use the 5-second `approval.md` poll loop. The
  file write is the only signal. No `TaskUpdate`-based wakeup.

Each layer is independently opt-in — an adapter may advertise `task_tools=true`
but `agent_background=false` and still benefit from Layers 1 + 3 without
adopting background fan-out.

## Stderr Mirroring (related but capability-independent)

The task-runner also mirrors every `progress.log` append to `stderr`. This
behavior is NOT gated by `task_tools` because it is host-agnostic: Claude Code
surfaces stderr through TaskOutput automatically, and other hosts simply see it
on the terminal. Stderr mirroring is described in `core/agents/task-runner.md`.

## Related Files

- `adapters/claude/setup.sh` — producer (writes all three flags `true` for Claude Code)
- `core/agents/task-runner.md` — consumer
  - Phase 0: loads `task_tools` / `agent_background` / `monitor_tool` once
  - Phase 1c-bis: per-stage `TaskCreate` with `blockedBy` DAG (P3, Layer 1)
  - Phase 2 stage emits: `TaskUpdate(in_progress|completed|blocked)` per stage
  - Phase 2.5: `TaskUpdate(status="blocked")` carries plan-ready, `TaskGet` long-poll for approval wakeup (P1 + P6, Layer 3)
  - Stage Retry Rule: `TaskGet(taskId).status` classifies crash vs token-truncation (P7, Layer 1)
- `core/commands/run.md` — consumer
  - Step 6: background fan-out via `agent_background` (P4, Layer 2); legacy inline-Agent path preserved
  - Step 6 Task-Runner Health Check: `TaskGet`-based crash classification (P7, Layer 1)
  - Step 7.5: `TaskList`-based PLAN_READY detector (P2, Layer 1); `TaskUpdate(in_progress|cancelled)` releases waiters (P1 + P6, Layer 3)
- `core/commands/status.md` — consumer
  - Step 1b: `task_tools` selects `TaskList` for stage state; `monitor_tool` selects `TaskOutput` for event stream
  - Step 5: P5 event stream consumption via `TaskOutput`, fall back to `progress.log` tail
- `core/hooks/direct-edit-guard.sh` — consumer of marker layout (Layer 2 precondition: supports both legacy `tasks/active` and per-task `tasks/active.<TASK_ID>`)
- `core/agents/devops.md` + `core/agents/skills/deployment-ops.md` — consumer of the approval contract (Layer 3 dual-path: file primary + capability-gated wakeup)
