# Claude Invocation Guide

Use the canonical `crew:<intent>` workflow notation in prompts:

```text
crew:setup
crew:run "request"
crew:run "TaskA" | "TaskB"
crew:cost
crew:agent-maker
```

If the host exposes slash commands or alias registration, they should map back to
the same `crew:<intent>` semantics. Documentation should still prefer
`crew:<intent>`. The native shell CLI uses space-separated commands such as
`crew run` and `crew agent`; reserve those forms for CLI documentation.

## Host bridge command

Claude Code can complete native file-based handoffs through the Claude host
bridge:

```bash
export AGENT_CREW_HOST_BRIDGE_COMMAND="${HOME}/.agent-crew/adapters/claude/bin/claude-host-bridge"
```

The environment variable overrides bridge selection. When it is unset, the core
runtime can discover the installed Claude bridge from the active project's
`capabilities.json`.

The bridge runs Claude from an isolated temporary working directory and grants
explicit access to the project root and task state directory with `--add-dir`.
This prevents project-level instructions from turning a bridge validation back
into a new `crew:run` request while preserving the existing handoff artifacts.

The core runtime bounds bridge execution. Workflow handoffs use
`AGENT_CREW_BRIDGE_TIMEOUT_SECONDS=1800` by default, and direct-agent handoffs
use `AGENT_CREW_DIRECT_AGENT_BRIDGE_TIMEOUT_SECONDS=60` by default. A timeout is
recorded as `host_bridge_failure_reason=bridge_timeout` and
`failure_class=host_bridge_timeout` while preserving resumable handoff state.

Optional tuning:

```bash
export AGENT_CREW_CLAUDE_MODEL="claude-haiku-4-5"
export AGENT_CREW_CLAUDE_EFFORT="low"
export AGENT_CREW_CLAUDE_MAX_BUDGET_USD="0.25"
export AGENT_CREW_CLAUDE_TOOLS="Bash"
export AGENT_CREW_CLAUDE_ALLOWED_TOOLS="Bash"
```

## Capability mappings

`core/` markdown never names a Claude-Code-specific tool directly (Invariant 3 of
`core/rules/host-capabilities.md`). When core emits a logical capability intent,
this adapter binds it to Claude Code's native tool surface as follows:

| Intent (from core) | Claude Code tool |
|---|---|
| `ask_question(prompt, options[]) -> chosen_label \| "__cancelled__"` | `AskUserQuestion` (native structured-question tool with labeled options and an implicit cancel) |
| `createTask(name, metadata?) -> taskId` | `TaskCreate` |
| `listTasks(filter?) -> [...]` | `TaskList` |
| `getTask(taskId) -> { status, output?, metadata? }` | `TaskGet` |
| `updateTask(taskId, { status, metadata? })` | `TaskUpdate` |
| `streamOutput(taskId)` / `getOutputTail(taskId, n)` | `TaskOutput` |
| `spawnBackgroundAgent(agentName, prompt, env?)` | Claude Code's background agent surface (the same flow used by `crew:run` Step 6 P4 background fan-out) |

The capability flags written by `setup.sh` (see `core/rules/capabilities/*.md`)
determine which of these intents the core pipeline emits. Specifically:

- `task_tools=true` → the four task-lifecycle intents above are routed through
  the corresponding `Task*` tools (see `core/rules/capabilities/task-tools.md`).
- `agent_background=true` → `spawnBackgroundAgent` is routed through the
  host's background-agent surface (see
  `core/rules/capabilities/agent-background.md`).
- `monitor_tool=true` → `streamOutput` / `getOutputTail` is routed through
  `TaskOutput` (see `core/rules/capabilities/monitor-tool.md`).
- `interactive_question=true` → `ask_question` is routed through
  `AskUserQuestion` (see
  `core/rules/capabilities/interactive-question.md`).

When a flag is `false` (or `capabilities.json` is absent), core falls back to
the file-based or markdown-based path documented in the per-flag detail doc
— no Claude-Code-specific tool is invoked.

`AskUserQuestion` is the only correct destination for `ask_question` intents
on Claude Code. Do not introduce additional aliases or alternate question tools.

Note: declaring `interactive_question=true` in `adapters/claude/setup.sh`'s
`capabilities.json` output requires the `AskUserQuestion` tool to be available
in the session. Since `AskUserQuestion` is part of Claude Code's default tool
surface, this is true in every standard Claude Code session.
