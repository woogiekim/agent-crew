# Agent Tool Dispatch Convention

## Purpose

This rule formalizes the **dispatcher + adapter-skill** pattern that the
`issuer` agent proves in production (commits `89d85a1`, `40631f6`, `1f89c02`).
It is the convention-discovery counterpart to
`core/rules/agent-skill-loading.md`, which covers explicitly-declared
on-demand skill loading. The two rules are complementary:

| Convention | Mechanism | Example |
|---|---|---|
| Declared skill loading (`agent-skill-loading.md`) | Agent file lists skills in a `## Skills (Loaded On Demand)` section, by path. | `backend` declares `core/agents/skills/effective-kotlin.md`, `core/agents/skills/tdd.md`. |
| Convention-based dispatch (this rule) | Agent detects an axis at runtime, then loads `<agent>-<tool>.md` from `~/.agent-crew/user/skills/`. | `issuer` detects the git remote, resolves to `issuer-github` / `issuer-plane` / etc. |
| Metadata-driven profile dispatch (this rule) | Agent scans user-owned skill frontmatter for an abstract contract and loads matching files by returned path, not by filename convention. | `reviewer` loads applicable `review-policy` / `review-profile` skills whose metadata says `loaded_by: reviewer`. |

An agent MAY use both conventions simultaneously. For example, a future
`backend` dispatcher MAY declare `tdd.md` + `effective-kotlin.md` via the
on-demand section *and* dispatch to `backend-kotlin-spring` via convention.

---

## The 5-step dispatch protocol

Any agent that opts into the dispatcher pattern executes these five steps
in order, **before** any vendor-specific tool call. The reference
implementation is `core/agents/issuer.md` Step 0 + Step 0.5.

### Step 1 — Detect axis

Inspect repo / project state to determine which `<tool>` variant applies.
The detection rule is per-agent — examples:

| Agent | Detection input | Resolved axis value |
|---|---|---|
| `issuer` | `git remote get-url origin` | `github`, `gitlab`, `plane`, … |
| `backend` (future) | `pom.xml` / `build.gradle.kts` / `package.json` / `Cargo.toml` | `kotlin-spring`, `typescript-nest`, `python-fastapi`, `rust-axum`, … |
| `frontend` (future) | `package.json` framework field | `typescript-react`, `typescript-vue`, `typescript-svelte`, … |
| `devops` (future) | presence of `.github/workflows/` / `.gitlab-ci.yml` / `fly.toml` | `github-actions`, `gitlab-ci`, `fly`, … |
| `designer` (future) | presence of Figma file / project metadata | `figma`, `sketch`, `penpot`, … |
| `documenter` (future) | project tracker config / wiki metadata | `notion`, `outline`, `confluence`, … |

If the detection input is empty or ambiguous, the agent MUST fall back to
the **interactive resolution** path (Step 4 below) — never silently default.

### Step 2 — Resolve `<agent>-<tool>` skill name

Concatenate the agent name with the detected axis value using a dash:

```
{AGENT_NAME}-{TOOL_AXIS}
```

Examples: `issuer-github`, `issuer-plane`, `backend-kotlin-spring`,
`frontend-typescript-react`, `devops-github-actions`,
`documenter-notion`.

This name is the canonical user-skill filename (sans `.md`). It is also
the canonical reference inside the dispatcher's user-facing prose (e.g.
`"... use the issuer-plane skill"`).

### Step 3 — Attempt skill load

Locate and load `~/.agent-crew/user/skills/<agent>-<tool>.md`. The load
mechanism is host-specific:

