# Generic AI Invocation Guide

For hosts without a native command system, use the provider-neutral
`ac:<intent>` text form:

```text
ac:setup
ac:crew "request"
ac:crew "TaskA" | "TaskB"
ac:cost
ac:agent-maker
```

The generic adapter installs project-local `.agent-crew/` assets and `AGENTS.md`
so the assistant can follow the workflow from repository guidance.
`ac:task` may still be accepted as a compatibility alias for a single-item crew run.
