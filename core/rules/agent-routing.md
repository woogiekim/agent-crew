# Agent Routing Rules — Declarative Abstraction

This file is the **single source of truth** for provider-neutral system agent
capability definitions and auto-routing rules. High-level commands (crew:agent,
crew:run supervisor) depend on this abstraction and must not hard-code
user-specific agent names in their dispatch logic.

## Design Note (DIP)

```
High level:   crew:agent command         (depends on abstraction only)
                    ↓
Abstraction:  core/rules/agent-routing.md  (routing rules as data — this file)
                    ↓
Low level:    individual agents            (backend, frontend, planner, …)
```

Adding a new provider-neutral system agent: add a row to the Agent Registry and,
if auto-routing should reach it, add a row to the Auto-Routing Rules table. User
and project agents are discovered dynamically from their installed layer files
for explicit-name direct invocation; they are not added to this static registry
merely because they exist locally.

---

## Agent Registry

Defines every provider-neutral system agent known to the core runtime, its
scope, discovery keywords, and whether it is safe for direct invocation via
`crew:agent`. Direct invocation does not imply read-only; read-only guarantees
must be declared in the selected agent's own instructions.

| Agent | Scope | Keywords | Safe for direct invocation | Reason if restricted |
|---|---|---|---|---|
| backend | Server-side code, APIs, DB, domain logic | api, endpoint, server, database, schema, domain, query, service, repository, entity | yes | — |
| frontend | UI components, client-side code, CSS, UX | component, page, ui, css, style, layout, button, form, modal, react, vue | yes | — |
| planner | Architecture, design, decomposition, analysis | design, plan, architecture, decompose, analyze, structure, diagram | yes | — |
| designer | Wireframes, UX specs, visual design | wireframe, mockup, visual, figma, sketch, prototype | yes | — |
| analyst | Codebase understanding, domain investigation, architecture/audit analysis, general read-only investigation | explain, investigate, understand, map, trace, explore, audit, analyze, analyse, validate, 리뷰, 검토, 평가, 검증, 동작, 작동 | yes | — |
| debugger | Read-only concrete failure diagnosis and verified root-cause reporting | bug, exception, stack trace, failing test, build failure, integration failure, flaky behavior, performance regression | yes | — |
| historian | Session / git / project state Q&A (factual lookups only) | 어떤 에이전트, 방금, what just, what did, what ran, this session, this branch, history, spawned, running, recent activity | yes | — |
| documenter | Documentation, README, API docs | docs, readme, documentation, guide, reference, changelog, comment | yes | — |
| mentor | Mentoring, coaching, concept teaching, growth feedback, engineering guidance Q&A | mentor, mentoring, coach, guide, teach, learn, explain, concept, pattern, question, example, tutorial, feedback, study plan, growth, 멘토, 코칭, 가르쳐, 학습, 개념, 설명 | yes | — |
| learning-mentor | Legacy concept-teaching alias; prefer mentor for new routing | teach, learn, explain, concept, pattern, question, example, tutorial | yes | — |
| issuer | Issue lifecycle management for creation, state transitions, and field updates (user-installed, tool-agnostic dispatcher) | publish issues, create work items, issue tracking, task list import, import issues, bulk create issues, seed project, upload task list, issue file, issue lifecycle, status transition, state change, field update, label update, priority update, assignee update | yes | — |
| reviewer | Code review (needs prior stage output) | review, lint, quality, approve, check | no | Requires completed stage output from supervisor context |
| qa-owner | QA test-case planning and implementation verification (needs PRD and stage output) | qa, test case, tc, acceptance validation, regression, exploratory, verification | no | Requires supervisor context, qa_mode, PRD, and implementation evidence |
| devops | Deploy, CI/CD, push, infrastructure | deploy, push, ci, cd, pipeline, infrastructure, release | no | Requires supervisor approval gate |
| resolver | Merge conflict resolution (needs conflict state) | conflict, merge conflict, resolve | no | Requires git conflict state established by supervisor |
| requirements | Requirements gathering (interactive multi-round) | requirements, scope, clarify, interview | no | Interactive multi-round mode only valid inside supervisor |
| supervisor | Full pipeline orchestration | (use crew:run instead) | no | Is itself the orchestrator — recursive invocation forbidden |
| supervisor-bootstrap | Supervisor bootstrap phase (internal) | (internal) | no | Internal supervisor sub-module |
| supervisor-stages | Supervisor stages phase (internal) | (internal) | no | Internal supervisor sub-module |
| supervisor-retry | Supervisor retry phase (internal) | (internal) | no | Internal supervisor sub-module |

---

## Auto-Routing Rules

Used by `crew:agent` when invoked **without** an explicit agent name. Rules are
evaluated **top-to-bottom; first match wins**.

User and project agents do not participate in auto-routing through this table
unless a separate user-owned opt-in routing overlay is explicitly implemented
and loaded by the runtime. A user agent's file presence alone is not an
auto-routing signal.

Each rule specifies: a pattern (keywords or phrases to match against the task
string, case-insensitive), a target agent (or a block directive), a confidence
level, and a reason string shown to the user in the visibility line.

