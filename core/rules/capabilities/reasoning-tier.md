# reasoning_tier Capability

## Purpose

Each system agent declares the abstract compute tier it benefits from
via the `reasoning_tier` field in its frontmatter. The vocabulary is
provider-neutral — `xhigh`, `deep`, `balanced`, `light` — describing the
character of the work, not a specific model. Host adapters translate
the abstract tier into a concrete model assignment when they install
agent definitions into the host's discovery path. This keeps `core/`
free of any vendor's model identifier (Invariant 3) while still letting
each adapter route an agent's workload to the cost/quality point that
fits the agent's role.

This capability is **install-time only**. There is no `capabilities.json`
flag and no runtime gating. The supervisor and other core consumers do
not consult `reasoning_tier` at execution time — they only ever read
`model:` from the installed agent file, which the adapter has already
materialized.

## Tier vocabulary

The vocabulary is fixed and exhaustive. Adapters MUST recognize all
four tokens; new tokens are introduced via this doc, not invented per
adapter.

| Tier | Use for | Examples |
|---|---|---|
| `xhigh` | Highest-impact semantic decisions where missed defects, bad plans, or incorrect conflict resolution are expensive. Invocation should remain selective; quality dominates cost and latency. | analyst, planner, reviewer, resolver |
| `deep` | Code implementation, orchestration, tests, infrastructure, and recovery decisions that benefit from stronger reasoning but should not always pay the maximum latency/cost. | supervisor, backend, frontend, test-writer, devops |
| `balanced` | Substantive but bounded work within a defined domain. Moderate invocation frequency; quality / cost balanced. | requirements, designer, issuer, learning-mentor |
| `light` | Deterministic, high-volume synthesis or transformation. Quality requirements are modest; cost dominates. | documenter, input-normalizer, korean-normalizer |

## Required Adapter Surface (install-time)

Unlike runtime capabilities, this one has no `capabilities.json` flag.
An adapter implements `reasoning_tier` by performing two install-time
duties:

1. **Tier-to-model mapping table.** The adapter MUST define an internal
   mapping from `{xhigh, deep, balanced, light}` to its host's model
   identifiers. Where the adapter ships this mapping is up to the
   adapter (a constant in `setup.sh`, a separate config file, etc.).
   The mapping MUST be hermetic to the adapter — `core/` MUST NOT see
   any host-specific model name.

2. **Frontmatter materialization.** During `setup.sh`, after the
   adapter has copied agent files into the host's discovery path, the
   adapter MUST walk each installed agent file, read its
   `reasoning_tier` field, look up the corresponding model in the
   mapping table, and rewrite the `model:` line with the resolved
   value. Source files under `core/agents/` MUST be left unchanged
   (they keep `model: inherit`).

Adapters whose host does not support per-agent model assignment MAY
skip step 2; the abstract tier is then ignored and the host's default
model applies to every agent. The adapter SHOULD document this in its
`invocation.md` so operators know the tier declarations have no effect.

## Consumer Contract (core)

Core's only contract is:

- Every spawnable system agent under `core/agents/*.md` SHOULD declare
  a `reasoning_tier` value drawn from the vocabulary above.
- The source file's `model:` field SHOULD remain `model: inherit` so
  the abstract declaration is not shadowed by a concrete identifier.
- Sub-modules read by a parent agent (e.g., `supervisor-bootstrap.md`)
  do NOT need the field unless they become host-discovered standalone agents.

Core code MUST NOT read `reasoning_tier` at runtime. The only consumer
is the adapter's install-time materializer.

## Absence Behavior (no adapter mapping)

When an agent file has no `reasoning_tier`, the adapter MUST default
to `balanced`. Rationale: `balanced` is the safest middle for an
unclassified agent — it neither inflates cost (as `deep` would) nor
risks poor judgment (as `light` would).

User-installed agents under `~/.agent-crew/user/agents/` likely have
no `reasoning_tier`. The adapter SHOULD leave their `model:` line
untouched (treat user agents as "user owns the model choice") rather
than apply the `balanced` default. The materializer is for system
agents only.

## Frontmatter Exemption

Some internal modules may not have YAML frontmatter because they are read by a
parent agent rather than discovered as standalone agents. The materializer MUST
silently skip any file without a frontmatter block. These modules inherit the
host's default model if a host ever discovers them directly.

## Adapter Examples

| Adapter | Mapping | Notes |
|---|---|---|
| claude  | `xhigh → claude-opus-4-7`, `deep → claude-opus-4-7`, `balanced → claude-sonnet-4-6`, `light → claude-haiku-4-5` | Materializer runs after `merge_agents_to_discovery`; rewrites `~/.claude/agents/*.md`. Claude has no separate per-agent effort field, so `xhigh` and `deep` use the strongest configured model. |
| codex   | `xhigh → model_reasoning_effort="xhigh"`, `deep → "high"`, `balanced → "medium"`, `light → "low"` | Codex custom agents support per-agent `model`, `model_reasoning_effort`, `sandbox_mode`, and related config keys. The adapter maps system-agent abstract tiers to reasoning effort, while preserving user-specified concrete model keys. |
| generic | none — single-model environment | Leaves `model: inherit` (or absent equivalent) untouched. Tier declarations have no install-time effect. |

## Related Files

Producer (install-time):

- `adapters/claude/setup.sh` — Claude materializer (rewrites
  `~/.claude/agents/*.md`)
- `adapters/codex/setup.sh` and
  `core/scripts/generate-codex-system-agents.py` — Codex (maps system-agent
  tiers to `model_reasoning_effort`; preserves user-owned concrete model keys)
- `adapters/generic/setup.sh` — no-op

Consumer (none at runtime). The field is purely declarative for
runtime; only the materializer reads it.

Companion docs:

- `core/rules/host-capabilities.md` — Capability Registry index (this
  capability appears with `install-time` in the Status column).
- `docs/cache-tier-convention.md` — separate axis (prompt-cache prefix
  layout); `reasoning_tier` is about model selection, not cache layout.
  The two are independent and additive.

Cross-flag:

- Independent of `cost_tracking`. When both `reasoning_tier` is honored
  and `cost_tracking = true`, a future cost circuit breaker (Phase
  3.3) can weight per-tier cost differently. The two flags do not
  interact at install time.
