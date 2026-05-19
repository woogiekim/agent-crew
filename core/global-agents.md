<!-- agent-crew-start -->
<!-- MANAGED BLOCK - DO NOT EDIT HERE.
     Edit rules via: mnemos capture --layer global --id <id> --content '...'
     Then run: crew:sync-instructions --apply
     Manual edits inside this block will be overwritten on next sync. -->
<!-- Assembled: 2026-05-19T01:31:44Z from 10 mnemos rules (host=repo) -->

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

## ROUTE Directive Rule

When `[agent-crew] ROUTE` appears anywhere in the system context
(injected by auto-route.sh), the **only permitted action** is to
invoke `crew:agent` with the specified agent and question.

- Do NOT answer the question inline.
- Do NOT run any Bash command before calling `crew:agent`.
- Do NOT read files or gather data before calling `crew:agent`.
- The ROUTE directive is authoritative. Treat it as a hard override
  of any other default behavior.
- This rule applies even if the ROUTE directive arrives mid-execution
  (in a tool result system-reminder). Stop immediately and re-route.

Violation examples (forbidden when ROUTE is present):
- Answering the question directly without calling `crew:agent`
- Running `mnemos` commands or reading files to gather context first
- Continuing an in-progress response after ROUTE appears in a tool result
- Treating the ROUTE directive as advisory rather than mandatory

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
