# Claude Invocation Guide

Use the canonical `crew:<intent>` text form:

```text
crew:setup
crew:run "request"
crew:run "TaskA" | "TaskB"
crew:cost
crew:agent-maker
```

Compatible alias form:

```text
@crew:run "request"
@crew:setup
@crew:cost
```

If the host exposes slash commands or alias registration, they should map back to
the same `crew:<intent>` semantics. Documentation should still prefer
`crew:<intent>`.
