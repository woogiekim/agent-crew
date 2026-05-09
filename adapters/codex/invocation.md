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
@crew:run "implement order domain API with TDD"
```

The Codex adapter installs `.codex/` agent and hook configuration plus
`AGENTS.md` guidance. Do not rely on custom slash command registration in Codex.
Prefer `crew:<intent>` in documentation. `@crew:*` should be treated as an
optional compatibility alias only when the host supports it.
