# core/scripts/ — Provider-Neutral Helpers

Helpers that core code and host adapters can invoke without knowing
anything about the calling host. This directory is the canonical home
for **provider-neutral logic** that was previously inlined into host
hooks, agent prose, or `run.md` shell blocks.

## Contract

Every script under `core/scripts/` MUST satisfy:

1. **Stdin / stdout / exit code only.** No host-specific environment
   variables (e.g., `${HOOK_INPUT}` JSON shape) referenced directly. If
   structured input is needed, define it explicitly at the top of the
   script and document the JSON shape.
2. **No host-tool calls.** Never invoke any host-specific tool name
   directly (e.g., a host's native question, task-create, or background-spawn
   tools). Use the abstract capability intents documented under
   `core/rules/capabilities/`. The script computes a fact; the caller
   decides what to do with it.
3. **Idempotent and side-effect-minimal.** Read files, classify input,
   emit a result. Scripts that intentionally mutate state must be named as
   operational tools (`repair-*`, `update-*`) and document the exact files
   they write. Validators and classifiers must not mutate pipeline state.
4. **Fail loudly.** Exit codes:
   - `0` — success / "ok"
   - `1` — soft failure (e.g., pattern not matched, threshold not
     exceeded). Caller decides if this is an error.
   - `2` — hard failure (malformed input, unreachable dependency).
     Caller should escalate.
5. **Self-documented.** First 20 lines explain: purpose, inputs,
   outputs, exit-code semantics, example invocation.
6. **Language choice:**
   - Bash (`.sh`) for simple text classification and file checks.
   - Python (`.py`) for anything with structured input/output, JSON
     parsing, or non-trivial logic. Python 3 only; no external deps
     unless agreed in the relevant capability doc.

## Why this directory exists

Two of the Three Invariants in
`core/rules/host-capabilities.md` are enforced here:

- **Invariant 1** (no direct host-tool calls): provider-neutral logic
  lives here so adapters can wire it into their hook mechanisms without
  re-implementing the logic per host.
- **Invariant 3** (no host-tool names in core/): when core needs to do
  something that could conceivably be done with a host-specific tool,
  the algorithm goes here as a script; the adapter decides how to
  invoke it.

## How adapters wire these in

| Adapter | Wiring mechanism |
|---|---|
| claude  | Hook scripts under `core/hooks/*.sh` call these scripts. `adapters/claude/setup.sh` registers the hooks via `settings.json`. |
| codex   | `adapters/codex/skill/agent-crew/SKILL.md` instructs the model to invoke specific scripts at specific lifecycle moments. |
| generic | `adapters/generic/invocation.md` documents the same expectations as guidance; the model invokes them best-effort. |

The capability `hook_system` (see `core/rules/capabilities/hook-system.md`)
gates whether hook-based enforcement is strict or advisory; the scripts
themselves are the same code either way.

## Planned scripts

These scripts are referenced by various capability docs but introduced
in later refactor phases. They do not exist yet — listing them here
documents the planned surface so adapter authors can prepare.

| Script | Phase | Purpose | Referenced by |
|---|---|---|---|
| `classify-trivial-intent.sh` | 0 | Decide whether an input matches one of the 7 trivial operations (merge, push, deploy, tag, rollback, status, commit_only) | `core/commands/run.md` |
| `check-task-injection.py` | 14 | Mid-injection duplicate disambiguation prompt (Step 1.6 already does dup detection via inline Python; this script would extend with merge/queue/cancel options) | `core/rules/capabilities/hook-system.md` |
| `cost-aggregate.py` | E3.3 | Aggregate per-call token data into a per-task / crew-wide summary | `core/commands/cost.md`, `core/rules/capabilities/cost-tracking.md` |
| ~~`handoff-page-out.py`~~ | superseded by Phase 3.5 | Auto-summarize `handoff.md` when it exceeds a threshold (opt-in) — **now implemented via the documenter agent in `MODE=page-out`, not a standalone script**. See `core/agents/documenter.md` § Page-Out Mode and `core/agents/supervisor-stages.md` § Post-stage handoff page-out. | `core/rules/quality-loop.md` § Page-Out As Hygiene Operation |

