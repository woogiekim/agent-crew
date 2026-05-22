# Framework Review Round 3

Date: 2026-05-23

Scope: follow-up review against the AI Agent Framework Review Guideline, focused
on converting Round 2's static capability governance into runtime pipeline
preflight enforcement.

## Findings

1. Round 2 added a machine-readable capability manifest, but runtime stage
   execution still relied on planner prompt discipline to avoid unsafe stage
   shapes.
2. A malformed or externally edited `pipeline.json` could put a delegating
   agent, supervisor component, reviewer mixed with implementers, or non-solo
   devops stage into the runtime stage loop.
3. Existing custom agents need to remain usable, but unknown or newly planned
   agents need a deterministic policy boundary so they do not silently acquire
   destructive authority.
4. Resume paths need the same preflight as fresh planning. Otherwise an invalid
   persisted pipeline could bypass the Phase 1 planning checks and jump directly
   to Phase 2.

## Changes

- Added `core/scripts/pipeline-capability-check.py`, a provider-neutral
  preflight validator for planned runtime stages.
- Added supervisor Phase 1b and resume-path capability gates that block
  invalid pipelines before any stage agent receives tools.
- Extended `crew doctor` readiness checks with
  `architecture.pipeline_capability_preflight`.
- Extended runtime auto-refresh and smoke tests so the new checker is installed
  with other runtime scripts.
- Added regression tests for delegating-agent rejection, reviewer/devops stage
  shape enforcement, planned dynamic agents, existing custom agents, unknown
  agents, and custom destructive-name blocking.

## Remaining Work

- Add deterministic replay/golden tool-flow fixtures for full workflow
  reproducibility.
- Add a memory GC/eviction command that operationalizes the memory lifecycle
  beyond policy and retrieval SLO checks.
- Consider a richer custom-agent capability declaration format so user-owned
  agents can opt into explicit non-default capability profiles.
