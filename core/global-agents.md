# agent-crew - Global Rules

## Input Language

Task descriptions may arrive in Korean. Always apply the Korean Input
Normalization rule (`core/rules/korean-input.md`) before passing TASK to
any agent or writing it to pipeline state. Never pass raw Korean text
as a TASK description to downstream agents.

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
| Backend API, domain logic, database work | `crew:run` → task-runner → backend |
| UI, full-stack, or implementation workflows | `crew:run` → task-runner → pipeline agents |
| Multiple independent features | `crew:run` with one task-runner per task |
| Requirements analysis only | `crew:run` → task-runner → planner (no implementation stages) |

## Parallel-First Execution Rule

**Default to parallel execution. Never serialize tasks to avoid merge conflicts.**

When a request contains multiple independent sub-tasks — even if they touch the
same files — run them as parallel task-runners:

```
crew:run "Sub-task A" | "Sub-task B" | "Sub-task C"
```

Merge conflicts that arise after parallel completion are resolved by the
**resolver agent**. That is its explicit purpose. Choosing sequential execution
to avoid conflicts is an incorrect optimization that sacrifices throughput for a
problem the resolver already solves.

**Sequential execution is only correct when:**
- Task B cannot start until Task A's output exists (true dependency)
- The tasks are logically a single atomic unit

File overlap alone is never a reason to serialize.

## Auto-Execution Triggers

> Requirements collection (Step 5 of `crew:run`) is always mandatory and must
> never be skipped, even when the request seems self-evident.

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

### Explicit Command Invocation Rule

When the user's message begins with a workflow command such as `crew:run`,
`crew:setup`, `crew:status`, `crew:cost`, `crew:agent-maker`, or the portable
aliases `ac:crew`, `ac:task`, `ac:setup`, `ac:cost`, and `ac:agent-maker`,
treat it as an explicit command invocation, not as ordinary natural language.

For `crew:run` specifically:

- Execute the workflow defined in `~/.agent-crew/commands/run.md`.
- Do not reinterpret bare `crew:run` as "run standard verification", "run CI",
  "summarize the project", or any other host-default task.
- If no task argument is provided, follow Step 1 of the command definition and
  ask for the task description through the host structured input UI.
- If task arguments are provided, use them as the task descriptions and continue
  through requirements collection and task-runner delegation.

For `crew:setup` specifically:

- Execute the workflow defined in `~/.agent-crew/commands/setup.md`.
- Do not reinterpret it as a request to inspect the repository, inspect Gradle or
  package files, run verification, or infer project setup manually.
- Run the host adapter setup flow and initialize agent-crew state exactly as the
  command definition says.

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

## Approval Rule (Framework-Level)

### Centralized Approval Gate

All approval decisions for the following actions are owned exclusively by the
orchestrator (crew:run for N > 1, task-runner for N == 1):

- Merge (git merge)
- Push to remote (git push)
- Deployment (any deploy script or command)
- Destructive operations (delete, reset, overwrite)
- Branch cleanup (git branch -d / -D)

**Stage agents (devops, and any agent that performs destructive operations) MUST NOT
issue AskUserQuestion for any of the above actions.** Instead, those agents must:

1. Write their planned actions to `{TASK_DIR}/context/action-plan.md`
2. Return a `PLAN:` block to the task-runner with the following fields:
   ```text
   PLAN:
     actions: {list of planned commands}
     risk: {none | low | medium | high}
     reversible: {yes | no}
   STATUS: plan_ready
   ```
3. Poll `{TASK_DIR}/context/approval.md` for `APPROVED` or `CANCELLED`
   (up to 60s timeout before reporting BLOCKED)
4. Execute only after receiving `APPROVED`; halt with STATUS: BLOCKED on
   `CANCELLED` or timeout

### Orchestrator Approval Gate

The orchestrator (crew:run or task-runner) issues the consolidated AskUserQuestion
after collecting all PLAN blocks. This ensures:
- A single approval prompt regardless of how many stage agents need approval
- A consolidated view of all planned actions across all tasks (for N > 1)
- No duplicate or out-of-order approval dialogs

All AskUserQuestion calls for these actions must include at minimum:
- header: action type (e.g., "Deploy", "Approve All Actions", "Merge", "Push", "Rollback")
- question: describing the specific action(s) with relevant details
- options: at minimum "Approve — proceed" and "Cancel — hold"

Plain-text approval requests ("Shall I?", "Should I?", "Do you want me to?")
are FORBIDDEN at every level of the system. Violating this rule is a workflow
consistency error.

## Subagent Plan Approval Rule

Stage agents that perform **destructive operations** (deploy, push, merge, overwrite,
or branch cleanup) must present a PLAN block for approval before executing. The planner,
backend, frontend, and designer agents are exempt — they commit code and return STATUS
directly without a PLAN gate.

**How plans flow depends on the agent type:**

### Destructive-action stage agents (devops, and any agent that deploys or pushes)

These agents write their plan to `{TASK_DIR}/context/action-plan.md` and return
a `PLAN:` block to the task-runner. They do NOT issue AskUserQuestion directly.
The task-runner (or crew orchestrator for parallel runs) owns the approval gate.

PLAN block format:
```text
PLAN:
  actions:
    - {action 1}
    - {action 2}
  risk: {none | low | medium | high}
  reversible: {yes | no}
STATUS: plan_ready
```

### Orchestrator-level approval (task-runner for N == 1, crew:run for N > 1)

After collecting all PLAN blocks, the orchestrator issues a single AskUserQuestion
with a consolidated summary of all planned actions.

Standard approval options:

```text
[A] Approve - proceed as planned
[B] Request changes - revise the plan and ask again
[C] Cancel - stop implementation
[D] Custom input
```

Standard plan summary (presented by orchestrator, not stage agents):

```text
[agent-name] Work Plan

Target: {feature name}
Approach: {pattern or methodology summary}
Files:
  - {file path 1} (new or modified)
  - {file path 2} (new or modified)
Planned Actions:
  - {action 1}
  - {action 2}
Risk: {none | low | medium | high}

Proceed with this plan?
```
