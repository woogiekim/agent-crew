---
name: crew:evolve
description: Use when the user explicitly mentions $crew:evolve or asks to inspect, approve, or apply agent-crew self-evolution proposals in Codex. This is a thin Codex skill wrapper for crew:evolve and delegates all behavior to ~/.agent-crew/commands/evolve.md.
---

# crew:evolve

Load and follow:

```text
~/.agent-crew/commands/evolve.md
```

`crew:evolve` manages existing self-evolution proposals only. It does not
discover, aggregate, or analyze new candidates unless another explicit command
does so.
