---
name: crew-agent-maker
description: Use when the user explicitly mentions $crew-agent-maker or asks to design/register a custom agent for agent-crew in Codex. This is a thin Codex skill wrapper for crew:agent-maker and delegates all behavior to ~/.agent-crew/commands/agent-maker.md.
---

# crew-agent-maker

This Codex skill is an alias for:

```text
crew:agent-maker
```

## Execution

1. Load `~/.agent-crew/commands/agent-maker.md`.
2. Follow the command definition exactly.
3. Preserve the provider-neutral agent-crew boundaries defined by the command.

Do not create ad hoc agents or bypass the command definition.
