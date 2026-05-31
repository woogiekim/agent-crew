# Generalized Dispatcher + `<agent>-<tool>` Skill Pattern as a Framework Primitive

**Scope:** broad. Formalize the dispatcher + adapter-skill pattern that
`issuer` adopted in commits `#56`, `#59`, and `#1f89c02` as a first-class
framework primitive that other strong-fit agents can opt into without
re-deriving the pattern.

**Companion doc:** `issuer-vendor-promotion.md` (narrow case). The narrow
case should ship on its own evidence regardless of how this doc lands.

---

## 1. Verdict statement

After classifying every agent currently under `core/agents/` (and the
companion sub-modules), the dispatcher + `<agent>-<tool>` skill pattern is:

- **Strong-fit (6 agents):** `backend`, `frontend`, `devops`, `issuer`
  (existing reference implementation), `designer`, `documenter`.
- **Moderate-fit (4 agents):** `planner`, `mentor` (alias `learning-mentor`),
  `reviewer`, `analyst`.
- **Weak-fit (9 agents):** `historian`, `resolver`, `requirements`,
  `supervisor` and its three sub-modules (`supervisor-bootstrap`,
  `supervisor-stages`, `supervisor-retry`), `input-normalizer`,
  `korean-normalizer`. Test-writer is borderline weak.

The strong-fit set clears the ship-threshold. The moderate set is worth
revisiting after the strong-fit wave is in production. The weak set should
be left alone — applying the pattern there would create maintenance burden
without proportional value.

---

## 2. Per-agent fit analysis

The fit criterion is: **does this agent's behaviour change materially based
on which external tool/runtime it talks to, in a way that today forces
vendor-specific prose into the agent file itself?**

| Agent | Fit | Reason |
|---|---|---|
| `backend` | **strong** | Behaviour differs across runtimes (Spring Boot, NestJS, Express, FastAPI, Rails, Go HTTP, gRPC). Today the agent's prose stays generic but the *skills* it loads (`api-design.md`, `database-design.md`, `effective-java.md`, `effective-kotlin.md`, etc.) already lean to specific stacks. A `<agent>-<lang>-<framework>` dispatcher formalizes the split. |
| `frontend` | **strong** | React vs Vue vs Angular vs Svelte vs Solid require distinct idioms. Today the agent must hold all of them; a dispatcher loads `frontend-react-vite`, `frontend-vue3`, etc. |
| `devops` | **strong** | Cloud (AWS / GCP / Azure / fly.io / Vercel / on-prem k8s) and CI (GitHub Actions / GitLab CI / Buildkite / CircleCI) are the axis. Pattern is identical to `issuer`'s tracker axis. |
| `issuer` | **strong** | The original case — already shipped as the reference implementation (`core/agents/issuer.md` + `core/rules/agent-tool-dispatch.md`, commit `1f89c02`). This PR set ratifies the pattern; no further work on the issuer agent itself is required. |
| `designer` | **strong** | Figma vs Sketch vs Penpot vs raw HTML mockup is a vendor axis. Today the agent prose handles only Figma-like tooling. |
| `documenter` | **strong** | Notion vs Outline vs Confluence vs raw-markdown vs Slab is a vendor axis. Each tool's create / update / link semantics differ enough to dwarf the prose. |
| `planner` | **moderate** | Behaviour is mostly LLM reasoning, but project-management tool integration (Plane / Jira / Linear / GitHub Projects) is a real axis when the planner writes the plan to a tracker. If the planner never writes to a tracker, dispatcher buys nothing. |
| `mentor` / `learning-mentor` | **moderate** | The teaching surface is tool-agnostic, but learning-platform integration (Replit, GitHub Classroom, internal LMS) would benefit. Today no such integration exists; pattern is speculative. |
| `reviewer` | **moderate** | The review act is tool-agnostic, but **posting reviews** to a tracker is the same axis as `issuer`. If reviewer ever posts inline PR comments via tool A / tool B, a `reviewer-<tool>` skill makes sense. |
| `analyst` | **moderate** | Mostly internal — produces `analysis.md`, `prd.md`, `pipeline.json`, `handoff.md`. No external vendor axis today. Could become strong if analyst learns to file analysis docs to a wiki tool. |
| `historian` | **weak** | Internal git + state lookups only. No external vendor axis. |
| `resolver` | **weak** | Pure git operation. `git` is the only "tool". |
| `requirements` | **weak** | Interactive structured choice — host-capability axis already covered by `core/rules/capabilities/interactive-question.md`. No vendor split. |
| `supervisor` + 3 sub-modules | **weak** | Internal orchestration. The host-capability axis IS the vendor axis here, and it is already factored out via `capabilities.json`. |
| `input-normalizer` / `korean-normalizer` | **weak** | Pure-text utilities. No tool axis. |
| `test-writer` | **borderline weak** | Test-framework axis (JUnit / Kotest / Vitest / pytest / RSpec) does exist, but the framework is usually obvious from the existing test files in the repo. A skill split is over-engineering. Skill files already cover the variation (`tdd.md`, `effective-kotlin.md`, etc.). |

