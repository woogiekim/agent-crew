---
name: crew-run
description: Use when the user explicitly mentions $crew-run or asks to run an agent-crew task workflow in Codex. This is a thin Codex skill wrapper for crew:run and delegates all behavior to ~/.agent-crew/commands/run.md.
---

# crew-run

This Codex skill is an alias for:

```text
crew:run
```

## Execution

1. Load `~/.agent-crew/commands/run.md`.
2. Treat any user text after `$crew-run` as the task description.
3. Follow the command definition exactly, including mandatory requirements collection.
4. Delegate execution to task-runner as defined by the command.

Do not implement directly, run generic verification, inspect the repository as a substitute, or duplicate task-runner logic in this skill.
