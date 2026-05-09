# Codex Invocation Guide

Codex does not currently expose project-defined slash commands as user commands.
Use the provider-neutral `ac:<intent>` text form instead:

```text
ac:setup
ac:crew "request"
ac:crew "TaskA" | "TaskB"
ac:cost
ac:agent-maker
```

Recommended prompts:

```text
ac:setup
ac:crew "implement order domain API with TDD"
ac:crew "Order API" | "Product API"
```

The Codex adapter installs `.codex/` agent and hook configuration plus
`AGENTS.md` guidance. Do not rely on custom slash command registration in Codex.
`ac:task` may still be accepted as a compatibility alias for a single-item crew run.