---

## 3. The common 5-step dispatcher protocol

Crystallized from `core/agents/issuer.md` Step 0 + Step 0.5. Any agent that
opts into the pattern follows the same 5 steps:

```text
1. Detect axis              — Inspect repo / project state to determine
                              which `<tool>` variant applies. Examples:
                              `git remote get-url origin` for issuer,
                              `package.json` framework field for frontend,
                              `pom.xml` / `build.gradle.kts` / `Cargo.toml`
                              for backend.

2. Resolve <agent>-<tool>   — Concatenate the agent name with the detected
   skill name                 axis value: `frontend-react-vite`,
                              `backend-spring-kotlin`, `devops-github-actions`.

3. Attempt load              — Use the host's skill-loading mechanism
                              (Claude Code Skill tool, Codex skill discovery,
                              generic adapter Read of the file). The load
                              is conventional, not registry-based.

4. Branch                    — If skill is found: execute its Step 0
                              (authenticate / resolve target / emit
                              TARGET_SUMMARY). If not found: the agent
                              applies its per-agent fallback policy
                              (BLOCKED for issuer, degraded-fallback for
                              backend, etc. — defined in each agent file).

5. Dispatch                  — Every tool call from this point forward
                              MUST be invoked via the loaded skill, never
                              directly by the dispatcher agent. Skill
                              owns the vendor knowledge; dispatcher owns
                              the workflow shape.
```

This is exactly what `issuer.md` Step 0 (lines 184–262) + Step 0.5 (lines
264–340) currently encode. Generalizing it means **lifting those two steps
into `core/rules/agent-tool-dispatch.md`** and having the strong-fit agents
reference the rule rather than re-stating it inline.

---

## 4. Naming convention

**Convention:** flat dashed `<agent>-<tool>` or
`<agent>-<lang>-<framework>`. No subdirectory namespacing.

| Pattern | Examples |
|---|---|
| `<agent>-<tool>` | `issuer-plane`, `issuer-github`, `issuer-gitlab`, `devops-aws`, `devops-fly`, `documenter-notion`, `documenter-outline`, `designer-figma` |
| `<agent>-<lang>-<framework>` | `backend-kotlin-spring`, `backend-typescript-nest`, `frontend-typescript-react`, `frontend-typescript-vue` |

**Why no subdirectory namespacing:** `core/setup/deploy-user-skill.sh` already
copies files as a **flat directory copy** (`cp "${SKILL_PATH}" "${CLAUDE_CREW_SKILLS}/${SKILL_BASENAME}"`,
see lines 51–83 of that script). Introducing
`~/.agent-crew/user/skills/issuer/plane.md` instead of
`~/.agent-crew/user/skills/issuer-plane.md` would break that deploy script
for every installed host adapter (Claude, Codex, generic).

The flat naming is also operationally friendly: `ls ~/.agent-crew/user/skills/`
gives an immediate inventory of every installed adapter without recursive
listing.

---

## 5. Framework primitives needed

To support strong-fit agents adopting the pattern with **no per-agent
re-derivation**, four primitives are needed. All are additive; none break
back-compat.

### 5.1 NEW — `core/rules/agent-tool-dispatch.md`

Formalize the 5-step protocol from § 3 above as a rule. Every dispatcher
agent then writes one short Step 0 that says "Apply the 5-step protocol
defined in `core/rules/agent-tool-dispatch.md` with axis-detection rule
`<axis>` and skill prefix `<agent>-`." Without this rule, every dispatcher
agent independently re-derives Step 0 / Step 0.5 — drift is inevitable.

