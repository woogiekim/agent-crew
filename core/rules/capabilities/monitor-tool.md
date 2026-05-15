# monitor_tool Capability

## Purpose

The host exposes a streaming output surface over running background
processes (for example, Claude Code's `TaskOutput`) so `crew:status` can
show a live event stream instead of tailing `progress.log`. Decoupled
from `agent_background` because a host could expose one without the
other — for example, a host might provide file-tail streaming without
the ability to spawn background agents.

## Required Adapter Surface (flag=true)

Adapter MUST expose one of:

| Abstract call | Purpose |
|---|---|
| `streamOutput(taskId \| backgroundId) -> async iterator` | Yield stdout / stderr lines as they appear |
| `getOutputTail(taskId, n_lines) -> string` | Return the last `n_lines` of captured output |

Precondition (relied on but not strictly required): the task-runner
mirrors every `progress.log` append to `stderr` (see "Stderr Mirroring"
in `core/rules/host-capabilities.md`). This avoids file-buffering
caveats that affect raw file tailing.

## Consumer Contract (core)

Concrete call sites:

- **`core/commands/status.md` Step 1b** — selects the streaming surface
  for the event stream when the flag is true.
- **`core/commands/status.md` Step 5 (P5 event-stream consumption)** —
  prefers the streaming call for "Recent events"; falls back to
  `tail -20 progress.log` if the call is unavailable at runtime.

Input: boolean flag + task identifier. Output: text lines (string).

## Absence Behavior (flag=false)

`crew:status` uses `tail -20 progress.log` (the legacy event stream).
The file-based path is always written by the task-runner, so the
fallback is always safe; nothing breaks when this flag is false.

## Adapter Examples

| Adapter | monitor_tool | How it is implemented |
|---|---|---|
| claude  | true  | Native `TaskOutput`; `stderr` capture from `Task` background variant |
| codex   | false | No streaming surface; tails `progress.log` |
| generic | false | Tails `progress.log` |

## Related Files

Producer:

- `adapters/claude/setup.sh`

Consumer:

- `core/commands/status.md` (Step 1b, Step 5)
- `core/agents/task-runner.md` (stderr-mirror invariant — keeps the
  fallback path equivalent)
