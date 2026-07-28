---
name: crew:cost
description: Use when the user explicitly mentions $crew:cost or asks for agent-crew cost information in Codex. This is a thin Codex skill wrapper for crew:cost and delegates all behavior to ~/.agent-crew/commands/cost.md.
---

# crew:cost

This Codex skill is an alias for:

```text
crew:cost
```

## Execution

1. Load `~/.agent-crew/commands/cost.md`.
2. Follow the command definition exactly.
3. Report cost information using the format required by that command.

Do not invent usage numbers or infer costs without the command's data sources.
