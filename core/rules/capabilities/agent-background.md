# agent_background Capability

## Purpose

The host can spawn subagent invocations as background processes that
outlive the orchestrator's current turn. This capability describes an
available mechanism; it does not select the user's execution policy. The
default `crew:run` remains foreground on every host. Background fan-out
requires explicit `--background`.

## Required Adapter Surface (flag=true)

Adapter MUST expose:

| Abstract call | Purpose |
|---|---|
| `spawnBackgroundAgent(agentName, prompt, env?) -> backgroundId` | Launch a subagent that runs concurrently with the orchestrator's turn-end |
| `getBackgroundAgent(backgroundId) -> {status, output?}` | Read current lifecycle state without blocking |
| `awaitBackgroundAgent(backgroundId, timeoutSeconds?) -> {status, output?}` | Wait for progress or terminal state; a timeout returns the current state rather than fabricating completion |

Normalized `status` is one of `running`, `completed`, `error`, or `cancelled`.
An adapter may expose a richer native state, but it must map that state into
this enum before core consumes it. `agent_background=true` is valid only when
spawn, get, and await are all callable; a spawn-only host must advertise
`false` because it cannot support terminal collection.

Requirements:

- The background agent's `stderr` / `stdout` MUST be capturable by the
  same host for later inspection. (The streaming surface is a separate
  capability — see `monitor-tool.md` — because a host may give one
  without the other.)
- Concurrent runs MUST be safe. Precondition: the per-task
  `direct-edit-guard` marker layout `tasks/active.<TASK_ID>` (not the
  legacy singleton `tasks/active`). The hook accepts both layouts; this
  flag requires the per-task layout.
- `getBackgroundAgent` and `awaitBackgroundAgent` MUST remain callable after
  the starting orchestrator turn ends. A terminal response without a semantic
  `result.md` is handled by the bounded retry/block contract in `run.md`; it is
  never normalized to `running`.

## Consumer Contract (core)

Concrete call sites:

- **`core/commands/run.md` Step 6 (P4 background fan-out)** — when the
  user explicitly supplies `--background`, the flag validates that P4 may
  spawn every supervisor as a background agent, regardless of `N`. If the
  flag is false, the explicit request fails closed. Without `--background`,
  supervisors use the foreground path and the orchestrator waits through
  terminal result collection even when this flag is true.

  **`TaskCreate` is NOT called by the orchestrator on the P4 path.**
  Each supervisor creates its own host task at Phase 0 startup. The
  `task_tools` (`HAS_TASK_TOOLS`) capability flag is used only by
  `crew:status` Step 7.5 to choose the polling method (TaskList-based
  vs file-based) — it does not affect the spawn path.

- **`core/hooks/direct-edit-guard.sh`** — supports both marker layouts;
  the per-task layout is the precondition when this flag is true.

Input: boolean capability flag plus an explicit execution-policy choice.
Output for an accepted background request: a list of `backgroundId` values
for the orchestrator to persist in each `session.json` task entry, monitor,
and collect asynchronously. The flag alone
never changes a foreground request into a background request.

## Absence Behavior (flag=false)

The orchestrator uses the foreground path (`crew:run` Step 6) for every
default request — both `N == 1` and `N > 1`. The legacy singleton
`tasks/active` marker remains the gate. Status tailing reads
`progress.log` directly.

An explicit `--background` request fails closed with
`background_execution_unsupported`; it is never silently downgraded to a
different lifecycle.

**Task injection is not available.** When `agent_background=false`, the
orchestrator's turn does not end until all supervisors complete. There is no
window for the user to issue a new `crew:run` command mid-run, so mid-session
task injection (`core/rules/task-injection.md`) is structurally impossible.
`run.md` Step 1.5 enforces this via the Host-Capability Guard: when
`HAS_AGENT_BACKGROUND=0`, `IS_LIVE_SESSION` is reset to `0` and the injection
path is skipped entirely.

**Affected adapters:** Codex (`agent_background=false`) and generic
(`agent_background=false`). Codex has native custom subagents in supported
CLI/app runtimes, but that surface is not equivalent to this capability unless
agent-crew can call it as `spawnBackgroundAgent(...)` and later observe the
result. Tool-backed Codex sessions may expose no callable subagent surface at
all, so the adapter must keep this flag false until the active runtime exposes
the required background contract. For Codex-specific workarounds and native
subagent guidance, see `adapters/codex/invocation.md`.

This is the documented foreground path on Codex, generic, and any host that
has not advertised `agent_background = true`. It is also the default on
Claude; Claude's true capability only makes explicit background execution
available.

## Adapter Examples

| Adapter | agent_background | How it is implemented |
|---|---|---|
| claude  | true  | Host background-agent invocation (Task tool background variant) |
| codex   | false | Native subagents may exist in Codex, but no adapter-level background contract is guaranteed; uses inline/file fallback |
| generic | false | No fan-out abstraction; inline-only |

## Related Files

Producer:

- `adapters/claude/setup.sh`

Consumer:

- `core/commands/run.md` (Step 6)
- `core/hooks/direct-edit-guard.sh` (marker layout precondition)
- `core/agents/supervisor.md` (marker write site)
- `core/rules/task-injection.md` (injection path uses the same fan-out)
