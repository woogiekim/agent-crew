---
name: crew-agent
description: Use when the user explicitly mentions $crew-agent or when agent-crew routes a read-only question to crew:agent in Codex. This is a thin Codex skill wrapper for crew:agent and delegates all behavior to ~/.agent-crew/commands/agent.md.
---

# crew-agent

This Codex skill is an alias for:

```text
crew:agent
```

## Execution

1. Load `~/.agent-crew/commands/agent.md`.
2. Treat any user text after `$crew-agent` as the agent invocation arguments.
3. Follow the command definition exactly.

Use this skill only for read-only investigation, explanation, lookup, and
normalization tasks. If the task would mutate files, docs, issues, commits, or
state, route through `crew:run` instead.
