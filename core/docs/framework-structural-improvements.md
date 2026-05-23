# Framework Structural Improvements

Date: 2026-05-23

Scope: follow-up work after Framework Review Round 4, focused on the remaining
memory lifecycle and custom-agent capability-profile gaps.

## Changes

- Added `memory gc` through `core/scripts/memory-gc.py`.
  - Dry-run is the default.
  - `--apply` archives selected candidate metadata to JSONL.
  - Eviction writes an agent-crew local `evicted-ids.txt` list.
  - Fast memory search skips evicted IDs without deleting the mnemos vault.
- Added custom-agent capability profiles to
  `core/policies/agent-capabilities.json`.
  - `custom-worker` is the safe default.
  - `custom-readonly` supports explicit read-only user agents.
  - `custom-devops-approved` supports approval-gated custom DevOps agents.
- Extended pipeline capability preflight so dynamic and existing custom agents
  can declare `capability_profile`, while unsafe or unknown profiles fail
  before runtime execution.
- Extended `crew doctor` controls for memory GC/eviction and custom capability
  profiles.

## Operational Notes

- `memory gc --format json` is safe for regular diagnostics.
- `memory gc --apply --format json` does not delete backend memory; it archives
  metadata and removes selected IDs from agent-crew fast retrieval.
- Existing custom agents without a profile continue to use the safe
  `custom-worker` default.
- Destructive-looking custom agents, such as release or deploy agents, require
  an explicit approved profile and reviewer follow-up.
