<!-- agent-crew-start -->
<!-- MANAGED BLOCK - DO NOT EDIT HERE.
     Edit rules via: mnemos capture --layer global --id <id> --content '...'
     Then run: crew:sync-instructions --apply
     Manual edits inside this block will be overwritten on next sync. -->
<!-- Assembled: 2026-07-27T00:40:29Z from 19 mnemos rules (host=repo) -->

# agent-crew - Global Rules

## Raw Input Preservation

Preserve the user's task text as an immutable Root Input Snapshot. The system
must not translate, summarize, normalize, correct, or rewrite it before
candidate resolution, planning, handoff, or execution. Deterministic parsing may
split the explicit command and options, resolve declared aliases, and add
derived fields such as `language`, but it never replaces `rawInput`.

Agents and Tasks consume the original language directly. Translation is allowed
only when translation is the explicit Task. New executions do not create or
consume legacy normalization artifacts.

## Output Language

User-facing narrative follows the user's language and defaults to Korean on
this machine. Parser-required tokens such as `STATUS:`, `PLAN:`, `BLOCKER:`,
`REVIEW:`, enum values, commands, paths, and code identifiers remain in their
defined form. Never change the stored Root Input Snapshot to satisfy an output
language preference.

## Explicit Execution Entry

Agent Crew never infers execution intent from plain conversation. Ordinary
natural-language input must not start a Workflow, Task, or Agent. Only an
explicit logical `crew workflow`, `crew task`, or `crew agent` command may
cross the execution boundary. Host aliases map to one of those three commands.
Management commands do not start execution.

`run` is a deprecated candidate-only compatibility alias. It can present
registered Task and Workflow candidates but cannot choose or execute one.
`standalone` is a deprecated alias for `task execute`.

## Task Workflow Agent Boundaries

- A Task is one independent linear execution with no parallel branch and no
  more than one simultaneously running Agent.
- A Workflow invokes registered Tasks and includes at least one real parallel
  group of at least two Task Invocations, an explicit barrier, and a result
  policy. A Workflow cannot declare an Agent as an independent node.
- A direct Agent execution can use only the Agent and declared sequential child
  graph pinned in the approved plan. Parallel child work requires a Workflow.
- Invalid definitions are rejected; they are never silently converted or
  serialized.

## Candidate And Registry Boundaries

Candidate search is restricted to the explicitly named Registry. Zero
candidates never creates a definition. Multiple candidates, fuzzy or
LLM-recommended candidates, low metadata coverage, and resolver conflicts
require Candidate Selection. Candidate Selection is separate from Execution
Approval and must not start work.

## Hidden Routing Prohibition

No lifecycle hook, prompt preprocessor, injected directive, or host wrapper may
start a Workflow, Task, Agent, LLM router, or hidden Tool. It must not alter
input meaning, expand scope, create definitions, or persist Agent, Skill, or
Memory changes. Technical hooks are limited to deterministic dangerous-command
protection, bounded cost/tool telemetry, and cleanup.

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

## Namespaced Command Adapter

The `crew` plugin maps only explicit Codex `$crew:<intent>` and Claude Code
`/crew:<intent>` invocations to the provider-neutral definitions. It does not
infer an execution command from natural language or choose a Registry. Preserve
explicitly approved external skill context, but do not load unrelated
host/plugin skills by description match. Non-agent-crew host/plugin skills
require explicit user approval and plan pinning.

## Current-Session Fallback

When an explicit `crew workflow`, `crew task`, or `crew agent` handoff returns
`HOST_BRIDGE: current_session_required`
or the operator continues a host bridge handoff manually in the current host
session, that session replaces only the nested bridge. It must execute the
already pinned plan, original Root Input Snapshot, declared Agent/Tool graph,
permissions, and versions. It cannot re-resolve candidates, add execution
nodes, widen scope, or bypass approval.

