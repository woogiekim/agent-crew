---
name: parity-implement
description: Use only when the user explicitly invokes $parity-implement. Loads the user-owned parity implementation planning command.
---

# parity-implement

This Codex skill delegates to the user command in
`~/.agent-crew/commands/parity-implement.md`.

## Execution

1. Preserve all text after `$parity-implement` as immutable raw input.
2. Load `~/.agent-crew/commands/parity-implement.md` in full before acting.
3. Follow the command's evidence gate and implementation-unit planning contract.
4. Do not execute a Task, Workflow, code edit, or external mutation from this wrapper.
5. Never infer a concrete project or repository from this skill's origin.
