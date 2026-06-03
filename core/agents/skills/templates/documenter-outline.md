---
name: documenter-outline
description: >
  Adapter skill for the `documenter` dispatcher (Wave C exemplar). Loaded when
  the dispatcher detects an Outline output-target axis (env vars, project
  state file, or interactive resolution). Captures the canonical
  documentation-output contract that `core/agents/documenter.md` already
  documents (result.md + side-car README / CHANGELOG + page-out hygiene),
  packaged as a Channel B seed template per
  `core/rules/agent-tool-dispatch.md`. The Outline-specific surface is a
  marked seed point — adopters extend it in their own user-layer copy.
loaded_by: documenter
axis: outline
detection: |
  ~/.agent-crew/state/{PROJECT}/docs/outline.json exists OR
  OUTLINE_TEAM_ID / OUTLINE_API_TOKEN env vars set
---

# documenter-outline — Adapter Skill (Seed Template)

This skill is the **Channel B seed template** for the `documenter`
dispatcher when the detected output-target axis is `outline`. It is a
**faithful re-package** of the canonical documentation-output contract
that `core/agents/documenter.md` documents today — the default
`{TASK_DIR}/result.md`, the side-car README / CHANGELOG drafts under
`~/.agent-crew/state/{PROJECT}/docs/`, and the working-set page-out
discipline.

> **Honest seed-point disclaimer.** This template is intentionally thin
> on Outline-specific vendor knowledge. The framework refuses to ship
> fabricated API specifics (concrete endpoint paths, auth header
> formats, document/collection ID shapes) because `documenter.md`
> itself never specified them — see `core/rules/agent-tool-dispatch.md`
> § Channel B template seeding. The default-output contract below is
> the faithful coverage of what documenter.md says; everything in the
> "Outline-specific surface" section is an honest **seed point** /
> **extension point** marked for the adopter to fill in. After
> `crew:setup` / `crew:update` seeds this file copy-if-absent into
> `~/.agent-crew/user/skills/documenter-outline.md`, the adopter
> extends the seed point in their own user-layer copy — the framework
> never overwrites a user-edited file (commit `1f89c02`).

## What this skill covers faithfully

The dispatcher loads this skill on Outline-axis runs. Three faithful
contracts are documented below, every line traceable back to
`core/agents/documenter.md`:

1. **Canonical default output** — `{TASK_DIR}/result.md`.
2. **Side-car drafts** — README / CHANGELOG patches under
   `~/.agent-crew/state/{PROJECT}/docs/`.
