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
