# Codex Invocation Guide

Use the canonical `crew:<intent>` workflow notation in Codex prompts:

```text
crew:setup
crew:run "request"
crew:run "TaskA" | "TaskB"
crew:cost
crew:agent-maker
crew:agent "task description"
```

Recommended prompts:

```text
crew:setup
crew:run "implement order domain API with TDD"
crew:run "Order API" | "Product API"
```

The Codex adapter installs `.codex/` agent and hook configuration plus
`AGENTS.md` guidance. Do not rely on custom slash command registration in Codex.
Slash-style commands are host-specific aliases, and this adapter does not create
adapter-owned slash aliases. Use plain `crew:<intent>` text. In Codex, `@` is
interpreted as mention input, not as a custom command prefix. The native shell
CLI uses space-separated commands such as `crew run` and `crew agent`; those are
CLI forms, not the prompt workflow notation.

## crew:agent — Direct Agent Invocation

Use `crew:agent` only for read-only investigation, explanation, lookup, and
normalization tasks. Any task that would edit files, write docs, create issues,
commit code, or otherwise mutate state must use `crew:run`.

```text
crew:agent "task description"        # auto-routing: crew picks the best agent
crew:agent analyst "task"            # explicit: invoke a read-only analysis agent
crew:agent --list                    # list agents available for direct invocation
crew:agent --routing                 # display the auto-routing rules table
```

The routing logic is defined in `core/rules/agent-routing.md`. Auto-routing
matches your task against keyword patterns and shows which agent was selected
and why before spawning. The selected agent runs without a supervisor pipeline,
so the command is intentionally limited to read-only tasks.

## Native Codex Subagents

Codex supports native custom subagents through TOML files in:

- `.codex/agents/*.toml` for project-scoped agents
- `~/.codex/agents/*.toml` for user-scoped agents

Each agent file must define `name`, `description`, and
`developer_instructions`. The `name` field is the runtime identity Codex uses
when spawning the agent; matching the filename is only a convention. The Codex
setup flow writes regular copied TOML files, not symlinks, because some Codex
versions have not discovered symlinked custom-agent TOMLs reliably.

The project template also installs `.codex/config.toml` with:

```toml
[agents]
max_threads = 6
max_depth = 1
```

Keep `max_depth = 1` unless recursive delegation is explicitly required.
Deeper nesting can multiply token usage, latency, and local resource
consumption. Use `max_threads` as the concurrency cap for open agent threads.

### Parallel usage pattern on Codex

For user-facing workflows, keep using `crew:run`:

```text
crew:run "Task A" | "Task B" | "Task C"
```

Inside Codex, this should be expressed as native subagent fan-out when the
runtime exposes the subagent surface:

- spawn one `supervisor` subagent per top-level task
- for a `parallelizable_units` stage, spawn one worker subagent per unit
- keep every unit scoped to its `UNIT_FILES` and isolated worktree
- wait for all spawned agents before fan-in, review, and resolver handling

Prefer narrow, role-specific agents for read-only exploration, review, docs
research, debugging, and targeted fixes. Avoid giving multiple write-capable
agents the same files unless the supervisor has created isolated worktrees and
the resolver/fan-in path is active.

### Capability boundary

Codex native subagents are not the same as agent-crew's
`agent_background=true` contract. The `agent_background` flag means the
orchestrator can launch background supervisors that outlive the current turn and
can be monitored later. In tool-backed Codex sessions where no callable
subagent surface is exposed to agent-crew, the adapter must keep
`agent_background=false` and use the file-based fallback.

## Interactive Question Mapping

Codex has a conditional mapping for agent-crew's provider-neutral
`askQuestion(prompt, options[])` intent.

When the current Codex session is in Plan mode and exposes the
`request_user_input` tool, that tool is the adapter binding for structured
questions. The Codex prompt runtime must:

1. Compute a stable question id with `crew question key`.
2. Resolve any cached decision with `crew question resolve`.
3. If no decision exists, call `request_user_input` with the prompt and labeled
   options.
4. Persist the selected label with `crew question record` using
   `source=codex_plan_mode` and `adapter=codex`.
