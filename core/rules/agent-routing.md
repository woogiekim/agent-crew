# Agent Routing Rules — Declarative Abstraction

This file is the **single source of truth** for agent capability definitions
and auto-routing rules. High-level commands (crew:agent, crew:run supervisor)
depend on this abstraction and must not hard-code agent names in their dispatch
logic.

## Design Note (DIP)

```
High level:   crew:agent command         (depends on abstraction only)
                    ↓
Abstraction:  core/rules/agent-routing.md  (routing rules as data — this file)
                    ↓
Low level:    individual agents            (backend, frontend, planner, …)
```

Adding a new agent: add a row to the Agent Registry and, if auto-routing
should reach it, add a row to the Auto-Routing Rules table. No changes to
crew:agent or any orchestrator are required.

---

## Agent Registry

Defines every agent known to the system, its scope, discovery keywords, and
whether it is safe for direct invocation via `crew:agent`.

| Agent | Scope | Keywords | Safe for direct invocation | Reason if restricted |
|---|---|---|---|---|
| backend | Server-side code, APIs, DB, domain logic | api, endpoint, server, database, schema, domain, query, service, repository, entity | yes | — |
| frontend | UI components, client-side code, CSS, UX | component, page, ui, css, style, layout, button, form, modal, react, vue | yes | — |
| planner | Architecture, design, decomposition, analysis | design, plan, architecture, decompose, analyze, structure, diagram | yes | — |
| designer | Wireframes, UX specs, visual design | wireframe, mockup, visual, figma, sketch, prototype | yes | — |
| analyst | Codebase understanding, domain investigation | explain, investigate, understand, map, trace, explore, audit | yes | — |
| historian | Session / git / project state Q&A (factual lookups only) | 어떤 에이전트, 방금, what just, what did, what ran, this session, this branch, history, spawned, running, recent activity | yes | — |
| documenter | Documentation, README, API docs | docs, readme, documentation, guide, reference, changelog, comment | yes | — |
| learning-mentor | Concept explanation, teaching, Q&A | teach, learn, explain, concept, pattern, question, example, tutorial | yes | — |
| korean-normalizer | Korean text normalization (utility) | (internal — invoked automatically for Korean input) | yes | — |
| reviewer | Code review (needs prior stage output) | review, lint, quality, approve, check | no | Requires completed stage output from supervisor context |
| devops | Deploy, CI/CD, push, infrastructure | deploy, push, ci, cd, pipeline, infrastructure, release | no | Requires supervisor approval gate |
| resolver | Merge conflict resolution (needs conflict state) | conflict, merge conflict, resolve | no | Requires git conflict state established by supervisor |
| requirements | Requirements gathering (interactive multi-round) | requirements, scope, clarify, interview | no | Interactive multi-round mode only valid inside supervisor |
| supervisor | Full pipeline orchestration | (use crew:run instead) | no | Is itself the orchestrator — recursive invocation forbidden |
| supervisor-bootstrap | Supervisor bootstrap phase (internal) | (internal) | no | Internal supervisor sub-module |
| supervisor-stages | Supervisor stages phase (internal) | (internal) | no | Internal supervisor sub-module |
| supervisor-retry | Supervisor retry phase (internal) | (internal) | no | Internal supervisor sub-module |

---

## Auto-Routing Rules

Used by `crew:agent` when invoked **without** an explicit agent name.
Rules are evaluated **top-to-bottom; first match wins**.

Each rule specifies: a pattern (keywords or phrases to match against the task
string, case-insensitive), a target agent (or a block directive), a confidence
level, and a reason string shown to the user in the visibility line.

| Priority | Pattern (case-insensitive, any word matches) | Agent | Confidence | Reason shown to user |
|---|---|---|---|---|
| 1 | deploy OR "push to" OR "ci/cd" OR "cd pipeline" OR "release pipeline" | — BLOCK — | — | Restricted: devops requires supervisor approval gate — use crew:run |
| 2 | " review" OR "lint " OR " approve" OR "code review" OR "quality check" | — BLOCK — | — | Restricted: reviewer requires prior stage output — use crew:run |
| 3 | api OR endpoint OR server OR database OR schema OR domain OR service OR repository OR entity | backend | high | Matched backend keywords |
| 4 | component OR " page" OR " ui " OR " css" OR style OR layout OR button OR form OR modal OR react OR vue | frontend | high | Matched frontend keywords |
| 5 | wireframe OR mockup OR figma OR prototype OR sketch | designer | high | Matched design/UX keywords |
| 6 | design OR architecture OR plan OR decompose OR structure OR diagram | planner | high | Matched planning/architecture keywords |
| 6.5 | "어떤 에이전트" OR 방금 OR "what just" OR "what did this session" OR "what did we" OR "what ran" OR "what agent" OR "this session" OR "이번 세션" OR "this branch" OR "session history" OR "spawned agent" OR "what's running" OR "currently running" OR "recent activity" OR "어떤 commit" OR "무슨 commit" | historian | high | Matched session/git/project-state Q pattern |
| 7 | explain OR investigate OR understand OR trace OR audit OR explore | analyst | high | Matched analysis/exploration keywords |
| 8 | docs OR readme OR documentation OR guide OR reference OR changelog | documenter | high | Matched documentation keywords |
| 9 | teach OR learn OR concept OR pattern OR tutorial OR example | learning-mentor | high | Matched learning/mentorship keywords |
| 10 | (no match) | — NONE — | — | Cannot auto-route: specify an agent explicitly or use crew:run |

### Matching semantics

- Word boundaries are recommended but not enforced; whole-word matches are
  preferred to avoid false positives (e.g., "plan" in "explain" should not
  trigger planner — priority 7 fires first).
- When a task string plausibly matches multiple rules, the **highest priority**
  (lowest number) row wins.
- Restricted rules (priority 1–2) are checked before any agent-assignment
  rules to prevent unsafe direct invocations.

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

## How orchestrators must use this file

1. **Agent name validation** — look up the agent name in the Agent Registry.
   If not found: error "unknown agent". If found but `Safe for direct
   invocation = no`: error with the `Reason if restricted` text.

2. **Auto-routing** — apply Auto-Routing Rules top-to-bottom against the
   normalized task string. Return the matched agent (or block/none result).

3. **Visibility** — always emit the `[crew:agent] →` line before spawning,
   including the agent name, confidence (if auto-routed), and reason text.

4. **No hard-coding** — orchestrators must read agent names exclusively from
   this file. Embedding agent names in command logic is a DIP violation.
