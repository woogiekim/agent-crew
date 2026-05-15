---
name: crew-update
description: Use when the user explicitly mentions $crew-update or asks to refresh/update installed agent-crew assets in Codex. This is a thin Codex skill wrapper for crew:update and delegates all behavior to ~/.agent-crew/commands/update.md.
---

# crew-update

This Codex skill is an alias for:

```text
crew:update
```

## Execution

1. Load `~/.agent-crew/commands/update.md`.
2. Follow the command definition exactly.
3. Preserve state and run update mode as specified by the command.

Do not reset state, reinstall from scratch, or substitute generic git pull behavior for the update workflow.
