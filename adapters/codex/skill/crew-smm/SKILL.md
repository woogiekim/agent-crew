---
name: crew-smm
description: Use when the user explicitly mentions $crew-smm or asks for the agent-crew Shared Mental Model single-view (the whole per-task state — pipeline, progress, register, handoff — as one read-only block) in Codex. This is a thin Codex skill wrapper for crew:smm and delegates all behavior to ~/.agent-crew/commands/smm.md.
---

# crew-smm

This Codex skill is an alias for:

```text
crew:smm
```

## Execution

1. Load `~/.agent-crew/commands/smm.md`.
2. Follow the command definition exactly.
3. Render the Shared Mental Model single-view using the format required by that command.

Do not replace this workflow with generic repository inspection, CI status checks, or ad hoc summaries. The view is READ-ONLY — it never mutates any state file.
