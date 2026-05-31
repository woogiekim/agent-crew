# Issuer Vendor Skill Layer — DIP Review

**Status:** draft, awaiting upstream review
**Branch:** `docs/issuer-vendor-skill-layer-dip-review`
**Last updated:** 2026-05-31
**Owner:** twkim059@cowave.kr

## Problem statement

The `issuer` agent was reshaped in commits #56, #59, and #1f89c02 into a
backend-agnostic dispatcher whose vendor-specific behaviour lives in user-layer
adapter skills (`~/.agent-crew/user/skills/issuer-{adapter}.md`). The Dependency
Inversion intent — system-layer dispatcher depends on the abstract Adapter
Interface Contract, not on Plane / GitHub / GitLab APIs — is structurally in
place but is **leaking abstraction in two ways**:

1. **Concrete vendor literals still appear in the dispatcher's user-facing
   prompts.** `core/agents/issuer.md` mentions `mcp__plane`, `mcp__gitlab`, and
   the CLI `gh` inline in the no-remote and unknown-remote interactive
   resolution options (lines 208, 223–224, 244–245). The dispatcher cannot
   honestly claim adapter-agnostic ownership while the prose names backend
   tools.

2. **Production-proven adapter knowledge is trapped at the user layer.** A
   recent live-E2E pass (shopping repo, `ENRTC-437`, commit `24f9719d8`)
   surfaced four Plane-API quirks and a partial-update discipline pattern
   that the user-layer `issuer-plane.md` skill should encode, but no upstream
   canonical version exists today because the skill file is deliberately
   excluded from the source repo per commit `1f89c02`.

The first leak is a narrow editing fix on a system file. The second leak is a
broader question — does the dispatcher + user-skill pattern generalize beyond
`issuer`, and what framework primitives would unlock that generalization?

## Two findings, intentionally split

| Doc | Scope | Audience | Action |
|---|---|---|---|
| [`issuer-vendor-promotion.md`](./issuer-vendor-promotion.md) | **Narrow** — promote production-proven `issuer-plane.md` content and tighten dispatcher prose in `core/agents/issuer.md`. Single targeted PR. | Reviewers willing to ship in days. | Land as a single additive PR. |
| [`generalized-dispatcher-primitive.md`](./generalized-dispatcher-primitive.md) | **Broad** — formalize the dispatcher + `<agent>-<tool>` skill pattern as a framework primitive for every strong-fit agent (6 strong, 4 moderate, 9 weak). | Reviewers debating framework direction. | Land in waves (A–D) after direction approval. |

The split is deliberate. The narrow doc clears the ship-threshold on its own
evidence (`ENRTC-437` live E2E, 9/9 + 8/9 PASS, 8 spec gaps closed). The broad
doc opens design questions whose resolution should not gate the narrow
promotion.

## Reading order

1. **Start with `issuer-vendor-promotion.md`** for the concrete change set,
   evidence, and ship-threshold call. ~250 lines.
2. **Then `generalized-dispatcher-primitive.md`** for the framework-level case,
   per-agent fit table, common 5-step dispatch protocol, and PR-wave plan.
   ~400 lines.

## Status & next steps

- **Phase 1 (this doc set)** — research findings authored on branch
  `docs/issuer-vendor-skill-layer-dip-review`. Single commit. No remote push.
- **Phase 2** — after upstream review of these findings, file ONE GitHub issue
  on `woogiekim/agent-crew` linking this branch and proposing the PR waves.
- **Phase 3** — open PRs (Wave A → D) once the issue captures direction
  approval.

Local prototype evidence — task `20260531-111840-0` in the shopping repo's
agent-crew state — already implemented the changes against the user-layer
`~/.agent-crew/` source tree. That prototype is not on the source repo; it
served as the validation harness for the proposals contained here.
