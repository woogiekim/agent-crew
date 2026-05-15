# agent_background Capability

## Purpose

The host can spawn subagent invocations as background processes that
outlive the orchestrator's current turn, enabling parallel task-runner
fan-out (`crew:run` Step 6). Without it, fan-out happens inline within a
single turn, which blocks the user's next input and disables mid-session
task injection.

## Required Adapter Surface (flag=true)

Adapter MUST expose:

| Abstract call | Purpose |
|---|---|
| `spawnBackgroundAgent(agentName, prompt, env?) -> backgroundId` | Launch a subagent that runs concurrently with the orchestrator's turn-end |

Requirements:

- The background agent's `stderr` / `stdout` MUST be capturable by the
  same host for later inspection. (The streaming surface is a separate
  capability — see `monitor-tool.md` — because a host may give one
  without the other.)
- Concurrent runs MUST be safe. Precondition: the per-task
  `direct-edit-guard` marker layout `tasks/active.<TASK_ID>` (not the
  legacy singleton `tasks/active`). The hook accepts both layouts; this
  flag requires the per-task layout.

## Consumer Contract (core)

Concrete call sites:

- **`core/commands/run.md` Step 6 (P4 background fan-out)** — when the
  flag is true AND `N > 1`, spawn `N` task-runners as background agents.
  When the flag is false OR `N == 1`, fall back to the inline parallel
  path (legacy branch). (Note: a future refactor phase removes the
  `N == 1` exception so that all real development tasks go background.)
- **`core/hooks/direct-edit-guard.sh`** — supports both marker layouts;
  the per-task layout is the precondition when this flag is true.

Input: boolean flag + task count. Output: a list of `backgroundId`
values for the orchestrator to poll or await asynchronously.

## Absence Behavior (flag=false)

The orchestrator uses the inline-parallel-Agent path (`crew:run` Step 6
legacy branch). The legacy singleton `tasks/active` marker remains the
gate. Status tailing reads `progress.log` directly. Task injection
(`core/rules/task-injection.md`) is effectively unavailable because the
orchestrator's turn does not end until the inline run completes.

## Adapter Examples

| Adapter | agent_background | How it is implemented |
|---|---|---|
| claude  | true  | Host background-agent invocation (Task tool background variant) |
| codex   | false | No background subagent surface; uses inline fan-out |
| generic | false | No fan-out abstraction; inline-only |

## Related Files

Producer:

- `adapters/claude/setup.sh`

Consumer:

- `core/commands/run.md` (Step 6)
- `core/hooks/direct-edit-guard.sh` (marker layout precondition)
- `core/agents/task-runner.md` (marker write site)
- `core/rules/task-injection.md` (injection path uses the same fan-out)