3. **Page-Out hygiene** — stage `*.tmp` / `*.draft` files moved to
   `{TASK_DIR}/archive/`. (Page-Out Mode itself — `handoff.md`
   compaction — is supervisor-internal and is NOT part of this
   adapter's surface; see documenter.md § Page-Out Mode.)

## Default-output contract (faithful to documenter.md)

### Canonical `{TASK_DIR}/result.md`

Always written, regardless of whether an external backend skill is
loaded. Verbatim shape from documenter.md Step 2:

```markdown
# Result — {task title from prd.md}

## Summary
{1-2 sentence outcome derived from review.md verdict + analysis intent}

## Status
{COMPLETED | NEEDS_CHANGES | BLOCKED} — {reason}

## As-Is / To-Be

| Area | As-Is | To-Be |
|---|---|---|
| {component} | {prior behavior} | {new behavior} |

## Changes
- {one bullet per logical change, derived from git log + stage handoffs}

## Verification
- Review status: {APPROVED | NEEDS_CHANGES from review.md}
- Tests: {pass count or "no test changes"}
- Acceptance criteria: {N of M from prd.md satisfied}

## Artifacts
- PRD: `{TASK_DIR}/context/prd.md`
- Analysis: `{TASK_DIR}/context/analysis.md`
- Review: `{TASK_DIR}/context/review.md`
- Branch: `{BRANCH}`
```

### Side-car README patch

Written to `~/.agent-crew/state/{PROJECT}/docs/readme-patch-{TASK_ID}.md`.
Documenter does NOT modify `{PROJECT_ROOT}/README.md` in auto mode.
Verbatim patch-body shape from documenter.md Step 3:

```markdown
# Proposed README patch — {TASK_ID}

## Target section
{detected section heading in README that this change affects, or "(new section)"}

## Proposed insert/update
{markdown block ready to splice into README}

## Apply with
crew:doc --to-readme --task {TASK_ID}
```

If no README section appears to need an update, skip and note
"No README impact" in `result.md`.

### Side-car CHANGELOG entry

Written to `~/.agent-crew/state/{PROJECT}/docs/changelog-entry-{TASK_ID}.md`.
Keepachangelog-style. Verbatim body shape from documenter.md Step 4:

```markdown
## [Unreleased] — derived from {BRANCH}

### {Added|Changed|Fixed|Removed}
- {one-line summary} ({TASK_ID})
```

### Working-set page-out

Stage-original `*.tmp` / `*.draft` files are moved (not copied) to
`{TASK_DIR}/archive/`. Verbatim discipline from documenter.md Step 5 —
"keep the working set small so future invocations of `crew:status` and
resumed sessions only see canonical files at the top level".

## Supplementary Writing Guideline — Plain Lead + Developer Details

This guideline mirrors the core `documenter` dispatcher and is supplementary.
The canonical `result.md` shape, side-car README patch shape, CHANGELOG entry
shape, page-out discipline, and Outline seed-point disclaimer remain
authoritative. Apply the rule below inside generated prose without changing
those base formats.

1. **Plain-language summary first.** Lead documentation with short,
   outcome-focused sentences that any non-technical reader can understand
   without repository context. Avoid file paths, code identifiers, class or
   function names, command lines, branch names, schema names, and internal
   implementation jargon in the lead section.
2. **Developer details are separate.** Move engineer-only details into a
   clearly separated developer-detail subsection. The recommended heading is
   `구현 메모(개발자용)`; an equivalent heading such as
   `Implementation notes for developers` is acceptable when the document's base
   language or format calls for it.
3. **No audience-role labels for the plain summary.** A developer-detail
   separator is allowed because it describes the content type. Do not label the
   plain-language lead with role-targeting audience labels such as
   `기획자용`, `기획자 요약`, `for planners`, `for designers`, or similar
   role-specific labels.

Recommended structure inside generated documentation:

```markdown
## Summary
This change explains the completed outcome before any implementation detail.

## 구현 메모(개발자용)
- Changed `path/to/file.ext` and verified with `command --flag`.
```

## Outline-specific surface (seed point — extend in user layer)

> **The block below is a seed point.** None of these placeholders are
> derived from `documenter.md` (which deliberately documents only the
> side-car default — see Absolute Rules). Replace each `TODO` with the
> Outline-specific contract that fits your team's installation.

### Backend coordinates (TODO — adopter)

```text
OUTLINE_BASE_URL:   {TODO — your Outline instance, e.g. https://docs.example.com}
OUTLINE_TEAM_ID:    {TODO — Outline team / workspace ID}
OUTLINE_AUTH:       {TODO — API token resolution strategy (env var, vault, etc.)}
TARGET_COLLECTION:  {TODO — collection ID or slug where task documents land}
PARENT_DOCUMENT:    {TODO — optional parent doc ID for hierarchical scoping}
```

### Push contract (TODO — adopter)

The adopter MUST document, in this file, the answers to:

- **Idempotency.** Does the push update by title, by stable
  external-ID stored in document metadata, or always create a new
  document per `{TASK_ID}`? Documenter has no opinion; the seed point
  is honest about that.
- **Source-of-truth direction.** When `{TASK_DIR}/result.md` and the
  Outline document diverge, which one wins on the next sync? (The
  framework's default is "result.md wins" but this is per-team policy.)
- **Page-vs-document mapping.** Is each task a separate Outline
  document, or a heading within a per-week / per-sprint summary
  document?
- **Failure mode.** If the Outline API call fails after the side-car
  draft is already written, the dispatcher's degraded-fallback policy
  applies — the side-car draft is the canonical record and the agent
  does NOT retry the external push synchronously. (This is consistent
  with documenter.md's overall safety stance; the adopter MAY override
  for their own setup.)

### Tool dispatch (TODO — adopter)

The adopter chooses how to drive Outline from this skill:

- **Direct REST** — `curl` against the Outline API; auth header / body
  shape lives entirely in this user-layer skill.
- **MCP server** — if the host installs an Outline MCP adapter (e.g.
  `mcp__outline__*`), the adapter calls go here. This file is the
  ONLY place where vendor literals are permitted (per
  `agent-tool-dispatch.md` § Step 5 invariant — dispatcher prose stays
  vendor-agnostic).

> **Faithfulness rule.** Anything you add to this seed point lives in
> YOUR user-layer copy (`~/.agent-crew/user/skills/documenter-outline.md`),
> never in this framework-shipped template. The framework re-syncs this
> file with `crew:update` copy-if-absent semantics; your edits are
> preserved per commit `1f89c02`.

## Output Contract (faithful re-package)

Verbatim from documenter.md § Output Contract; the rightmost column is
the adapter-aware override. When the Outline adapter is loaded, the
side-car drafts are also pushed to Outline per the adopter's TODO
contract above. When the adapter is NOT loaded, the dispatcher's
degraded-fallback policy keeps everything below working at side-car
fidelity:

| Artifact | Location | Outline-adapter behavior |
|---|---|---|
| Canonical result summary | `{TASK_DIR}/result.md` | Pushed as the master document (TODO — adopter chooses idempotency) |
| Side-car README patch | `~/.agent-crew/state/{PROJECT}/docs/readme-patch-{TASK_ID}.md` | Drafted side-car AND mirrored to Outline (TODO — adopter chooses target heading) |
| Side-car CHANGELOG entry | `~/.agent-crew/state/{PROJECT}/docs/changelog-entry-{TASK_ID}.md` | Drafted side-car AND appended to per-release Outline doc (TODO — adopter chooses parent doc) |
| Archived stage files (`*.tmp` / `*.draft`) | `{TASK_DIR}/archive/` | Local-only — never pushed |

## Absolute rules (inherited verbatim from documenter.md)

This skill cannot relax any of the dispatcher's absolute rules. The
load-bearing invariants from documenter.md § Absolute Rules apply
unchanged when this skill is loaded:

- **NEVER** modify repo-tracked files in default (`auto`) mode.
  `--to-readme` mode still requires both the explicit flag AND the
  structured user-choice approval gate.
- **NEVER** insert code comments into implementation files.
- **NEVER** author new PRDs or design docs.
- `MODE=page-out` is supervisor-only and does NOT touch this skill —
  Page-Out Mode is supervisor-internal handoff compaction, not part of
  the output-target dispatch.

## See also

- `core/agents/documenter.md` — the dispatcher that loads this skill
  when the outline axis is resolved. The default-output contract above
  is a faithful re-package of its Steps 1–5.
- `core/rules/agent-tool-dispatch.md` — the 5-step dispatch protocol,
  naming convention, fallback-policy taxonomy, and Channel B template
  seeding contract.
- `core/setup/seed-skill-templates.sh` — the copy-if-absent seed helper
  that ships this template into `~/.agent-crew/user/skills/`.
- `core/setup/reconcile-skill-templates.sh` — the opt-in advisory diff
  helper for adopters who hand-merge template updates.
