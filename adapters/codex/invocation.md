# Codex Invocation Guide

Use the canonical `crew:<intent>` text form:

```text
crew:setup
crew:run "request"
crew:run "TaskA" | "TaskB"
crew:cost
crew:agent-maker
```

Recommended prompts:

```text
crew:setup
crew:run "implement order domain API with TDD"
crew:run "Order API" | "Product API"
```

The Codex adapter installs `.codex/` agent and hook configuration plus
`AGENTS.md` guidance. Do not rely on custom slash command registration in Codex.
Use plain `crew:<intent>` text. In Codex, `@` is interpreted as mention input,
not as a custom command prefix.
