# Framework Review Round 2

Date: 2026-05-23

Scope: follow-up review against the AI Agent Framework Review Guideline, focused
on gaps that remained after Round 1 operational readiness checks.

## Findings

1. Agent responsibilities were documented in prose, but there was no
   machine-readable permission manifest tying planner, worker, reviewer,
   resolver, devops, and support agents to explicit capabilities.
2. Reviewer read-only and worker no-recursive-delegation rules depended on
   prompt text. They were not independently checkable by CI or `crew doctor`.
3. Prompt-injection handling existed indirectly through trust and memory rules,
   but there was no single security rule for retrieved/external context as
   untrusted data.
4. Cost-aware routing was implied by `reasoning_tier`, but there was no review
   gate proving that role-level model tiers were not all high-tier.
5. Update/install drift verification did not include policy files, which would
   make future capability policy changes easier to miss.

## Changes

- Added `core/policies/agent-capabilities.json` as the role/capability source
  of truth for core agents and supervisor modules.
- Added `core/schemas/agent-capabilities.schema.json` and
  `core/scripts/agent-capability-check.py` so the manifest can be checked
  without host-specific tools or external dependencies.
- Added `core/rules/prompt-injection-defense.md` to define trust order,
  external-content isolation, and tool-request validation requirements.
- Extended `core/scripts/framework-review-check.py` so `crew doctor` now checks:
  agent capability manifest presence, prompt-injection defense policy, and
  cost-aware role tiers.
- Updated local/remote install paths, runtime auto-refresh, update
  fingerprinting, and drift verification so policy files are copied and checked.
- Added regression tests for capability validation, framework review coverage,
  CLI smoke coverage, runtime sync, and update fingerprint tracking.

## Remaining Work

- Enforce the capability manifest at runtime before each stage agent receives
  tools. Resolved in Round 3 with `pipeline-capability-check.py` and supervisor
  preflight gates.
- Add deterministic replay/golden tool-flow fixtures for end-to-end workflow
  verification.
- Add a memory GC/eviction command that operationalizes the memory lifecycle
  beyond policy and retrieval SLO checks.