Each script's introduction PR also adds a corresponding entry in the
relevant adapter (Claude wires it as a hook; Codex documents the
invocation in SKILL.md; generic adds guidance).

## Diagnostic tooling

- `smoke-test-state.sh` — end-to-end regression test for the F4
  validator + F5 progress buffer + G6 plain-text-approval validator +
  J13 telemetry aggregator. Pure read-only against the repo; writes
  only into a temp directory. Run `bash core/scripts/smoke-test-state.sh`
  from the repo root after changing any of these subsystems.
- `mnemos-bounded.sh` — wraps `mnemos` foreground commands with a portable hard
  timeout. Use this from Codex/manual recall paths when memory lookup should be
  visible but non-blocking.
- `bench-parallel.sh` — token-free dry-run benchmark for stage fan-out widths,
  N = 1/2/4/8 task-cardinality scenarios, and Phase 1d prefetch cleanup.
- `verify-update-dry-run.sh` — non-mutating update verifier that runs the local
  update flow against temporary install homes and a temporary project, then
  checks stale-file pruning, canonical Codex TOMLs, and user asset preservation.
- `e2e-slo-check.py` — CI-ready latency/noise SLO checker for status,
  telemetry, memory search, retrieval evaluation, and update dry-run budgets.
- `memory-gc.py` — dry-run-first memory lifecycle GC. It reads the mnemos FTS
  index, classifies duplicate/stale/low-value candidates, scores trust, archives
  selected metadata, and writes an agent-crew eviction list used by fast memory
  search without deleting the underlying vault.
- `framework-review-check.py` — static operational readiness gate for
  architecture, performance, quality, reliability, memory governance, security,
  observability, cost efficiency, developer experience, and long-term
  scalability controls. The native `crew doctor` command runs this check.
- `claude-performance-check.py` — checks Claude adapter asset-size, file-count,
  largest-agent, and hook-timeout budgets so Claude slowness is diagnosable
  from host diagnostics instead of anecdotal observation.
- `check-host-bridge.py` — validates an optional external
  `AGENT_CREW_HOST_BRIDGE_COMMAND` for shell-token parseability and executable
  discoverability/permissions. Missing external bridge configuration is a soft
  notice because `crew run` records `handoff_ready` through the internal
  fallback. `crew doctor` includes this probe in host diagnostics.
- `agent-capability-check.py` — validates the machine-readable
  `core/policies/agent-capabilities.json` manifest against agent markdown files,
  role boundaries, destructive-operation approval requirements, reviewer
  read-only constraints, and cost-aware model tier distribution.
- `pipeline-capability-check.py` — validates a planned `pipeline.json` against
  the capability manifest before runtime execution. It blocks recursive
  delegation agents, workflow-state mutation agents, unsafe reviewer/devops
  stage shapes, unknown agents without custom-agent files or `needs_creation`,
  custom capability-profile violations, and custom agents whose names imply
  destructive authority without an explicit approved profile.
- `workflow-replay-check.py` — replays golden workflow fixtures against local
  validators and expected state transitions. It verifies deterministic tool
  flow for schema validation, quality planning, capability preflight, blocked
  outcomes, and happy-path completion without calling an LLM.
- `validate-state-schema.py` — validates project/task state artifacts and
  schema-validates optional reviewer quality labels at
  `{TASK_DIR}/context/quality-metrics.json` when present.
- `retry-chaos-check.py` — replays deterministic retry-chaos fixtures without
  an LLM. It simulates token-limit resumes, host tool crashes, reviewer
  loop-back, quality-loop exhaustion, and host blocked/cancelled outcomes
  against explicit retry budgets.
- `telemetry-taxonomy-check.py` — correlates live `progress.buffer.jsonl`
  retry/blocker labels with the retry-chaos fixture taxonomy. It rejects
  unknown explicit retry reasons and can require specific labels for focused
  production-run validation.
