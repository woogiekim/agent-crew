---
name: crew:setup
description: Use when the user explicitly mentions $crew:setup or asks to initialize agent-crew in Codex. This is a thin Codex skill wrapper for crew:setup and delegates all behavior to ~/.agent-crew/commands/setup.md.
---

# crew:setup

This Codex skill is an alias for:

```text
crew:setup
```

## Execution

1. Load `~/.agent-crew/commands/setup.md`.
2. Follow the command definition exactly.
3. Run the host adapter setup dispatcher and initialize state as specified.

Before setup, do not inspect repository build files, package manifests, CI files, or source code unless the setup command definition explicitly asks for that.