Expected size: ~80–120 lines. Mirrors the structure of existing
`core/rules/agent-skill-loading.md` (151 lines) which formalizes the **how
to declare loaded skills** half of the contract. The new rule covers the
**how to dispatch by axis** half — they are complementary.

### 5.2 NEW — `core/bin/list-installed-adapters` helper

A ~10-line bash helper:

```bash
#!/usr/bin/env bash
# list-installed-adapters <agent-name>
# Prints the list of installed adapters for a given dispatcher agent.
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PREFIX="$1"
[ -z "$PREFIX" ] && { echo "usage: list-installed-adapters <prefix>" >&2; exit 1; }
ls "${AGENT_CREW_HOME}/user/skills/" 2>/dev/null \
  | sed -n "s/^${PREFIX}-\(.*\)\.md$/\1/p" \
  | sort -u
```

Used by:
- The dispatcher's BLOCKED message ("supported adapters with installed
  skills: …") — replaces the inline `ls` glob currently in `issuer.md`
  step 0.5.4.
- `crew:status` could surface "this project has issuer-plane and devops-aws
  configured" for visibility.
- Documentation auto-generation (later).

### 5.3 OPTIONAL — `tool-pins.json` schema

A per-project pin file (`<project>/.agent-crew/tool-pins.json`) so projects
can override axis detection. Today, axis detection is auto from repo state
(git remote, package.json, etc.). A pin file would allow:

```json
{
  "issuer":   "plane",
  "backend":  "kotlin-spring",
  "devops":   "github-actions"
}
```

This is **optional** because the auto-detection paths already work. Pins
help when:
- A repo is migrating from tracker A to tracker B and both remotes exist.
- A monorepo has multiple backends and the dispatcher cannot disambiguate
  from working-directory inspection alone.

Defer this to Wave-C unless reviewers see immediate value.

### 5.4 AMEND — `core/rules/agent-skill-loading.md`

Add a one-paragraph cross-reference to the new
`core/rules/agent-tool-dispatch.md`:

> Dispatcher agents that load adapter skills by convention (rather than via
> the explicit `## Skills (Loaded On Demand)` section above) follow the
> 5-step protocol in `core/rules/agent-tool-dispatch.md`. The two
> conventions are complementary: skill-loading covers **declared**
> skill consumption; tool-dispatch covers **convention-discovered**
> adapter skills. An agent may use both — for example, `backend` may
> declare `effective-kotlin.md` and `tdd.md` via the on-demand section
> while *also* dispatching to `backend-kotlin-spring` via convention.

This is a 5-line edit. It prevents the two conventions from being
mistakenly seen as competing.

---

## 6. Back-compat & migration mechanics

The pattern is **mechanical and additive** for every agent that opts in:

1. Keep the existing `agent.md` backbone intact — the agent's role,
   inputs, outputs, and the per-stage workflow contract stay where they
   are.
2. Extract tool-specific content from the agent file into one or more
   `<agent>-<tool>.md` user-layer skill files. The extraction is a copy +
   delete of clearly-bounded sections (almost always: API call examples,
   error-handling tables, vendor-specific gotchas).
3. Add a Step 0 to the agent file that invokes the 5-step protocol from
   the new `core/rules/agent-tool-dispatch.md` rule.
