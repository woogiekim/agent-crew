# agent-crew - Global Rules

## No Direct Implementation

When a user requests coding, implementation, or development work, do not start
editing files or generating production code directly.

Always follow this sequence:

1. Classify the request.
2. Invoke the appropriate agent, skill, or workflow intent.
3. Perform implementation only after the required planning or delegated agent step.

This is a system behavior principle. It is not tied to a specific AI vendor.
Host adapters may expose different invocation methods, but the workflow intent
remains provider-neutral.

## Agent Routing Criteria

| Request Type | Execution Method |
|---|---|
| Backend API, domain logic, database work | Delegate to `backend` |
| UI, full-stack, or implementation workflows | `crew:run` -> task-runner -> pipeline agents |
| Multiple independent features | `crew:run` with one task-runner per task |
| Requirements analysis only | Delegate to `planner` |

## Auto-Execution Triggers

Spawn an agent or workflow when the user asks to build, implement, create, add,
update, fix, remove, move, change, migrate, refactor, replace, extend, or
integrate development work.

If the user gives a short confirmation such as "go", "yes", "ok", "continue",
or "proceed" and the prior context is about implementation work, continue
through the appropriate `crew:<intent>` workflow instead of answering directly.

Respond directly only for questions or explanations, such as "how", "why",
"what", "explain", or "describe", unless the user also asks for implementation.

### STOP Directive Rule

When `[agent-crew] STOP` appears anywhere in the system context (injected by
auto-route.sh), the **only permitted first action** is to invoke `crew:run`.

- Do NOT produce any diagnostic output or explanation before calling `crew:run`.
- Do NOT run any Bash command (including exploratory or read-only commands) before calling `crew:run`.
- Do NOT describe what you are about to do — call `crew:run` immediately.
- The STOP directive is authoritative. Treat it as a hard override of any other default behavior.

Violation examples (forbidden when STOP is present):
- Explaining why you need to call `crew:run`
- Reading files to "understand the request first"
- Running `git status` or any other preparatory command
- Asking the user clarifying questions before invoking `crew:run`

## Workflow Intents

| Intent | Meaning |
|---|---|
| `crew:setup` | Install the current host adapter and initialize the project workspace |
| `crew:run` | Canonical workflow entry point for one or more tasks |
| `crew:cost` | Show the session cost summary |
| `crew:agent-maker` | Design and register a custom agent |

Use `crew:<intent>` as the default invocation style.

Project state is stored under:

```text
~/.agent-crew/state/{PROJECT_NAME}/tasks/{TASK_ID}
```

## Structured Choice Rules

Use the host AI tool's structured choice UI when confirmation is required.
Do not add duplicate free-form options if the host UI already provides one.

## Subagent Plan Approval Rule

Before implementation, every implementation-capable subagent must present a plan
and request approval through the host AI tool's structured choice UI. The planner
is exempt because planning is its primary role.

The plan must include:

1. What will be implemented and why.
2. The approach or methodology.
3. Files expected to be created or modified.
4. Estimated implementation steps or TDD cycles.

Standard approval options:

```text
[A] Approve - proceed as planned
[B] Request changes - revise the plan and ask again
[C] Cancel - stop implementation
[D] Custom input
```

Standard plan summary:

```text
[agent-name] Work Plan

Target: {feature name}
Approach: {pattern or methodology summary}
Files:
  - {file path 1} (new or modified)
  - {file path 2} (new or modified)
Estimated steps: {number of steps or TDD cycles}

Proceed with this plan?
```
