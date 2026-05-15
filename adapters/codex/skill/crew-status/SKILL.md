---
name: crew-status
description: Use when the user explicitly mentions $crew-status or asks for agent-crew status in Codex. This is a thin Codex skill wrapper for crew:status and delegates all behavior to ~/.agent-crew/commands/status.md.
---

# crew-status

This Codex skill is an alias for:

```text
crew:status
```

## Execution

1. Load `~/.agent-crew/commands/status.md`.
2. Follow the command definition exactly.
3. Report status using the format required by that command.

Do not replace this workflow with generic repository inspection, CI status checks, or ad hoc summaries.
