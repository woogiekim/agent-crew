# Generic AI Invocation Guide

Use the canonical `crew:<intent>` text form:

```text
crew:setup
crew:run "request"
crew:run "TaskA" | "TaskB"
crew:cost
crew:agent-maker
crew:agent "task description"
```

The generic adapter installs project-local `.agent-crew/` assets and `AGENTS.md`
so the assistant can follow the workflow from repository guidance.
Use plain `crew:<intent>` text as the portable form.

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