- `telemetry-aggregate.py` — aggregates task status, retry, token, tool, phase,
  stale-state, and operational quality metrics including success rate, retry
  rate, hallucination-signal rate, rollback frequency, and human-intervention
  rate. When `{TASK_DIR}/context/quality-metrics.json` exists, evaluator labels
  take precedence over weaker task/blocker text-signal fallbacks.
- `auto-issue-reporter.py` — native reporting engine for explicit agent-crew
  bug/error reports. It detects narrow agent-crew + error signals, redacts
  common secrets, deduplicates locally, stores reports in the local outbox, and
  supports optional GitHub publication through `crew report publish`.
- `update-slo-benchmark.py` — benchmarks no-op local, cold local, and remote
  `crew update` modes against explicit latency budgets and phase timings.
- `memory-evidence-trace.py` — writes `context/memory-evidence.{json,md}` so
  reports can prove which memory IDs and evidence paths were reused; it can
  fold `memory-retrieval-eval.py --format json` output into accepted-context,
  successor-memory feedback, and compact memory-quality metrics.
- `repair-task-state.py` — explicit operational repair for manual handoff
  fallback completion; rewrites the task's terminal state and archives the
  pre-repair `result.md`. Completed repairs for mutating implementation tasks
  require TDD/test evidence, reviewer evidence, and pipeline-level quality-loop
  events, or an explicit quality bypass reason.
- `pipeline-quality-plan-check.py` — validates `pipeline.json` immediately after
  analyst/planner emission. Mutating implementation stages must be encoded as
  TDD-capable stages and followed by a reviewer stage; every TDD stage must
  contain exactly one code implementer and be followed immediately by a solo
  reviewer stage, so multi-agent or batched code stages must be split and each
  implementer gets its own TDD + review loop.
- `quality-loop-check.py` — validates that completed mutating implementation
  tasks have a TDD-capable implementation stage, a later reviewer stage,
  implementer/TDD completion events, reviewer approval, and rework/re-review
  after any reviewer rejection. Rework evidence must be a later attempt on the
  rejected reviewer's immediately preceding implementation stage, followed by a
  later reviewer re-approval. The native `crew run` runtime uses this check
  before allowing mutating fake-host or host-bridge auto-completion.
- `reviewer-loop-decision.py` — classifies reviewer output for the supervisor
  retry loop. Both `STATUS: REJECTED` and `REVIEW: NEEDS_CHANGES` return
  `action=retry`; `REVIEW: APPROVED` returns `action=approve`.
- `cleanup-host-bridge-blockers.py` — dry-run/apply cleanup for stale
  `host_bridge_not_invoked` tasks that were already handled through manual
  fallback, keeping current telemetry from being dominated by old blockers.
- `update-preservation-manifest.py` — writes before/after update manifests
  under state to prove user-owned agents, skills, protected project Codex
  agents, and settings were not silently deleted or changed.
- `update-fingerprint.py` — records source, user, and generated-output hashes so
  repeated no-op local updates can skip expensive adapter refreshes safely, and
  reports changed fingerprint categories when a full refresh is required.
- `verify-install-drift.py` — post-update source/install drift verifier for
  source-owned commands, hooks, scripts, evaluations, policies, and binary
  entrypoints.

## Naming conventions

- Use kebab-case: `check-plaintext-approval.py`, not `check_plaintext_approval.py`.
- Prefix by category when helpful:
  - `check-*` for validators (return 0 = ok, 1 = violation)
  - `detect-*` for classifiers (return matched category or "none")
  - `classify-*` for intent classifiers (return one of N enum values)
  - `validate-*` for structural validators (return 0 = valid, 2 = invalid)
  - `aggregate-*` for collectors (emit JSON on stdout)
  - `cost-*` for cost-tracking (emit JSON on stdout)

## Related files

- `core/rules/host-capabilities.md` — capability registry and the Three Invariants
- `core/rules/capabilities/hook-system.md` — the capability that primarily wires these scripts
- `core/hooks/` — Claude-specific hook scripts; many of them will become thin wrappers around scripts in this directory as later refactor phases proceed
