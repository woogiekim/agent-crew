# Host Capabilities Contract

## Purpose

Some host adapters (notably Claude Code) expose richer task-tracking surfaces
than the file-based progress.log + pipeline.json model the core pipeline depends
on. To stay provider-neutral, the core pipeline depends on a small capability
contract instead of any specific host API. Host adapters declare their
capabilities at setup time; the core pipeline reads them and opts into the
richer surfaces only when the capability is advertised.

This file is part of the progressive-adoption plan documented in the task
description "Layer 1 progressive adoption of Claude Code's TaskCreate". This
document covers **Layer 1 only** — capability detection. Layers 2 (background
fan-out via TaskCreate) and 3 (approval signaling via TaskUpdate) reuse the
same flags but are not implemented yet.

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
| `task_tools` | bool | Host exposes `TaskCreate`, `TaskList`, `TaskGet`, `TaskUpdate`. |
| `agent_background` | bool | Host can run subagent invocations in the background (reserved for Layer 2). |
| `monitor_tool` | bool | Host exposes a streaming `Monitor` tool over background processes (reserved for Layer 2/3 progress streaming). |

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
| 1 | implemented | `task_tools` | task-runner registers via TaskCreate; `crew:status` prefers TaskList output |
| 2 | reserved | `agent_background`, `monitor_tool` | background subagent fan-out (not in this release) |
| 3 | reserved | `task_tools` | approval signal carried over `TaskUpdate` (not in this release) |

## Stderr Mirroring (related but capability-independent)

The task-runner also mirrors every `progress.log` append to `stderr`. This
behavior is NOT gated by `task_tools` because it is host-agnostic: Claude Code
surfaces stderr through TaskOutput automatically, and other hosts simply see it
on the terminal. Stderr mirroring is described in `core/agents/task-runner.md`.

## Related Files

- `adapters/claude/setup.sh` — producer (writes the file)
- `core/agents/task-runner.md` — consumer (gates TaskCreate, mirrors stderr)
- `core/commands/status.md` — consumer (prefers TaskList when flag is set)
