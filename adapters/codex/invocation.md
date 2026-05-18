# Codex Invocation Guide

Use the canonical `crew:<intent>` text form:

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
Use plain `crew:<intent>` text. In Codex, `@` is interpreted as mention input,
not as a custom command prefix.

## crew:agent — Direct Agent Invocation

For tasks that don't need the full crew:run pipeline overhead, invoke an agent
directly:

```text
crew:agent "task description"        # auto-routing: crew picks the best agent
crew:agent backend "task"            # explicit: invoke the backend agent directly
crew:agent --list                    # list agents available for direct invocation
crew:agent --routing                 # display the auto-routing rules table
```

The routing logic is defined in `core/rules/agent-routing.md`. Auto-routing
matches your task against keyword patterns and shows which agent was selected
and why before spawning. The selected agent runs without a supervisor pipeline —
no worktree, no `pipeline.json`, no multi-stage review.

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
