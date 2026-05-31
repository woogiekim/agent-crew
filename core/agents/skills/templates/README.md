# Channel B — Adapter Skill Templates

This directory is the framework's **canonical seed source** for adapter
skills used by dispatcher agents (see `core/rules/agent-tool-dispatch.md`).

## Channel B in one sentence

The framework ships canonical seed templates here. On install / update,
`crew:setup` and `crew:update` copy each template into
`~/.agent-crew/user/skills/<name>.md` **only if the user-layer file does
not already exist**. The runtime contract (dispatcher loads from
`~/.agent-crew/user/skills/`) is unchanged.

## Why this layout exists

`commit 1f89c02` removed adapter skills from the source repo to enforce a
user-layer-only policy: production-proven vendor knowledge (Plane
Pydantic quirks, GitHub rate-limit headers, etc.) lives at
`~/.agent-crew/user/skills/<agent>-<tool>.md` and is **never overwritten**
by `crew:update`. That policy is load-bearing.

Two channels were considered for shipping vendor knowledge upstream:

| Channel | Mechanism | Status |
|---|---|---|
| A — docs-as-reference | Skill content lives in `docs/`; users hand-sync into `~/.agent-crew/user/skills/`. | Rejected: defeats the dispatcher's point of loading knowledge into the agent prompt at runtime. |
| **B — reference-template** (this directory) | Skill content lives in `core/agents/skills/templates/`; `crew:setup` / `crew:update` seed into the user layer copy-if-absent. | **Adopted.** Preserves the spirit of user-layer-only (no automatic system→user overrides) while giving the framework a canonical reference. |
| C — auto-merge | Skill content lives in `core/agents/skills/`; install always replaces the user layer. | Rejected: violates `commit 1f89c02`. |

The full design rationale is at
`docs/issuer-vendor-skill-layer-dip-review/issuer-vendor-promotion.md` § 5.1.

## Path catalog

| Path | Purpose | Overwritable? |
|---|---|---|
| `core/agents/skills/templates/<agent>-<tool>.md` | Framework-shipped seed template. Tracked in the source repo. | Yes — by source sync (the framework's canonical copy). |
| `~/.agent-crew/system/agents/skills/templates/<agent>-<tool>.md` | Installed mirror of the source template. | Yes — replaced by `crew:update` from source. |
| `~/.agent-crew/user/skills/<agent>-<tool>.md` | Runtime artifact loaded by the dispatcher. | **NEVER overwritten by `crew:update`.** |
| `~/.agent-crew/skills/<agent>-<tool>.md` | Unified discovery view (system + user, user-wins). Templates are **NOT** merged here. | Refreshed by `merge_skills_to_discovery`. |

## Naming convention

Templates follow the dashed convention defined in
`core/rules/agent-tool-dispatch.md` § Naming convention:

- `<agent>-<tool>.md` — examples: `issuer-plane.md`, `issuer-github.md`,
  `documenter-notion.md`, `devops-fly.md`.
- `<agent>-<lang>-<framework>.md` — examples:
  `backend-kotlin-spring.md`, `frontend-typescript-react.md`.

Subdirectory namespacing is forbidden because the install machinery
(`deploy-user-skill.sh`, `merge_skills_to_discovery`) is a flat-copy
operation.

## When to add a template

A new template belongs here when **all** of the following hold:

1. The agent is a dispatcher (or is migrating to become one — see
   `core/rules/agent-tool-dispatch.md` § Agents subject to dispatch).
2. The vendor knowledge is concrete enough to be useful (API quirks,
   error-handling tables, request-shape examples), not just a heading
   stub.
3. The knowledge is reasonably stable (the underlying vendor API changes
   slowly enough that the template can stay current with quarterly
   refreshes).
4. The knowledge has been validated against a real backing service —
   per the project rule "live E2E is the bar, not mock slices".

If any of these conditions are absent, prefer keeping the file in your
own `~/.agent-crew/user/skills/` until it earns the upstream promotion.

## How to add a template

1. Create `core/agents/skills/templates/<agent>-<tool>.md` following the
   adapter interface contract of the relevant dispatcher agent.
   For `issuer`, see `core/agents/issuer.md` § Adapter Interface Contract.
2. Commit the file. The next `crew:update` on user machines will
   install it under `~/.agent-crew/system/agents/skills/templates/` and
   (if the user layer is empty for that name) seed it into
   `~/.agent-crew/user/skills/`.
3. NEVER edit `~/.agent-crew/user/skills/<name>.md` from the framework
   side. That layer belongs to the user. Use `crew:update
   --reconcile-skills` if you need to surface template changes to users
   who already customized their copy.

## What does NOT belong here

- `SKILL-TEMPLATE.md`-style structural stubs. Those live one level up at
  `core/agents/skills/SKILL-TEMPLATE.md` and are documentation, not
  seed material. The seed helper explicitly skips files named
  `README.md` and `SKILL-TEMPLATE.md`.
- System-level skills (`tdd.md`, `api-design.md`, `effective-*.md`).
  Those are agent-declared and merged into the unified discovery view
  via the normal `sync_system_skills` + `merge_skills_to_discovery`
  path. Templates are convention-discovered, not declared.
- Wave-B / Wave-C exemplar adapters. Concrete `issuer-plane.md`,
  `backend-kotlin-spring.md`, etc. land via the wave-specific PRs the
  research docs describe. This Wave-A run ships only the **primitive**:
  the directory, the README, and the install/update plumbing.

## See also

- `core/rules/agent-tool-dispatch.md` — the dispatcher contract that consumes these templates.
- `core/setup/seed-skill-templates.sh` — install/update copy-if-absent helper.
- `core/setup/reconcile-skill-templates.sh` — opt-in diff helper for divergence detection.
- `core/commands/setup.md` § Skill Template Seeding — install integration.
- `core/commands/update.md` § Skill Template Reconcile — update integration.
- `docs/issuer-vendor-skill-layer-dip-review/issuer-vendor-promotion.md` § 5.1 — the Channel B design sketch.
- `docs/issuer-vendor-skill-layer-dip-review/generalized-dispatcher-primitive.md` § 5 — framework-primitives discussion.