| Host | Mechanism |
|---|---|
| Claude Code | `Skill` tool (preferred) when the capability is available, or `Read` of the file path |
| Codex | Skill auto-discovery from `~/.codex/skills/` (the adapter's mirror of `~/.agent-crew/user/skills/`) |
| Generic adapter | `Read` of the file path |

The framework's `crew:setup` / `crew:update` flows seed and mirror user
skills into each host's discovery path automatically — see § Channel B
template seeding below. Agents themselves do not perform mirror copies.

### Step 4 — Branch on load result

The dispatcher's behaviour after the load attempt depends on the per-agent
fallback policy:

| Policy | Behaviour when skill is missing | Example agents |
|---|---|---|
| `BLOCKED` | Emit `STATUS: BLOCKED` with `BLOCKER: missing_adapter=<tool>` and stop. Do not call any external API as a workaround. | `issuer` (today) |
| `degraded-fallback` | Continue using only language-level / framework-agnostic skills (e.g., `tdd.md`, `effective-kotlin.md`). Emit a `[crew] DEGRADED | adapter=<tool>` warning before continuing. | `backend` (proposed Wave B) |
| `prompt-user` | Present a structured user-choice (`core/rules/capabilities/interactive-question.md`) offering "run in safe-mode / dry-plan-only" vs. "cancel". | (no current adopter — reserved for future agents whose missing adapter has a meaningful dry-plan fallback) |

Each agent file MUST declare its policy explicitly. If no policy is
declared, the default is `BLOCKED` (most restrictive — safest for
operations that mutate external state).

**Interactive resolution.** When Step 1 detection is empty / ambiguous,
the agent presents a structured user-choice (`core/rules/capabilities/interactive-question.md`)
asking the user to pick the axis. The options list MUST use the **skill
name** (`issuer-plane`, `issuer-github`) as the user-facing label, NOT
the underlying tool API namespace (`mcp__plane`, `mcp__gitlab`, `gh`).
The host tool / CLI namespace is owned by the loaded skill, not by the
dispatcher.

**Skill load enforcement rail.** Between Step 3 and Step 5, the
dispatcher MUST NOT execute any vendor-specific tool call (e.g.,
`mcp__plane__*`, `mcp__gitlab__*`, `gh api *`). Any such call before
the skill is loaded indicates the dispatcher has bypassed its own
dispatch boundary and must be treated as a workflow bug.

### Step 5 — Dispatch

Every tool call from this point forward MUST be invoked via the loaded
skill. The dispatcher owns:

- Operation classification (`create` / `transition` / `update` / …)
- Workflow shape (e.g., resolve-then-act, batch boundaries)
- Per-step status reporting

The skill owns:

- Tool / API selection (`mcp__plane__*`, `gh api …`, etc.)
- Vendor-specific request shapes (HTML body formats, header conventions)
- Vendor quirks (e.g., Plane Pydantic adapter quirks, GitHub rate-limit headers)
- Authentication / target resolution semantics

This separation is the load-bearing invariant of the dispatch pattern.
If the dispatcher's `.md` file mentions a concrete vendor tool name in
its prose (outside the Adapter Interface Contract section), that is a
leak of skill-layer knowledge into the dispatcher layer and should be
fixed in the same PR cycle.

---

## Metadata-driven skill dispatch

> Originally introduced as "Metadata-driven review-profile dispatch" in
> #137 and generalized to all opted-in agents in #186.

Capability and policy skills are not external vendor adapters. They are
user-owned lenses that may be named after a domain, codebase, capability,
or local convention. Therefore, capability/policy skill discovery MUST
NOT depend on a `<agent>-<tool>.md` filename and the requesting agent
MUST NOT mention concrete project/user skill filenames in its prose.

Agents use `core/scripts/review-profile-dispatch.py --agent <name>` to scan
`~/.agent-crew/user/skills/` and the unified `~/.agent-crew/skills/`
discovery path. The default `--agent reviewer` preserves the original
review-profile contract (#137); `--agent backend` and `--agent frontend`
opt in to the same primitive for capability-skill discovery (#186).

A skill qualifies for an agent when its YAML frontmatter satisfies:

```yaml
loaded_by: reviewer            # or: backend,frontend,reviewer (CSV)
profile_type: review-policy    # reviewer-only; optional for backend/frontend
axis: {capability-axis}        # e.g. code-cleanup, review-policy
detection: {project/task/file matching expression}
```

For the reviewer agent, `profile_type: review-profile` is also accepted.
For backward compatibility with existing reviewer skills, `loaded_by:
reviewer` plus a review-oriented `axis`/`description`/`detection`
contract is accepted when `profile_type` is absent. New reviewer skills
SHOULD include `profile_type` explicitly.

For `backend` / `frontend` (#186), the qualifying contract is simpler:
`loaded_by` containing the agent name plus an `axis` and `detection`
expression is sufficient. The reviewer-specific `profile_type` /
"review" keyword check does NOT apply.

The dispatcher returns a JSON payload:

```json
{
  "agent": "reviewer",
  "matched": [
    {
      "name": "user-owned-skill-name",
      "path": "/absolute/path/to/skill.md",
      "axis": "review-axis",
      "loaded_by": ["reviewer"],
      "detection": "project/task/file matching expression",
      "matched_by": "detection"
    }
  ],
  "fallback": false,
  "fallback_policy": "generic-reviewer-skills"
}
```

**Three-state dispatch result:**

1. **Script missing, crashed, or report-move failed** → emit one of three documented DEGRADED tokens:
   - `[crew] DEGRADED | capability-dispatch=script_missing agent=<name>` (the dispatcher script itself is absent).
   - `[crew] DEGRADED | capability-dispatch=script_failed agent=<name>` (the dispatcher ran but exited non-zero).
   - `[crew] DEGRADED | capability-dispatch=mv_failed agent=<name>` (the dispatcher succeeded but the atomic `mv` of the JSON report into the canonical path failed, e.g. due to a read-only TASK_DIR or a cross-device move).
   In every case, write a fallback JSON report with `"fallback": true`; continue with the agent's declared base skills only.
2. **Script succeeded, no matches** (`.matched[] == []`) → emit `[crew] CAPABILITY_SKILLS: none agent=<name>` and continue normally. This is the **expected** state when no user-owned capability skills are installed for this agent — it is NOT a degraded condition.
3. **Script succeeded, matches found** → read each `.matched[].path`; load the matched skills before the first execution step; cite loaded skill paths in `${TASK_DIR}/context/skill-use.json` (append a `{skill_path: ..., loaded_by: ...}` entry per matched skill, creating the file if absent). Agents that already write a more specific skill-use artifact (e.g. `context/review.md` for reviewer) record paths there instead.

For reviewer specifically, the historical compatibility token `[crew] DEGRADED | review-profile=none fallback=generic-reviewer-skills` MAY also be emitted alongside the canonical `CAPABILITY_SKILLS: none` line; both refer to the same "empty match, continue with generic review skills" state. (Finding [13]: the fallback policy literal is now the uniform `generic-reviewer-skills` form; the legacy `generic-review-skills` singular was retired.) New agents SHOULD emit only the canonical `CAPABILITY_SKILLS: none agent=<name>` token. Missing profiles never produce `STATUS: BLOCKED` regardless of agent.

This is a DIP boundary:

- Reviewer owns the abstract loading contract and fallback behavior.
- User profile skills own domain-specific heuristics and detection wording.
- `crew:setup` / `crew:update` continue preserving user-owned skills because
  runtime profiles live under `~/.agent-crew/user/skills/` and are merged into
  `~/.agent-crew/skills/` with user-wins semantics.

---

## Semantic evidence provider dispatch

Code intelligence tools are another dispatch axis, but the generic framework
must not bind itself to one language server. Implementation agents and
reviewers follow `core/rules/code-intelligence-evidence.md` and treat each
language server, compiler, type checker, or static analyzer as a semantic
evidence provider.

The dispatcher owns the abstract decision:

- detect the project language and available provider;
- record whether semantic capabilities are available;
- require `context/code-intelligence-evidence.json` for code changes when
  practical;
- fall back to `fallback-static` with explicit `unsupported_capabilities` when
  no stronger provider exists.

Provider adapters own the concrete calls:

- TypeScript LSP or `tsserver` queries for TypeScript / JavaScript;
- Pyright, Jedi, `gopls`, `rust-analyzer`, JDT Language Server, Kotlin tooling,
  compilers, or linters for their respective stacks;
- provider-specific diagnostic shapes and symbol lookup quirks.

This keeps TypeScript LSP as one semantic evidence provider while preserving a
language-agnostic and provider-agnostic implementation gate.

---

## Naming convention

Adapter skill files use **flat dashed** names:

| Pattern | Examples |
|---|---|
| `<agent>-<tool>` | `issuer-plane`, `issuer-github`, `issuer-gitlab`, `devops-aws`, `devops-fly`, `documenter-notion`, `documenter-outline`, `designer-figma` |
| `<agent>-<lang>-<framework>` | `backend-kotlin-spring`, `backend-typescript-nest`, `frontend-typescript-react`, `frontend-typescript-vue` |

**No subdirectory namespacing.** `core/setup/deploy-user-skill.sh` and the
`merge_skills_to_discovery` helper in `core/setup/common.sh` are both
flat-directory operations. A nested layout like
`~/.agent-crew/user/skills/issuer/plane.md` would break those scripts.

Operational benefit: `ls ~/.agent-crew/user/skills/` is a complete
inventory of every installed adapter without recursion. Use the
`core/scripts/list-installed-adapters.sh` helper to filter by agent
prefix programmatically.

The dashed structure is also the **only** convention; deviations require
a documented constraint and the rationale must be recorded in the agent
file that deviates.

---

## Channel B template seeding (framework primitive)

`commit 1f89c02` removed adapter skills from the source repo to enforce
a user-layer-only policy: production-proven vendor knowledge lives at
`~/.agent-crew/user/skills/<agent>-<tool>.md` and is never overwritten
by `crew:update`.

This rule preserves that policy while still letting the framework ship
**seed templates** for vendor knowledge. The mechanism is:

| Path | Purpose | Overwritable? |
|---|---|---|
| `core/agents/skills/templates/<agent>-<tool>.md` | Framework-shipped seed template. Tracked in the source repo. | Yes (by source sync — it is the framework's canonical copy). |
| `~/.agent-crew/system/agents/skills/templates/<agent>-<tool>.md` | Installed mirror of the source template. | Yes (replaced by `crew:update` from source). |
| `~/.agent-crew/user/skills/<agent>-<tool>.md` | Runtime artifact loaded by the dispatcher. | **NEVER overwritten by `crew:update`.** |

`crew:setup` and `crew:update` seed missing user-layer skills from the
matching template using copy-if-absent semantics. When the user-layer
file already exists, the template is NEVER applied — even if its content
differs from the template byte-for-byte. The template directory is NOT
copied into the unified `~/.agent-crew/skills/` discovery path; it is a
seed source, not a runtime artifact.

`crew:update` also runs a passive reconcile check: if a user-layer skill
differs from its template, a single advisory line is printed
(`[crew:update] templates/<name> diverged from user skill (N lines); run 'crew:update --reconcile-skills' to compare`).
The optional `--reconcile-skills` flag writes a unified diff to
`~/.agent-crew/state/<project>/reconcile/<name>.diff` and stops there.
The user reads the diff out-of-band and decides whether to hand-merge.
**No automatic write to the user layer ever happens.**

The full operational design lives at
`core/setup/seed-skill-templates.sh` (the seed-on-install/update helper)
and `core/setup/reconcile-skill-templates.sh` (the opt-in diff helper).
See `core/commands/setup.md` § Skill Template Seeding and
`core/commands/update.md` § Skill Template Reconcile for the
install/update integration points.

### Exception: dead-code-elimination ships as a system-wide framework default

`dead-code-elimination` is the single, named exception to the
user-opt-in-only capability-skill rule. It ships at the dispatcher
discovery-dir location `core/agents/skills/dead-code-elimination.md` and
is auto-loaded framework-wide for `backend` and `frontend` whenever the
task body matches its `detection` regex
(`cleanup|refactor|dead.code|unused`).

Rationale: cleanup and refactor work is the framework's
quality-improvement default. The skill is a low-risk pre-deletion safety
checklist, applies to every refactor/cleanup task, and is keyed off the
implementer's task body rather than a vendor adapter — so the
user-opt-in barrier does not buy safety here. Auto-loading lets
backend/frontend recognize and act on dead-code signals across every
installation without requiring per-user opt-in.

This exception is **narrow and named**: it applies to
`dead-code-elimination` only. The general user-opt-in-only rule
(Channel B template seeding above) remains in force for every other
capability skill — production-proven vendor knowledge continues to live
at `~/.agent-crew/user/skills/<agent>-<tool>.md` and is never
auto-loaded from the source repo.

---

## Open/Closed extension protocol

**Adding a new adapter requires only:**

1. Write `~/.agent-crew/user/skills/<agent>-<tool>.md` following the
   adapter interface contract of the relevant agent.
2. Run `core/setup/deploy-user-skill.sh <agent>-<tool>.md` to mirror
   the file into every installed host adapter's discovery path.

**Adding a new framework-shipped seed template requires only:**

1. Write `core/agents/skills/templates/<agent>-<tool>.md` in the source
   repo.
2. The next `crew:setup` / `crew:update` seeds it into
   `~/.agent-crew/user/skills/` automatically (only if a user-layer
   file does not already exist).

**What does NOT need to change:**

- This rule file.
- Any agent file that already follows the 5-step protocol.
- `core/setup/deploy-user-skill.sh` (it is naming-convention-agnostic — flat copy).
- The unified `~/.agent-crew/skills/` discovery view (templates are
  excluded by directory; user skills are merged with system-wins-on-name
  via `merge_skills_to_discovery`).

This is the Open/Closed guarantee for the dispatch pattern.

---

## Agents subject to dispatch

The following agents are eligible to adopt this protocol. The list is
informational; an agent's own `.md` file is the authoritative source of
whether it has opted in.

| Agent | Status | Axis |
|---|---|---|
| `issuer` | Opted in (reference implementation, commit `1f89c02`; also metadata-driven skill dispatch) | tracker (git remote) **and** cross-cutting issue/policy metadata |
| `backend` | Opted in (metadata-driven skill dispatch, #186) | language / framework manifest **and** capability-skill metadata |
| `frontend` | Opted in (metadata-driven skill dispatch, #186) | framework (`package.json`) **and** capability-skill metadata |
| `devops` | Opted in (metadata-driven skill dispatch) — formerly Wave-C candidate | cloud / CI (manifest files) **and** capability-skill metadata |
| `designer` | Opted in (metadata-driven skill dispatch) — formerly Wave-C candidate | design tool **and** capability-skill metadata |
| `documenter` | Opted in (metadata-driven skill dispatch) — formerly Wave-C candidate | wiki / docs tool **and** capability-skill metadata |
| `reviewer` | Opted in (review-profile dispatch) | review-policy metadata |
| `test-writer` | Opted in (metadata-driven skill dispatch) | capability-skill metadata |
| `qa-owner` | Opted in (metadata-driven skill dispatch) | capability-skill metadata |
| `planner` | Opted in (metadata-driven skill dispatch) | capability-skill metadata |
| `analyst` | Opted in (metadata-driven skill dispatch) | capability-skill metadata |
| `requirements` | Opted in (metadata-driven skill dispatch) | capability-skill metadata |
| `resolver` | Opted in (metadata-driven skill dispatch) | capability-skill metadata |

### Capability/domain skill flow for `backend` / `frontend`

The `backend` and `frontend` dispatchers participate in two complementary
load paths:

1. **Adapter skill load** — the existing 5-step convention picks one
   `<agent>-<lang>-<framework>` template per dispatch (e.g.
   `backend-kotlin-spring`, `frontend-typescript-react`).
2. **Metadata-driven capability skill load** — additional skills whose
   frontmatter declares `loaded_by: backend` (or `frontend`) plus a
   capability `axis` and a `detection` expression are discovered at
   runtime via `core/scripts/review-profile-dispatch.py --agent backend`
   (or `--agent frontend`). These cover language-/framework-agnostic
   capabilities such as `code-cleanup`, `error-handling`, and similar
   cross-cutting concerns.

Because capability skills are user-named and may evolve per project,
they MUST NOT be hard-coded into the dispatcher's prose. The
`## Skills (Loaded On Demand)` section of `backend.md` / `frontend.md`
continues to list **base** language-agnostic skills explicitly (TDD,
`oop-principles`, etc.); cross-cutting capability skills are picked up
through metadata dispatch only.

The dispatcher fallback policy for capability skills follows the same
three-state semantics described in § "Metadata-driven skill dispatch":

| State | Token emitted | Continue? |
|---|---|---|
| Script missing | `[crew] DEGRADED | capability-dispatch=script_missing agent=<name>` | Yes — declared base skills only |
| Script crashed | `[crew] DEGRADED | capability-dispatch=script_failed agent=<name>` | Yes — declared base skills only |
| Report move failed | `[crew] DEGRADED | capability-dispatch=mv_failed agent=<name>` | Yes — declared base skills only |
| No matches (expected) | `[crew] CAPABILITY_SKILLS: none agent=<name>` | Yes — normal flow |
| Matches found | (none — read `.matched[].path` and load) | Yes — normal flow with loaded skills |

For backend / frontend specifically, `<name>` is `backend` or `frontend`.
The canonical token is emitted by the dispatch block in each agent's
`.md` file (see `core/agents/backend.md` § "Capability Dispatch" and
`core/agents/frontend.md` § "Capability Dispatch"). Missing capability
skills never produce `STATUS: BLOCKED`.

## Agents not subject to dispatch

> Scope: this section excludes the listed agents from the **vendor-adapter**
> 5-step dispatch pattern (Channel B / `<agent>-<tool>.md` flat-name lookup)
> only. Some agents listed here participate in the **metadata-driven
> capability-skill dispatch** path (see the catalog table above) even though
> they have no vendor adapter; the inline notes record that overlap.

The following agents are **explicitly excluded** from the vendor-adapter
dispatch pattern. They are weak-fit because they either have no external vendor
axis, or their vendor axis is already factored out elsewhere
(host-capability flags, git itself). Documenting the exclusion prevents
future drift in the form of "should we add a vendor adapter to X?" discussions.

| Agent | Reason (vendor-adapter exclusion only) |
|---|---|
| `historian` | Internal git + state lookups only. No external vendor axis. |
| `resolver` | Pure git operation. `git` is the only "tool". (Capability-skill dispatch: opted in — see catalog above.) |
| `requirements` | Interactive structured choice. Host-capability axis already covered by `core/rules/capabilities/interactive-question.md`. (Capability-skill dispatch: opted in.) |
| `supervisor` (+ `supervisor-bootstrap`, `supervisor-stages`, `supervisor-retry`) | Internal orchestration. The host-capability axis is its vendor axis and is already factored out via `capabilities.json`. |
| `input-normalizer`, `korean-normalizer` | Pure-text utilities. No tool axis. |
| `analyst`, `planner` | Moderate-fit candidates for vendor adapters; not opting in until concrete vendor-axis evidence appears (see `docs/issuer-vendor-skill-layer-dip-review/generalized-dispatcher-primitive.md` § 1 Verdict statement). (Capability-skill dispatch: opted in.) |
| `mentor`, `learning-mentor` | Moderate-fit candidates; not opting in until concrete vendor-axis evidence appears. |
| `test-writer` | Test framework variation is already covered by language skills (`tdd.md`, `effective-*.md`). Vendor-adapter split would over-engineer. (Capability-skill dispatch: opted in.) |

---

## Audit / verification

**List every installed adapter for a given dispatcher agent:**

```bash
bash core/scripts/list-installed-adapters.sh issuer
# → github
#   plane
```

**Verify a dispatcher agent's `.md` does not leak vendor literals into
user-facing prompts:**

```bash
# Vendor tool namespaces should appear only inside the Adapter Interface
# Contract section, never inside Step 0 / Step 0.5 interactive resolution.
grep -nE 'mcp__plane|mcp__gitlab|gh api' core/agents/<agent>.md
```

**Verify the user-layer file exists for every declared adapter:**

```bash
for adapter in $(bash core/scripts/list-installed-adapters.sh <agent>); do
  test -f "${HOME}/.agent-crew/user/skills/<agent>-${adapter}.md" \
    && echo "OK  <agent>-${adapter}" \
    || echo "MISSING  <agent>-${adapter}"
done
```

---

## See also

- `core/rules/agent-skill-loading.md` — declared skill loading (complementary)
- `core/setup/deploy-user-skill.sh` — adapter-agnostic flat-copy mechanism
- `core/setup/seed-skill-templates.sh` — Channel B template-seed helper
- `core/setup/reconcile-skill-templates.sh` — Channel B reconcile helper
- `core/scripts/list-installed-adapters.sh` — adapter enumeration helper
- `core/agents/issuer.md` — reference implementation of the 5-step protocol
- `docs/issuer-vendor-skill-layer-dip-review/generalized-dispatcher-primitive.md`
  — design rationale and per-agent fit analysis