Before acting, load the applicable skill files and record the exact loaded skill
path(s) in `{TASK_DIR}/context/skill-load.md` or
`{TASK_DIR}/context/skill-load.json` when available. Every `selected_skill` /
`selected_skills` entry should have matching load coverage (for example,
`selected_skill: frontend-typescript-react` maps to
`frontend-typescript-react.md`, and `selected_skill: tdd` maps to `tdd.md`).
Automatically loaded skills must come from agent-crew system/user skill
locations or the active host's agent-crew mirrors. In particular, do not load unrelated
host/plugin skills by description match. If a non-agent-crew host/plugin skill
is genuinely needed, ask the user first and record approval in
`{TASK_DIR}/context/external-skill-approval.md` or `.json`. Completion/repair
for a current-session fallback reports missing or incomplete skill-load coverage
as advisory gaps and still rejects unapproved external skill loads.

Optional skill-use notes may be recorded in
`{TASK_DIR}/context/skill-use.json` or `{TASK_DIR}/context/skill-use.md`, but
they are diagnostic coverage, not required completion artifacts. TDD and other
loaded skills are covered first by real task outcomes, tests, diffs, reviews,
pipeline/progress state, reviewer quality metrics, and tool events. Phase notes
such as red/green/refactor files may improve auditability, but missing or
incomplete notes must be reported as advisory gaps for standard-risk work, not
completion blockers.

Optional operational understanding notes may be recorded in
`{TASK_DIR}/context/skill-plan.json` or `{TASK_DIR}/context/skill-plan.md`, but
these notes are diagnostic coverage only. Completion or repair for a mutating
current-session fallback must not require separate skill-plan artifacts when
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

## Technical Hook Boundary

Technical lifecycle hooks may protect dangerous commands, record bounded cost
or tool metadata, and perform cleanup. They must be deterministic, bounded,
traceable, and fail in a documented way. They cannot invoke an LLM or Agent,
select a definition, modify user meaning, duplicate the full context, or create
formal verification artifacts.

## Explicit Scope Boundary

An explicit command selects exactly one logical Registry. Imported command or
skill origin does not determine the repository, module, endpoint, or contract
to change. Resolve work scope from explicit request and contract evidence, pin
it in the Execution Plan, and request a new plan before any scope expansion.

## Workflow Intents

`crew:<intent>` is provider-neutral prompt notation. Codex uses
`$crew:<intent>`, Claude Code uses `/crew:<intent>`, and the native shell CLI
uses space-separated commands such as `crew workflow`, `crew task`, and
`crew agent`.

| Logical command | Provider notation | Codex | Claude Code | Native CLI |
|---|---|---|---|---|
| Workflow | `crew:workflow` | `$crew:workflow` | `/crew:workflow` | `crew workflow` |
| Task | `crew:task` | `$crew:task` | `/crew:task` | `crew task` |
| Agent | `crew:agent` | `$crew:agent` | `/crew:agent` | `crew agent` |

The text following the explicit command is immutable `rawInput`. Read-only
`list`, `describe`, and `status` operations do not require Execution Approval.
Lifecycle `pause`, `resume`, and `cancel` operations validate owner and state.

Compatibility and management wrappers are explicit but are not additional
logical execution commands:

| Intent | Codex | Claude Code | Meaning |
|---|---|---|---|
| `crew:run` | `$crew:run` | `/crew:run` | Deprecated Task/Workflow candidate-only resolver |
| `crew:setup` | `$crew:setup` | `/crew:setup` | Install or refresh the current host adapter |
| `crew:status` | `$crew:status` | `/crew:status` | Inspect local execution state |
| `crew:update` | `$crew:update` | `/crew:update` | Explicitly refresh installed assets |
| `crew:smm` | `$crew:smm` | `/crew:smm` | Inspect the Shared Mental Model |
| `crew:cost` | `$crew:cost` | `/crew:cost` | Inspect measured cost records |
| `crew:agent-maker` | `$crew:agent-maker` | `/crew:agent-maker` | Propose an Agent definition; activation requires approval |

