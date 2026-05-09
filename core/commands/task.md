# ac:task - Compatibility Alias

`ac:task` is a compatibility alias for `ac:crew` with exactly one task.

```text
ac:task "implement order API"
```

is equivalent to:

```text
ac:crew "implement order API"
```

## Purpose

Keep older workflows working while the orchestration engine is unified around
`ac:crew -> task-runner`.

## Required Behavior

1. Accept one task request.
2. Forward that request to the `ac:crew` workflow as a single task entry.
3. Do not maintain a separate execution engine.
4. Do not run planner or stage agents directly from `ac:task`.

## User Guidance

Prefer `ac:crew` in new documentation, prompts, and examples.
