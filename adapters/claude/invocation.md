# Claude Invocation Guide

Use the canonical `crew:<intent>` text form:

```text
crew:setup
crew:run "request"
crew:run "TaskA" | "TaskB"
crew:cost
crew:agent-maker
```

If the host exposes slash commands or alias registration, they should map back to
the same `crew:<intent>` semantics. Documentation should still prefer
`crew:<intent>`.
