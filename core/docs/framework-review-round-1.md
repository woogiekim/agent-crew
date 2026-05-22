# Framework Review Round 1

Date: 2026-05-23

Scope: agent-crew framework review against architecture, performance, quality,
reliability, memory governance, security, observability, cost efficiency,
developer experience, and long-term scalability.

## Findings

### Resolved in this round

1. Security policy did not explicitly deny `sudo`, force push, or credential
   access.
   - Impact: approval-gated commands were covered, but some high-risk command
     classes were not represented as non-approvable policy violations.
   - Resolution: added forbidden command policy paths for `sudo`, force push,
     and common credential access commands/files.

2. Native CLI did not expose the existing cost aggregator as `crew cost`.
   - Impact: cost observability existed in scripts and docs, but shell users had
     no deterministic native entrypoint.
   - Resolution: added `crew cost` and wired it to `cost-aggregate.py`.

3. Operational readiness review criteria were not executable.
   - Impact: architecture/security/memory/cost controls could regress without a
     single review gate.
   - Resolution: added `framework-review-check.py` and `crew doctor`.

4. Memory governance lifecycle was implicit across scripts and fixtures.
   - Impact: retrieval evaluation existed, but the lifecycle and trust
     separation policy were not documented as a reusable rule.
   - Resolution: added `core/rules/memory-governance.md`.

### Remaining watch items

- Capability sandboxing is still primarily policy/hook driven. A future round
  should add per-agent machine-readable tool capability manifests.
- Retrieval scoring has fast-path reranking and regression fixtures, but not a
  standalone GC/eviction command yet.
- Deterministic replay is partially covered by fake-host and state-schema tests;
  a golden tool-flow replay fixture would improve release confidence.

## Verification

- `framework-review-check.py`: 19 controls passed, 0 failed.
- Focused tests passed:
  - `tests/python/test_framework_review_check.py`
  - `tests/shell/test_crew_cli.bash`
  - `tests/shell/test_guard_dangerous_commands.bash`
  - `tests/integration/test_cli_smokes.bash`
