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
| mentor | Mentoring, coaching, concept teaching, growth feedback, engineering guidance Q&A | mentor, mentoring, coach, guide, teach, learn, explain, concept, pattern, question, example, tutorial, feedback, study plan, growth, 멘토, 코칭, 가르쳐, 학습, 개념, 설명 | yes | — |
| learning-mentor | Legacy concept-teaching alias; prefer mentor for new routing | teach, learn, explain, concept, pattern, question, example, tutorial | yes | — |
| input-normalizer | Multilingual input translation and instruction normalization (utility) | (internal — invoked automatically for multilingual or ambiguous input) | yes | — |
| korean-normalizer | Korean text normalization compatibility alias (utility) | (legacy internal alias; prefer input-normalizer) | yes | — |
| issuer | Issue lifecycle management for creation, state transitions, and field updates (user-installed, tool-agnostic dispatcher) | publish issues, create work items, issue tracking, task list import, import issues, bulk create issues, seed project, upload task list, issue file, issue lifecycle, status transition, state change, field update, label update, priority update, assignee update | yes | — |
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
| 0.5 | build OR implement OR create OR add OR update OR fix OR remove OR move OR change OR migrate OR refactor OR replace OR extend OR integrate OR test OR deploy OR merge OR rollback OR write OR save OR edit OR publish OR commit | — BLOCK — | — | Restricted: mutating work must use crew:run |
| 1 | deploy OR "push to" OR "ci/cd" OR "cd pipeline" OR "release pipeline" | — BLOCK — | — | Restricted: devops requires supervisor approval gate — use crew:run |
| 2 | " review" OR "lint " OR " approve" OR "code review" OR "quality check" | — BLOCK — | — | Restricted: reviewer requires prior stage output — use crew:run |
| 3 | api OR endpoint OR server OR database OR schema OR domain OR service OR repository OR entity | backend | high | Matched backend keywords |
| 4 | component OR " page" OR " ui " OR " css" OR style OR layout OR button OR form OR modal OR react OR vue | frontend | high | Matched frontend keywords |
| 5 | wireframe OR mockup OR figma OR prototype OR sketch | designer | high | Matched design/UX keywords |
| 6 | design OR architecture OR plan OR decompose OR structure OR diagram | planner | high | Matched planning/architecture keywords |
| 6.5 | "어떤 에이전트" OR 방금 OR "what just" OR "what did this session" OR "what did we" OR "what ran" OR "what agent" OR "this session" OR "이번 세션" OR "this branch" OR "session history" OR "spawned agent" OR "what's running" OR "currently running" OR "recent activity" OR "어떤 commit" OR "무슨 commit" | historian | high | Matched session/git/project-state Q pattern |
| 7 | explain OR investigate OR understand OR trace OR audit OR explore | analyst | high | Matched analysis/exploration keywords |
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

## Read-only vs mutating: hook decision table

This table is the **single source of truth** for the read-only vs mutating
routing split that `core/hooks/auto-route.sh` enforces and that the README
describes in the "Auto-Execution Triggers" section. Both the hook and the
test suite (`tests/python/test_auto_route_issue_127.py`) read this table at
runtime — adding or changing a row updates the live contract.

