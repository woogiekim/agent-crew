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
| `prompt-user` | Present a structured user-choice (`core/rules/capabilities/interactive-question.md`) offering "run in safe-mode / dry-plan-only" vs. "cancel". | `devops` (proposed Wave C) |

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

## Metadata-driven review-profile dispatch

Reviewer policy profiles are not external vendor adapters. They are user-owned
review lenses that may be named after a domain, codebase, review style, or
local convention. Therefore, reviewer profile discovery MUST NOT depend on a
`reviewer-<tool>.md` filename and the reviewer agent MUST NOT mention concrete
project/user skill filenames.

The reviewer uses `core/scripts/review-profile-dispatch.py` to scan
`~/.agent-crew/user/skills/` and the unified `~/.agent-crew/skills/`
discovery path. A skill qualifies as a reviewer review profile when its YAML
frontmatter satisfies:

```yaml
loaded_by: reviewer
profile_type: review-policy
detection: {project/task/file matching expression}
```

`profile_type: review-profile` is also accepted. For backward compatibility
with existing user skills, `loaded_by: reviewer` plus a review-oriented
`axis`/`description`/`detection` contract is accepted when `profile_type` is
absent. New skills SHOULD include `profile_type` explicitly.

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
  "fallback_policy": "generic-review-skills"
}
```

If no profile applies, reviewer follows the `degraded-fallback` policy:
emit `[crew] DEGRADED | review-profile=none fallback=generic-review-skills`
and continue with its generic review skills (`code-review.md`,
`clean-architecture.md`, language-specific effective-* guidance, and
`code-quality.md`). Missing review profiles never produce `STATUS: BLOCKED`.

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
| `issuer` | Opted in (reference implementation, commit `1f89c02`) | tracker (git remote) |
| `backend` | Wave-B candidate | language / framework (manifest file) |
| `frontend` | Wave-C candidate | framework (`package.json`) |
| `devops` | Wave-C candidate | cloud / CI (manifest files) |
| `designer` | Wave-C candidate | design tool |
| `documenter` | Wave-C candidate | wiki / docs tool |
| `reviewer` | Opted in (review-profile dispatch) | review-policy metadata |

## Agents not subject to dispatch

The following agents are **explicitly excluded** from the dispatch
pattern. They are weak-fit because they either have no external vendor
axis, or their vendor axis is already factored out elsewhere
(host-capability flags, git itself). Documenting the exclusion prevents
future drift in the form of "should we add dispatch to X?" discussions.

| Agent | Reason |
|---|---|
| `historian` | Internal git + state lookups only. No external vendor axis. |
| `resolver` | Pure git operation. `git` is the only "tool". |
| `requirements` | Interactive structured choice. Host-capability axis already covered by `core/rules/capabilities/interactive-question.md`. |
| `supervisor` (+ `supervisor-bootstrap`, `supervisor-stages`, `supervisor-retry`) | Internal orchestration. The host-capability axis is its vendor axis and is already factored out via `capabilities.json`. |
| `input-normalizer`, `korean-normalizer` | Pure-text utilities. No tool axis. |
| `analyst`, `planner`, `mentor`, `learning-mentor` | Moderate-fit candidates; not opting in until concrete vendor-axis evidence appears (see `docs/issuer-vendor-skill-layer-dip-review/generalized-dispatcher-primitive.md` § 1 Verdict statement). |
| `test-writer` | Test framework variation is already covered by language skills (`tdd.md`, `effective-*.md`). Skill split would over-engineer. |

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