4. Define the per-agent fallback policy for "skill not found":
   - `BLOCKED` (issuer's choice) — stop and ask the user. Appropriate when
     the agent cannot do useful work without a tool binding.
   - `degraded-fallback` (proposed for backend / frontend) — proceed
     using only the language-level skills (`effective-kotlin.md`,
     `tdd.md`) without framework-specific tooling. Emit a warning and
     log that the run was degraded.
   - `prompt-user` (proposed for devops) — present a structured choice
     to confirm "no devops skill found; run in dry-run-plan-only mode?".

Critically, **agents that don't migrate continue to work unchanged**. The
new rule and the helper script are dormant for non-opted agents.

---

## 7. PR waves

Bounded waves so each PR is reviewable in one sitting (~300–500 lines diff).

### Wave A — Framework primitives (foundation)

- NEW `core/rules/agent-tool-dispatch.md` (5-step protocol formalization).
- NEW `core/bin/list-installed-adapters` (10-line helper + 1 test).
- AMEND `core/rules/agent-skill-loading.md` (5-line cross-reference).
- Tests: 2 shell tests covering the helper script (installed / not
  installed paths). Lives in `tests/shell/list-installed-adapters.bats`.

**Estimated diff:** ~150–200 lines. No agent files touched. No back-compat
risk. Lands first because every later wave references it.

### Wave B — Issuer (from local prototype) + Backend with degraded-fallback

- `issuer` migration — re-states its Step 0 / Step 0.5 as a one-paragraph
  invocation of the new rule. Removes the inline 5-step protocol code from
  `core/agents/issuer.md`. Net file shrink: ~100 lines.
- `backend` migration — adds Step 0 dispatcher, extracts framework-specific
  content into `backend-kotlin-spring.md` and `backend-typescript-nest.md`
  user-layer skills (template channel per `issuer-vendor-promotion.md` § 5).
  Backend agent file shrinks; new skill files appear as templates.

**Why pair them:** issuer is the existence proof; backend is the
"degraded-fallback policy" exemplar. Reviewing both at once locks the
policy taxonomy in.

### Wave C — Frontend, Devops, Designer, Documenter

- `frontend`, `devops`, `designer`, `documenter` migrations. Each follows
  the Wave B pattern.
- Each gets one or two reference-template skill files seeding the most
  common variants (React, AWS, Figma, Notion).
- Optional: introduce the `tool-pins.json` schema (§ 5.3) if reviewers
  approved it in Wave A discussion.

**Estimated diff per agent:** ~200–400 lines (mostly content extraction,
small agent-file edits).

### Wave D — Moderate-fit agents (optional, deferred)

- `planner`, `mentor`, `reviewer`, `analyst` migration if there's
  demonstrated demand. The pattern fit is real but the production
  evidence (live regressions caused by missing tool dispatch) is not
  yet there for any of these agents.
- Could be deferred indefinitely. Wave D is an "open option", not a
  commitment.

### Phase 3 — Weak-fit agents: do nothing

- `historian`, `resolver`, `requirements`, `supervisor` + sub-modules,
  `input-normalizer`, `korean-normalizer`, `test-writer` — explicit
  no-migration decision, documented in `agent-tool-dispatch.md` § "Agents
  not subject to dispatch". The decision is itself the artifact —
  prevents future drift in the form of "should we add dispatch to X?"
  discussions.

---

## 8. Discovery mechanism — no per-agent specialization

`core/setup/deploy-user-skill.sh` (91 lines, current upstream) is already
**adapter-agnostic**. Its flow:

```text
1. Take a bare filename as input.
2. Verify it exists at ~/.agent-crew/user/skills/<file>.
3. Enumerate installed host adapters by sentinel path (~/.claude/agents/,
   ~/.codex/agents/, $PWD/.agent-crew/).
4. Copy the skill file to each adapter's discovery path.
```

There is **no agent-specific branching** in this script. Adding 100 new
adapter skills (`backend-kotlin-spring.md`, `frontend-react-vite.md`, etc.)
costs zero changes to deploy-user-skill.sh. The script picks them up via
its flat-copy mechanism (lines 51–83 of the script).

The only requirement is the naming convention (§ 4) — flat dashed names,
no subdirectories. That convention is already enforced by the script's
`SKILL_BASENAME="$(basename "${SKILL_FILE}")"` line and by `crew:agent-maker`'s
file-creation flow.

---

## 9. Ship-threshold call

Three gains, in priority order:

1. **Capability (drop-one-file onboarding).** Today, adding a new tracker
   adapter (say, Linear) requires: write `~/.agent-crew/user/skills/issuer-linear.md`,
   run `deploy-user-skill.sh`. That's it — the dispatcher already picks
   it up. Generalizing to frontend / backend gives the same drop-one-file
   onboarding for *frameworks*: add Solid support by dropping
   `frontend-solid.md`. No agent file edits, no PR, no rebuild.
2. **Token economy.** A monolithic `backend.md` that covers Spring,
   NestJS, FastAPI, Rails, Go HTTP and gRPC is **always** loaded in full
   by every backend invocation, even when the project is single-stack.
   Dispatcher + per-framework skills load only the relevant skill —
   expected several-fold reduction in always-loaded prompt size for
   single-stack repositories; precise multiplier deferred to a Wave-B
   operational measurement once at least one strong-fit agent has
   shipped the dispatcher pattern.
3. **Maintainability.** Today, when Spring Boot 3.5 changes a contract,
   the backend.md owner edits the monolithic file and risks regression
   for NestJS users. With dispatcher + per-framework skills, only
   `backend-kotlin-spring.md` changes; NestJS users are insulated by
   construction.

**Honest framing:**
- Gains 1 + 2 are quantifiable and clearly clear the strong-fit threshold.
- Gain 3 is real but harder to evidence without a regression-history audit.
- The moderate-fit set does not yet clear the threshold because no analogous
  evidence of capability / token / maintenance pain exists for those
  agents. Revisit after Wave A + B + C have produced operational data.

The strong-fit verdict ships. The moderate verdict waits.

---

## 10. Recommendation

**File ONE upstream issue covering both this doc and `issuer-vendor-promotion.md`.**

The issue body should:

- Link to both docs as the design rationale.
- Propose the PR wave plan from § 7 (A → B → C, with D and Phase 3 noted).
- Pose the three open questions from `issuer-vendor-promotion.md` § 8 plus
  the moderate-fit question from this doc § 1 ("how do we revisit Wave D
  agents — needs-driven or scheduled?").
- Frame Wave A as the minimal commitment ask. If reviewers approve only
  Wave A, the framework is still better off (the rule + helper exist for
  future use) and the issuer narrow promotion still ships independently.

**Sequence:** Wave A merges → narrow `issuer-vendor-promotion.md` PR merges
in parallel (since it does not depend on Wave A) → Wave B exemplars land →
Wave C scales out → Wave D is left as an open issue.

---

## 11. Open questions for upstream

1. **Template channel choice.** Same as `issuer-vendor-promotion.md` § 8 Q1.
   Affects every wave, so worth resolving up-front.
2. **`tool-pins.json` priority.** Ship in Wave A, Wave C, or defer? § 5.3.
3. **Moderate-fit reactivation policy.** "When does Wave D earn priority?"
   Concrete trigger: e.g. "first time a moderate-fit agent ships a
   vendor-specific edit, file a Wave D issue for that agent."
4. **Documentation surface.** Should each `<agent>-<tool>.md` skill ship
   with a stub `<agent>-<tool>.example.md` for users? Could explode the
   skill catalogue but improves onboarding. Lean: no, defer to community
   contributions.

---

## 12. Out of scope (explicitly)

- The actual implementation of Wave A / B / C / D. This doc is a research
  proposal, not a coded change.
- Migrating the strong-fit agents in this same task. Each migration is a
  separate PR per § 7.
- Filing the upstream GitHub issue. Phase 2 work.
- Any change to `core/agents/skills/` system skills (`tdd.md`,
  `api-design.md`, etc.). Those are unaffected — they are "loaded on
  demand" per `core/rules/agent-skill-loading.md`, not "dispatched by
  convention".
- Removing legacy aliases (`learning-mentor`, `korean-normalizer`). Those
  are routing-rule concerns, not dispatch-pattern concerns.

---

## 13. Citation map

| Claim | Evidence |
|---|---|
| `issuer` dispatcher pattern is in production | Commits `89d85a1` (#56), `40631f6` (#59), `1f89c02`, `2543527` |
| `core/setup/deploy-user-skill.sh` is adapter-agnostic | `core/setup/deploy-user-skill.sh` lines 51–83 (flat-copy loop, no per-agent branching) |
| Skill loading convention exists and is documented | `core/rules/agent-skill-loading.md` (151 lines) — this proposal complements it with a dispatch-by-convention rule |
| Live E2E is the production-evidence bar | mnemos memory `feedback_prefer-live-e2e` (project rule) + shopping commit `24f9719d8` |
| Research-before-implementation discipline | mnemos memory `feedback-research-before-implementation` — this doc IS the research |
| Ship-threshold framing | mnemos memory `feedback-ship-threshold` |
| User-layer-only adapter-skill policy | Commit `1f89c02` + its embedded mnemos memory `711045c9-8378-41fb-88c2-d8a5e9079f36` |
| Local prototype validating the issuer dispatcher | Task `~/.agent-crew/state/shopping/tasks/20260531-111840-0/` |
| Commit-message convention examples | `0c47ce3`, `68fc277`, `f288ef0`, `d501a25` |