The split (per issue #127):

- **Read-only Q&A / explanations / diagnostics / status / history → ROUTE → `crew:agent`.**
  Direct agent invocation, no supervisor pipeline, no worktree. crew:agent is
  the default path for read-only work so simple lookups stay cheap.
- **Implementation / mutation / issue publication / git ops → STOP → `crew:run`.**
  Full supervisor pipeline with the existing requirements collection,
  plan approval, stage execution, and reviewer gates.

The row format is `| "prompt" | ROUTE | reason |` or `| "prompt" | STOP | reason |`.
Every row is exercised by the docs/hook consistency test, so adding a new
example automatically pins the hook's behavior for that input.

| Example prompt | Directive | Reason |
|---|---|---|
| `"explain how the supervisor works"` | ROUTE | Question — codebase explanation |
| `"what just ran in this session"` | ROUTE | Question — session history lookup |
| `"show me the most recent commit"` | ROUTE | Question — git history Q (read-only) |
| `"list the available agents"` | ROUTE | Question — read-only enumeration |
| `"describe the routing flow"` | ROUTE | Question — codebase description |
| `"어떻게 동작하나요?"` | ROUTE | Korean question (read-only) |
| `"status"` | ROUTE | Trivial intent — read-only project status |
| `"Review the routing classifier for gaps; do not edit files."` | ROUTE | Read-only review with explicit "do not edit" marker |
| `"fix the bug in auto-route"` | STOP | Mutating verb (fix) — implementation |
| `"add a new test for routing"` | STOP | Mutating verb (add) — implementation |
| `"update README.md to mention X"` | STOP | Mutating verb (update) + file extension |
| `"commit the staged changes"` | STOP | Git operation — mutating |
| `"rename a variable"` | STOP | Mutating verb (rename) — refactor |
| `"refactor this function"` | STOP | Mutating verb (refactor) |
| `"remove the legacy alias"` | STOP | Mutating verb (remove) |
| `"change the default value"` | STOP | Mutating verb (change) |
| `"create issue for routing gap"` | STOP | Issue publication |
| `"push"` | STOP | Git operation — push |
| `"merge to main"` | STOP | Git operation — merge |
| `"배포해주세요"` | STOP | Korean deploy — mutating |
| `"버그를 수정해주세요"` | STOP | Korean fix (수정) — mutating |

### Read-only signal overrides

When a prompt mixes a mutating verb with an explicit read-only signal, the
read-only signal wins (preserves ROUTE). Recognized signals:

- A question marker (`QUESTION_PAT` in the hook: why / what / how / explain /
  Korean question endings such as 어떻게 / 뭐야 / 인가요 / 됩니까).
- A read-only review verb (`READONLY_REVIEW_PAT`: review / evaluate /
  inspect / diagnose / 검토 / 평가).
- A read-only complaint pattern (`READONLY_COMPLAINT_PAT`: 안 쓰 / 안 되 /
  자꾸 ...) without a paired mutation verb.
- An explicit marker: `do not edit`, `read-only`, `no files edited`,
  `수정하지 마`, `읽기 전용`.

This is why `"Inspect the routing classifier and identify gaps. Do not edit files."`
still routes to `crew:agent` even though it contains the action verb
"identify".

### How the hook enforces the split

Phases of `core/hooks/auto-route.sh` (in order):

1. **Fast path** — short trivial intents (`status`, `push`, `merge`, `git push`, …)
   are classified up front. `status` and `git status` go to ROUTE (read-only);
   everything else goes to STOP.
2. **Question detection** — prompts shaped as questions (`QUESTION_PAT` matches
   AND no mutating action verb) route to ROUTE → analyst or historian per the
   Auto-Routing Rules table above.
3. **Read-only review detection** — `READONLY_REVIEW_PAT` + `QUESTION_PAT`
   without `ACTION_PAT` (or with explicit "do not edit") routes to ROUTE → analyst.
4. **Domain detection** — `ACTION_PAT` + (backend / frontend / fullstack /
   design) routes to STOP → crew:run with a suggested pipeline.
5. **Extended detection** — `ACTION_PAT` paired with a file extension,
   agent-crew keyword, workflow verb, memory verb, or artifact verb routes
   to STOP → crew:run.
6. **Mutating-verb fallback (issue #127)** — `ACTION_PAT` matched but no
   prior layer fired AND no read-only signal is present → STOP → crew:run.
   This guard prevents bare mutating verbs (`fix`, `add`, `commit`, `rename`,
   `refactor`, `remove`, `change`, Korean `수정`) from leaking into the
   read-only ROUTE path.
7. **General read-only fallback** — no `ACTION_PAT` match, no specific
   domain match → ROUTE → analyst ("general user request"). This keeps
   crew:agent as the default for non-action conversational prompts.

The fallback ordering preserves both acceptance criteria of issue #127:
read-only Q&A stays on crew:agent (#1, #2) while mutating requests always
land on crew:run (#3). Docs and hook stay in sync because this table is
testable from a single source (#4).

---

## How orchestrators must use this file

1. **Mutating-task guard** — if the task string requests any file/document/
   issue/work-item creation or update, or any commit, merge, deploy, save,
   publish, or other state mutation, direct invocation is disallowed
   regardless of agent. Return the `crew:run` instruction instead.

2. **Agent name validation** — look up the agent name in the Agent Registry.
   If not found: error "unknown agent". If found but `Safe for direct
   invocation = no`: error with the `Reason if restricted` text.

3. **Auto-routing** — apply Auto-Routing Rules top-to-bottom against the
   normalized task string. Return the matched agent (or block/none result).

4. **Visibility** — always emit the `[crew:agent] →` line before spawning,
   including the agent name, confidence (if auto-routed), and reason text.

5. **No hard-coding** — orchestrators must read agent names exclusively from
   this file. Embedding agent names in command logic is a DIP violation.
