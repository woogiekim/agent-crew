# Generic AI Invocation Guide

Use the canonical `crew:<intent>` text form:

```text
crew:setup
crew:run "request"
crew:run "TaskA" | "TaskB"
crew:cost
crew:agent-maker
```

The generic adapter installs project-local `.agent-crew/` assets and `AGENTS.md`
so the assistant can follow the workflow from repository guidance.
`@crew:*` may be supported as an optional compatibility alias on hosts that allow
custom command mapping.
