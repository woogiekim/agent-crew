---
name: feature-step
description: Use when the user explicitly mentions $feature-step or asks to implement one complete feature through step-by-step approval-gated phases. This is a thin Codex wrapper for the provider-neutral feature-step workflow command.
---

# feature-step

This Codex skill delegates to the provider-neutral workflow in
`~/.agent-crew/commands/feature-step.md`.

## Execution

1. Load `~/.agent-crew/commands/feature-step.md` in full before acting.
2. Treat text after `$feature-step` as the feature request and requirement
   source hint. Treat this wrapper as the target only when the user explicitly
   names the skill, wrapper, file, or `SKILL.md` as the object.
3. Follow the command's phase gates exactly: requirements collection,
   implementation direction approval, domain logic, application services,
   adapters, and external integration.
4. Do not implement all phases in one pass. Stop at every phase report for
   retrospective notes and explicit user approval before continuing.
5. Route any destructive action through the centralized agent-crew approval
   gate.
