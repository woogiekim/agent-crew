# Claude Invocation Guide

Claude Code supports project and global slash commands. Use these invocations:

```text
/setup
/crew "TaskA" "TaskB"
/cost
/agent-maker
```

For a single task, prefer:

```text
/crew "request"
```

Provider-neutral aliases are:

```text
ac:setup
ac:crew "request"
ac:crew "TaskA" | "TaskB"
ac:cost
ac:agent-maker
```

The command names are a Claude adapter concern. Core workflow documents should
refer to workflow intents instead of requiring slash command syntax.
`/task` and `ac:task` may still be supported as compatibility aliases for a
single-item crew run.