5. Continue with that selected label. User refusal or explicit cancellation maps
   to `__cancelled__`.

When `request_user_input` is not available, Codex uses the structured markdown
fallback described in `core/rules/capabilities/interactive-question.md`.

Because the native surface is session-mode dependent, `capabilities.json` keeps
`interactive_question=false` and records the conditional surface separately:

```json
{
  "interactive_question_mode": "codex_plan_mode_conditional",
  "interactive_question_surface": "request_user_input",
  "interactive_question_fallback": "structured_markdown"
}
```

## Host Bridge Command

The Codex adapter includes an executable bridge command for native CLI handoffs:

```bash
export AGENT_CREW_HOST_BRIDGE_COMMAND="${HOME}/.agent-crew/adapters/codex/bin/codex-host-bridge"
```

When `crew run` or `crew agent` creates a handoff, the core runtime uses this
variable when it is set. If it is unset, the runtime can discover the installed
Codex bridge from the active project's `capabilities.json`. The bridge receives
the provider-neutral handoff coordinates:

- `AGENT_CREW_TASK_ID`
- `AGENT_CREW_TASK_DIR`
- `AGENT_CREW_HANDOFF_PATH`
- `AGENT_CREW_RESULT_PATH`
- `AGENT_CREW_PROJECT_ROOT`

For direct-agent handoffs, the runtime also passes:

- `AGENT_CREW_AGENT_NAME`
- `AGENT_CREW_AGENT_REQUEST_ID`
- `AGENT_CREW_REQUEST_DIR`

The bridge runs `codex exec` in the project root and prompts Codex to resume the
existing handoff. It does not create a new `crew:run`, and it does not change
STOP / ROUTE / `crew:run` / `crew:agent` semantics. If `codex` is unavailable or
the command fails, the core runtime leaves the existing resumable handoff state
intact for `crew resume` or manual repair.

Use `AGENT_CREW_CODEX_BIN=/path/to/codex` when the `codex` executable is not on
`PATH`.

When the bridge is invoked from an already-active Codex session, it fails fast
instead of launching a nested `codex exec` process. Nested Codex sessions do not
provide reliable completion signals in this adapter path, so the runtime keeps
the existing handoff/request state resumable and tells the operator to continue
from the current host session. Set `AGENT_CREW_CODEX_ALLOW_NESTED=1` only for
explicit debugging or test fixtures.

The core runtime bounds bridge execution. Workflow handoffs use
`AGENT_CREW_BRIDGE_TIMEOUT_SECONDS=1800` by default, and direct-agent handoffs
use `AGENT_CREW_DIRECT_AGENT_BRIDGE_TIMEOUT_SECONDS=60` by default. When a
bridge times out, the runtime records `host_bridge_failure_reason=bridge_timeout`
and `failure_class=host_bridge_timeout`, then leaves the handoff/request
resumable. Set either timeout to `0` only for deliberate unbounded debugging.

## Limitations

### Task injection is not available in Codex

Task injection (`crew:run --inject`) — submitting new tasks into an already-running
parallel session — is **not supported** in Codex.

**Why it cannot work:** Codex sets `HAS_AGENT_BACKGROUND=0` in `capabilities.json`,
meaning the orchestrator runs inline and its turn does not end until all supervisors
have completed. Because the orchestrator's turn never ends mid-run, there is no
window for the user to issue a new `crew:run` command while tasks are executing.
The `session.json` injection detection logic (`run.md` Step 1.5) runs but is
effectively inert on the Codex path — `IS_LIVE_SESSION` is treated as `0` because
no new input can arrive during the execution window.

**Workaround — queue all tasks upfront:**

Instead of injecting tasks mid-run, specify all tasks before starting execution
using the pipe syntax:

```text
crew:run "Task A" | "Task B" | "Task C"
```

All tasks are queued, planned, and executed as a batch. This is the recommended
pattern for multi-task workflows in Codex.

**References:**
- `core/rules/task-injection.md` — full injection protocol and host-capability guard
- `core/rules/capabilities/agent-background.md` — `agent_background` flag and absence behavior