| Priority | Pattern (case-insensitive, any word matches) | Agent | Confidence | Reason shown to user |
|---|---|---|---|---|
| 3 | api OR endpoint OR server OR database OR schema OR domain OR service OR repository OR entity | backend | high | Matched backend keywords |
| 4 | component OR " page" OR " ui " OR " css" OR style OR layout OR button OR form OR modal OR react OR vue | frontend | high | Matched frontend keywords |
| 5 | wireframe OR mockup OR figma OR prototype OR sketch | designer | high | Matched design/UX keywords |
| 6 | design OR architecture OR plan OR decompose OR structure OR diagram | planner | high | Matched planning/architecture keywords |
| 6.5 | "어떤 에이전트" OR 방금 OR "what just" OR "what did this session" OR "what did we" OR "what ran" OR "what agent" OR "this session" OR "이번 세션" OR "this branch" OR "session history" OR "spawned agent" OR "what's running" OR "currently running" OR "recent activity" OR "어떤 commit" OR "무슨 commit" OR "latest commit" OR "git log" OR "git history" | historian | high | Matched session/git/project-state Q pattern |
| 6.8 | bug OR exception OR "stack trace" OR "failing test" OR "build failure" OR "integration failure" OR "flaky behavior" OR "performance regression" | debugger | high | Matched concrete failure diagnosis keywords |
| 6.9 | "mentor me" OR "be my mentor" OR "멘토처럼" OR "mentor role" OR coaching OR coach OR 코칭 OR 코치 | mentor | high | Matched explicit mentor coaching keywords |
| 7 | explain OR investigate OR understand OR trace OR audit OR explore OR analyze OR analyse OR validate OR 리뷰 OR 검토 OR 평가 OR 검증 OR 동작 OR 작동 | analyst | high | Matched analyst analysis/exploration keywords |
| 8 | docs OR readme OR documentation OR guide OR reference OR changelog | documenter | high | Matched documentation keywords |
| 9 | mentor OR mentoring OR coach OR guide OR teach OR learn OR concept OR pattern OR tutorial OR example OR feedback OR study plan OR growth OR 멘토 OR 코칭 OR 가르쳐 OR 학습 OR 개념 OR 설명 | mentor | high | Matched mentoring/learning keywords |
| 9.5 | publish issues OR create work items OR issue tracking OR task list import OR import issues OR bulk create issues OR seed project OR upload task list OR issue file OR issue lifecycle OR status transition OR state change OR field update OR label update OR priority update OR assignee update | issuer | medium | Matched issue lifecycle / work-item keywords |
| 10 | (no match) | — NONE — | — | Cannot auto-route: specify an agent explicitly or use crew:run |

### Matching semantics

- Word boundaries are recommended but not enforced; whole-word matches are
  preferred to avoid false positives (e.g., "plan" in "explain" should not
  trigger planner — priority 7 fires first).
- When a task string plausibly matches multiple rules, the **highest priority**
  (lowest number) row wins.
- Rules select only the target agent. They must not block mutating requests or
  redirect to `crew:run`; that choice is made by the explicit command the user
  typed.

### Historian vs analyst — disambiguation

Both agents can be reached by question-shaped tasks. Use this rule of thumb:

- **historian** (priority 6.5): factual lookups about session, git, or
  project state. "What ran?", "what commits are on this branch?", "what
  did this session do?", "방금 어떤 에이전트?". Source: `progress.log`,
  `git log`, `~/.agent-crew/state/`. No code reasoning.
- **analyst** (priority 7): codebase understanding and code-semantic
  questions. "Explain how X works", "investigate this bug", "audit the
  caching layer". Source: source files. Reasons about code behavior.

Because historian sits at priority 6.5 (before analyst's row 7), a question
like "what agent just ran" matches historian first. A question like "explain
how this DB query works" does not match historian's keywords and falls
through to analyst's row 7. A question like "explain what just ran" matches
historian first ("what just" beats "explain") — which is the correct outcome
because the user is asking about session state, not code semantics.

---

## Explicit command boundary

`core/hooks/auto-route.sh` must not classify ordinary natural-language input as
read-only or mutating, and must not choose `crew:agent` vs `crew:run`.

The hook adapts only explicit command syntax such as `$crew:run`, `$crew:agent`,
`crew:run`, and `crew:agent`. Any ordinary natural-language prompt passes
through without a STOP/ROUTE directive. Once the user explicitly invokes
`crew:agent`, this file may still auto-select the best agent from the table
above.

---

## How orchestrators must use this file

1. **Agent name validation** — look up provider-neutral system agents in the
   Agent Registry and look up user/project agents through the installed agent
   layer discovery paths. If neither source has a candidate: error "unknown
   agent". If the static registry marks the name as `Safe for direct invocation
   = no`: error with the `Reason if restricted` text.

2. **Auto-routing** — apply Auto-Routing Rules top-to-bottom against the
   normalized task string. Return the matched agent or none result. Auto-routing
   chooses the agent only; it must not choose the command.

3. **Visibility** — always emit the `[crew:agent] →` line before spawning,
   including the agent name, confidence (if auto-routed), and reason text.

4. **No hard-coding** — orchestrators must read provider-neutral system agent
   names from this file and user/project agent names from layer discovery.
   Embedding user-specific agent names in command logic is a DIP violation.
