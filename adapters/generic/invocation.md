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
Use plain `crew:<intent>` text as the portable form.
