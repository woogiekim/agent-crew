<!-- agent-crew-start -->
<!-- MANAGED BLOCK - DO NOT EDIT HERE.
     Edit rules via: mnemos capture --layer global --id <id> --content '...'
     Then run: crew:sync-instructions --apply
     Manual edits inside this block will be overwritten on next sync. -->
<!-- Assembled: 2026-05-16T12:43:58Z from 12 mnemos rules (host=repo) -->

# agent-crew - Global Rules

## Input Language

Task descriptions may arrive in Korean. Always apply the Korean Input
Normalization rule (`core/rules/korean-input.md`) before passing TASK to
any agent or writing it to pipeline state. Never pass raw Korean text
as a TASK description to downstream agents.

## Output Language

User-facing output should appear in the user's input language (Claude
follows the conversation's language naturally; other adapters mirror
this where possible). See `core/rules/output-language.md` for the full
rule, including the **English-only status invariant**: structured
tokens like `STATUS: completed`, `REVIEW: APPROVED`, `PLAN:`,
`BLOCKER:` are parsed by regex and MUST be returned in English
regardless of input language. Narrative around those tokens (the
explanation, description, report body) follows the user's language.

The two rules are paired: input is normalized to English for
**internal artifacts** (pipeline.json, register.json, handoff.md,
agent prompts), while output narrative is **NOT forced into English**
for the user-facing surface.

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
| Backend API, domain logic, database work | `crew:run` → supervisor → backend |
| UI, full-stack, or implementation workflows | `crew:run` → supervisor → pipeline agents |
| Multiple independent features | `crew:run` with one supervisor per task |
| Requirements analysis only | `crew:run` → supervisor → planner (no implementation stages) |

## Parallel-First Execution Rule

**Default to parallel execution. Never serialize tasks to avoid merge conflicts.**

When a request contains multiple independent sub-tasks — even if they touch the
same files — run them as parallel supervisors:

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

For questions and explanations, route through `crew:agent` (auto-routing
selects analyst for codebase Q, historian for session/git/project state Q).
Direct inline response is permitted ONLY for trivial single-fact replies
(yes/no, file path lookup, single-number metric) AND when no agent in the
registry has the right scope.

## Codex Routing Fallback

Codex lifecycle hooks can require trust review and may inject only advisory
context. Therefore, the Codex adapter also installs an `agent-crew` skill as a
host-specific routing adapter.

When running in Codex, if a natural-language implementation request matches the
Auto-Execution Triggers above, treat it exactly like:

```text
crew:run "{original request}"
```

This fallback must depend on the provider-neutral command definitions under
`~/.agent-crew/commands/`. Do not embed supervisor, planner, backend, frontend,
resolver, or approval behavior in Codex-specific hooks or skills.

## STOP Directive Rule

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
`crew:setup`, `crew:status`, `crew:cost`, or `crew:agent-maker`,
treat it as an explicit command invocation, not as ordinary natural language.

For `crew:run` specifically:

- Execute the workflow defined in `~/.agent-crew/commands/run.md`.
- Do not reinterpret bare `crew:run` as "run standard verification", "run CI",
  "summarize the project", or any other host-default task.
- If no task argument is provided, follow Step 1 of the command definition and
  ask for the task description through the host structured input UI.
- If task arguments are provided, use them as the task descriptions and continue
  through requirements collection and supervisor delegation.

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
| `crew:sync-instructions` | Re-assemble host AI md files from mnemos rules |

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
orchestrator (crew:run for N > 1, supervisor for N == 1):

- Merge (git merge)
- Push to remote (git push)
- Deployment (any deploy script or command)
- Destructive operations (delete, reset, overwrite)
- Branch cleanup (git branch -d / -D)

**Stage agents (devops, and any agent that performs destructive operations) MUST NOT
issue the host's interactive question mechanism for any of the above actions
(see `core/rules/capabilities/interactive-question.md`).** Instead, those agents must:

1. Write their planned actions to `{TASK_DIR}/context/action-plan.md`
2. Return a `PLAN:` block to the supervisor with the following fields:
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

The orchestrator (crew:run or supervisor) issues the consolidated structured
user-choice intent (see `core/rules/capabilities/interactive-question.md`)
after collecting all PLAN blocks. This ensures:
- A single approval prompt regardless of how many stage agents need approval
- A consolidated view of all planned actions across all tasks (for N > 1)
- No duplicate or out-of-order approval dialogs

All structured user-choice calls (per `core/rules/capabilities/interactive-question.md`)
for these actions must include at minimum:
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
a `PLAN:` block to the supervisor. They do NOT issue the host's interactive
question mechanism directly (see `core/rules/capabilities/interactive-question.md`).
The supervisor (or crew orchestrator for parallel runs) owns the approval gate.

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

### Orchestrator-level approval (supervisor for N == 1, crew:run for N > 1)

After collecting all PLAN blocks, the orchestrator issues a single structured
user-choice intent (per `core/rules/capabilities/interactive-question.md`)
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

<!-- agent-crew-end -->