Project state is stored under:

```text
~/.agent-crew/state/{PROJECT_STATE_KEY}/tasks/{TASK_ID}
```

## Codex Output Language

Respond in Korean by default when the user writes Korean or when the desired response language is ambiguous.

Keep code, commands, file paths, protocol/status tokens, API names, model names, and quoted source text in their original language.

Use English only when the user explicitly requests English or an external protocol requires it.

## Korean Output Default

이 PC의 agent-crew 산출물, 작업 메모, 리뷰/검증 요약, 코드 주석, 문서 보강, 사용자-facing workflow 설명은 기본적으로 한국어로 작성한다.

사용자가 명시적으로 영어를 요청한 경우에만 영어로 작성한다.

예외: `STATUS:`, `PLAN:`, `BLOCKER:`, `REVIEW:`, 파일 경로, 명령어, 프로토콜 키워드, API 이름, 코드 식별자처럼 도구나 파서가 요구하는 구조화 토큰과 원문 보존이 필요한 literal은 기존 표기를 유지한다.

## Contents-System Scope Guard

When the active repository or task scope is contents-system / contents-systsem, never modify `apps/proxy/contents/src/main/resources/api-docs/**` or any other `api-docs` generated artifact unless the user explicitly requests API documentation changes.

For sprint-scoped contents-system tasks, Enuri-related logic is out of scope unless the user explicitly reopens Enuri scope. Do not change Enuri channel or legacy behavior merely because nearby Danawa/contents code is being edited.

## Structured Choice Rules

Use the host AI tool's structured choice UI when confirmation is required.
Do not add duplicate free-form options if the host UI already provides one.

## Approval Rule (Framework-Level)

Candidate Selection and Execution Approval are distinct decisions owned by the
Approval Service. Exact deterministic single safe Workflow/Task candidates may
skip approval only after final plan risk assessment. Multiple, fuzzy,
LLM-recommended, low-coverage, or conflicting candidates require selection.
Every direct Agent execution requires approval.

High-cost, destructive, external-write, deployment, push, merge, release,
credential, permission, broad-scope, and hard-to-reverse plans always require
approval. Approval binds definition and Agent versions, Host and installed
asset fingerprints, Root Input Snapshot, execution graph, permissions, Tools,
repository revisions, side effects, cost/risk, and canonical Plan Hash. Any
bound-field change invalidates the decision.

Use a structured host decision surface, structured markdown fallback, or a
strict PREAPPROVED manifest. Headless ambiguity fails immediately instead of
hanging or defaulting to approval.

## Risky Action Execution Rule

An Agent that encounters an unapproved destructive or external-write action
must stop and return the proposed action, scope, risk, reversibility, and
compensation needs to the Approval Service. It must not ask a duplicate
free-form question, poll an unrelated file, self-approve, or execute before the
recorded decision. A scope or graph change creates a new Execution Plan.

<!-- agent-crew-end -->


## Local And Offline Default Convention

Unless the user explicitly says otherwise, all work targets are local by
default. Apply this to coding, git, MR drafting, verification, issue workflows,
and deployment-adjacent wording.

- Do not infer remote mutation from short commands.
- Do not push, deploy, merge, create/update remote MRs, trigger remote CI, or
  mutate external systems unless explicitly requested.
- Prefer the current local repository/worktree, local generated text, local
  verification, and local clipboard operations when the user does not name a
  remote target.
- For build/test/check/verification commands, avoid remote network access by
  default. Prefer offline or cache-only modes when available, such as Gradle
  `--offline`.
- If offline/cache-only verification cannot run because required dependencies
  or artifacts are not cached, report that directly and ask before switching to
  an online/network-backed run.
- Exception: `mnemos` and `agent-crew` are allowed to perform their own required
  memory, state, hook, and instruction-management operations. Do not use this
  local/offline convention to block `mnemos` or `agent-crew` from maintaining
  their own stores or workflow state.
