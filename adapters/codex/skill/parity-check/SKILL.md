---
name: parity-check
description: Use when the user explicitly mentions $parity-check or asks to verify that a contract or behavior implemented in one codebase matches an upstream, producer, or sibling codebase. This is a thin Codex wrapper for the project-agnostic cross-repository parity workflow.
---

# parity-check

This Codex skill delegates to the provider-neutral workflow in
`~/.agent-crew/commands/parity-check.md`.

## Execution

1. Load `~/.agent-crew/commands/parity-check.md` in full before acting.
2. Treat text after `$parity-check` as the contract description and repository
   scope. Treat this wrapper as the target only when the user explicitly names
   the skill, wrapper, file, or `SKILL.md` as the object.
3. Follow the command's repository resolution, mode selection, evidence, and
   `MATCH` / `MISMATCH` / `UNVERIFIABLE` reporting contract.
4. Remain read-only by default. Route any required mutation through `crew:run`
   and its centralized approval rules.
5. Never infer a concrete project or repository from this skill's origin.
