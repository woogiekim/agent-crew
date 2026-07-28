<!-- agent-crew-start -->
<!-- MANAGED BLOCK - DO NOT EDIT HERE.
     Edit rules via: mnemos capture --layer global --id <id> --content '...'
     Then run: crew:sync-instructions --apply
     Manual edits inside this block will be overwritten on next sync. -->
<!-- Assembled: 2026-06-26T04:48:11Z from 16 mnemos rules (host=repo) -->

# agent-crew - Global Rules

## Raw Input Preservation

Task descriptions may arrive in Korean or any other language. Preserve the
exact user text as the canonical TASK and Root Input Snapshot. Do not translate
or normalize the task to English before passing it to agents or writing it to
pipeline state.

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

## Explicit Execution Entry

> Requirements collection (Step 5 of `crew:run`) is always mandatory and must
> never be skipped, even when the request seems self-evident.

Agent Crew never infers execution intent from plain conversation. Ordinary
natural-language input must not start a workflow, task, agent, LLM router, or
hidden tool.

The user chooses the execution boundary with an explicit command such as
`crew:run`, `crew:agent`, `$crew:run`, or `$crew:agent`. Once `crew:agent` is
explicitly invoked, agent auto-routing may still select the best registered
agent, but that selection must not redirect the request to `crew:run`.

`crew:agent` may execute mutating single-agent work when the selected agent's
own definition allows mutation. Agents that remain read-only must declare that
contract in their own instructions and enforce it there.

If the user gives a short confirmation such as "go", "yes", "ok", "continue",
"proceed", "네", or "진행해주세요", continue through the appropriate
`crew:<intent>` workflow instead of answering directly.

Direct inline output is permitted for ordinary conversation unless the user has
explicitly invoked an agent-crew command or an existing command handoff is being
continued.

## Code Style Context Breaks

Frontend and backend agents must preserve code readability by inserting a line
break when the implementation context changes.

Treat transitions between setup, validation, transformation, side effects,
rendering or return values, error handling, and reporting as context changes.
Do not reformat unrelated code solely to add spacing; apply this rule to code
the agent writes or directly touches.

## Imported Command Scope Rule

Imported command/skill origin is not the work target. For example, an imported cowave command such as `$feat` provides workflow and methodology only; it does not prove that cowave is the repository, module, system, or API to modify.

Before choosing any implementation, analysis, review, git, issue, or external-mutation target, resolve scope from explicit evidence:

1. Ticket/issue title and body
2. Explicit repo, module, endpoint, API contract, or source-of-truth contract
3. Current working root
4. Notes such as "already complete", "no change", or "integration only"
5. The system whose contract must be followed for integration

Use this priority when signals conflict:

1. Explicit ticket/request scope
2. API contract or other source-of-truth contract
3. Current working root
4. Imported command/skill origin

Therefore, never infer upstream or source-project implementation work solely from the imported command/skill origin. If the ticket says a related system is already complete, needs no change, or only needs integration, keep that system closed unless newer explicit evidence reopens it. If scope remains ambiguous after checking the evidence above, stop before editing or mutating external state and ask for clarification.

## Codex Routing Fallback

Codex lifecycle hooks can require trust review and may inject only advisory
context. Therefore, the Codex adapter installs explicit `crew:<intent>` skills
as host-specific command adapters.

When running in Codex, do not infer a `crew:run` or `crew:agent` wrapper from
natural language. Use the wrapper only when the user explicitly invokes it.

If the user explicitly invoked another Codex skill, preserve that explicit
context as task input for requirements collection, supervisor handoffs, and
generated prompts. Do not auto-load non-agent-crew host/plugin skills merely
because their descriptions appear to match the task.
Non-agent-crew host/plugin skills require explicit user approval under the provider-neutral external skill boundary below.

When a Codex `crew:run` handoff returns `HOST_BRIDGE: current_session_required`,
apply the provider-neutral Current-Session Fallback rule. The Codex session is
only replacing the nested host bridge; it is not an exemption from agent,
subagent, skill, TDD, reviewer, or repair evidence requirements.

## Current-Session Fallback

When any host `crew:run` handoff returns `HOST_BRIDGE: current_session_required`
or the operator continues a host bridge handoff manually in the current host
session, that current session is only replacing the nested host bridge. It must
not bypass agent-crew dispatch. Before executing task work, re-apply specialist
agent/user-agent/subagent and agent-skill selection for the normalized task,
use/load the selected specialist when available, and record selected-axis
coverage in `{TASK_DIR}/context/specialist-dispatch.md` when available.

Before acting, load the applicable skill files and record the exact loaded skill
path(s) in `{TASK_DIR}/context/skill-load.md` or
`{TASK_DIR}/context/skill-load.json` when available. Every `selected_skill` /
`selected_skills` entry should have matching load coverage (for example,
`selected_skill: frontend-typescript-react` maps to
`frontend-typescript-react.md`, and `selected_skill: tdd` maps to `tdd.md`).
Automatically loaded skills must come from agent-crew system/user skill
locations or the active host's agent-crew mirrors. Do not auto-load unrelated
host/plugin skills by description match. If a non-agent-crew host/plugin skill
is genuinely needed, ask the user first and record approval in
`{TASK_DIR}/context/external-skill-approval.md` or `.json`. Completion/repair
for a current-session fallback reports missing or incomplete skill-load coverage
as advisory gaps and still rejects unapproved external skill loads.

Optional skill-use notes may be recorded in
`{TASK_DIR}/context/skill-use.json` or `{TASK_DIR}/context/skill-use.md`, but
they are diagnostic coverage, not required proof artifacts. TDD and other
loaded skills are covered first by real task outcomes, tests, diffs, reviews,
pipeline/progress state, reviewer quality metrics, and tool events. Phase notes
may improve auditability, but missing or incomplete notes must be reported as
advisory gaps for standard-risk work, not completion blockers.

Optional operational understanding notes may be recorded in
`{TASK_DIR}/context/skill-plan.json` or `{TASK_DIR}/context/skill-plan.md` and
linked from `rule_evidence` in `context/skill-use.json`, but these notes are
diagnostic coverage only. Completion/repair for a mutating current-session
fallback must not require separate skill-plan or rule-evidence artifacts when
the actual task outcomes, tests, diffs, reviews, or tool events are sufficient;
missing notes should be surfaced as advisory gaps.

For implementation or production-code mutation work, the same fallback must not
bypass the full TDD Red → Green → Refactor cycle. Before production-code
mutation, identify the focused test target, add or update the test, and run it;
if no runnable harness or red failure can reasonably be produced, make the
exception explicit before implementation. After green, perform the refactor
review or document a no-op refactor decision and rerun focused verification.
Completion/repair for production-code implementation may reject missing runtime
quality-loop outcomes or high-risk hard blockers, but standard-risk missing
phase-note artifacts are coverage gaps rather than proof-file requirements.

This fallback must depend on the provider-neutral command definitions under
`~/.agent-crew/commands/`. Do not embed supervisor, planner, backend, frontend,
resolver, or approval behavior in Codex-specific hooks or skills.

## STOP Directive Rule

When `[agent-crew] STOP` appears anywhere in the system context (for example
from a stale session, external host wrapper, or compatibility directive), the
first agent-crew workflow action is to invoke `crew:run`.
In Codex, this means loading the `crew:run` skill wrapper after any explicitly
invoked Codex skill has loaded, then executing the workflow intent through that
wrapper. Domain-match alone is not approval to load external host/plugin
skills.

- Do NOT produce diagnostic output or explanation before the `crew:run` wrapper
  begins the workflow.
- Do NOT run any Bash command (including exploratory or read-only commands)
  before the `crew:run` wrapper begins the workflow.
- Do NOT describe what you are about to do — enter the `crew:run` workflow.
- Do preserve explicit host skill context as requirements and handoff input.
- The STOP directive is authoritative. Treat it as a hard override of any other default behavior.

Violation examples (forbidden when STOP is present):
- Explaining why you need to enter the `crew:run` workflow
- Reading files to "understand the request first"
- Running `git status` or any other preparatory command
- Asking the user clarifying questions before the workflow's requirements step

## ROUTE Directive Rule

When `[agent-crew] ROUTE` appears anywhere in the system context
(injected by auto-route.sh), the workflow action is to invoke `crew:agent` with
the specified agent and question. In Codex, load the `crew:agent` skill wrapper
after any explicitly invoked Codex skill has loaded, then execute the workflow
intent through that wrapper. Domain-match alone is not approval to load
external host/plugin skills.

- Do NOT answer the question inline.
- Do NOT run any Bash command before the `crew:agent` wrapper begins.
- Do NOT read files or gather data before the `crew:agent` wrapper begins.
- Do preserve explicit host skill context as direct-agent input.
- The ROUTE directive is authoritative. Treat it as a hard override
  of any other default behavior.
- This rule applies even if the ROUTE directive arrives mid-execution
  (in a tool result system-reminder). Stop immediately and re-route.

Violation examples (forbidden when ROUTE is present):
- Answering the question directly without entering the `crew:agent` workflow
- Running `mnemos` commands or reading files to gather context first
- Continuing an in-progress response after ROUTE appears in a tool result
- Treating the ROUTE directive as advisory rather than mandatory

## Workflow Intents

### Explicit Command Invocation Rule

`crew:<intent>` is workflow notation used in prompts and host adapter guidance.
The native shell CLI uses space-separated commands such as `crew run` and
`crew agent`; documentation may mention those forms only when describing the
CLI control plane.

When the user's message begins with a workflow command such as `crew:run`,
`crew:setup`, `crew:status`, `crew:cost`, or `crew:agent-maker`,
treat it as an explicit command invocation, not as ordinary natural language.
Codex wrapper forms at the beginning of the message, such as `$crew:run`,
`$crew:agent`, `$crew:status`, `$crew:update`, `$crew:smm`, `$crew:setup`,
`$crew:cost`, and `$crew:agent-maker`, are the same kind of explicit command
invocation. The text after a leading `$crew:run` is the task description; only
treat `$crew:run` as the review target when the prompt explicitly names the
skill, wrapper, file, or `SKILL.md` as the object.

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
| `$crew:run` | Codex wrapper for `crew:run` |
| `$crew:agent` | Codex wrapper for `crew:agent` |
| `$crew:status` | Codex wrapper for `crew:status` |
| `$crew:update` | Codex wrapper for `crew:update` |
| `$crew:smm` | Codex wrapper for `crew:smm` |
| `$crew:setup` | Codex wrapper for `crew:setup` |
| `$crew:cost` | Codex wrapper for `crew:cost` |
| `$crew:agent-maker` | Codex wrapper for `crew:agent-maker` |

Use `crew:<intent>` as the default invocation style.

Project state is stored under:

```text
~/.agent-crew/state/{PROJECT_STATE_KEY}/tasks/{TASK_ID}
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
