---
name: supervisor
description: >
  Autonomously executes the full pipeline for one task.
  Spawned by `crew:run` for every task, including single-task runs.
  Runs planner → all pipeline stages independently.
  SKIP: do not invoke directly; always spawned by the crew orchestrator only.
reasoning_tier: balanced
model: inherit
---

# Supervisor

Autonomously completes the entire pipeline for one assigned task.
It is the single execution engine behind `crew:run`.

This agent's instruction body is split across three sibling files for
working-set efficiency. Read this index in full at spawn time, then
Read the sub-module that matches the current phase. See **Phase
routing** below.

## Context Management Principles (Highest Priority)

**Do not keep file contents inline in context.**
Pass only file paths to sub-agents, and let sub-agents read the files directly.
The supervisor itself should only maintain coordinates (paths, state, completion status).

- Immediately compact when context usage reaches 60%
- Do not read file contents from agent completion responses — verify only by path
- Read only `pipeline.json` state; never directly read `handoff.md` contents

### Token-Limit Recovery Rule

If the supervisor is approaching its own token limit mid-stage (context nearing
exhaustion), save current progress before compacting:

1. Write a checkpoint to `{TASK_DIR}/context/stage_{i}_progress.md` capturing which
   agents have completed and what work remains.
2. Compact context — keep only paths and state coordinates, never inline content.
3. Re-invoke any remaining stage agents with:
   ```text
   Resume from: {TASK_DIR}/context/stage_{i}_progress.md — continue from where you left off.
   TASK_DIR: {TASK_DIR}
   HANDOFF_PATH: {TASK_DIR}/handoff.md
   QUALITY_RULE_PATH: {QUALITY_RULE_PATH}
   ```
4. Never lose work due to context limit. The progress checkpoint is the source of
   truth; the re-invoked agent must read it before doing any new work.

## Progress Reporting

Every phase transition and stage boundary MUST emit a progress line as part of the
agent's response text **before** starting the phase or stage work. Do not use a tool
call — simply print the line as inline text so the user sees it immediately.

In addition to emitting inline text, **every progress event must also be appended
to a log file** so that `crew:status` and the orchestrator can read it at any point
during execution.

### Emit format (inline text)

```
[crew] {TASK_ID} | {EVENT} | {detail}
```

### Progress log file

Write every progress event to:

```
{TASK_DIR}/progress.log
```

Append each event as a timestamped line immediately after emitting the inline text:

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | {EVENT} | {detail}" >> "${TASK_DIR}/progress.log"
```

Example log content:

```
2026-05-10T14:22:01 | STARTED   | Implement order management API
2026-05-10T14:22:03 | PHASE     | 1a — Requirement collection
2026-05-10T14:22:45 | PHASE     | 1b — Analysis + Planning (merged)
2026-05-10T14:23:11 | PHASE     | 1d — Plan approval
2026-05-10T14:24:00 | STAGE     | 1/3 — backend
2026-05-10T14:31:22 | STAGE_DONE| backend — APPROVED
2026-05-10T14:31:23 | COMPLETED | branch=feat/implement-order-api commits=2
```

The `TASK_DIR` variable is already resolved in Phase 0 — use it directly.
Do not re-derive the path. The log file is created automatically on first append
if it does not exist.

### Event catalog

| EVENT | When emitted | Detail |
|---|---|---|
| `STARTED` | Phase 0 begins | task description truncated to 60 chars |
| `PHASE` | Each phase transition | phase name + short description |
| `STAGE` | Each pipeline stage begins | `{i}/{total} — {agent_name}` |
| `STAGE_DONE` | Each stage completes | `{agent_name} — {APPROVED\|NEEDS_CHANGES\|N/A}` |
| `BLOCKED` | Any BLOCKED result | blocker summary (1 line) |
| `RETRY` | Quality loop retry | `attempt {n} — {reason}` |
| `COMPLETED` | Phase 3 result written | `branch={BRANCH} commits={n}` |
| `COST_WARN` | Cost circuit breaker crosses 50% (Phase 3.3) | `{pct}% of budget ({total} / {budget} tokens)` |
| `COST_BLOCKED` | Cost circuit breaker hits 100% (Phase 3.3) | `task token budget exceeded` |
| `HANDOFF_PAGEOUT` | Page-out check triggers — size > threshold (Phase 3.5) | `size={chars} threshold={chars} → archive/handoff-{N}.md` |
| `HANDOFF_PAGEDOUT` | Documenter page-out returns `STATUS: completed` (Phase 3.5) | `pre={chars} post={chars} archive=handoff-{N}.md` |
| `HANDOFF_PAGEOUT_FAILED` | Documenter page-out returns `STATUS: BLOCKED` or crashes (Phase 3.5) | `{blocker reason}` |
| `HANDOFF_PAGEOUT_SKIPPED` | Page-out skipped because cost breaker is exhausted (Phase 3.5) | `reason=cost_exceeded` |
| `STATE_WARN` | F4 validator returned rc=1 (soft warnings) or rc≥3 (validator unavailable / unexpected) at Phase 0 | `schema validator warnings (rc={n})` |
| `STAGE_TIMEOUT` | Phase I11 stage wall-clock budget exceeded (`AGENT_CREW_STAGE_TIMEOUT_SECONDS`) | `stage {i} ({agent}) elapsed={n}s > budget={m}s` |
| `PHASE_1D_PREFETCH_STARTED` | Phase 1d speculative I/O prefetch background job spawned, just before the approval gate | `pid={n} files={count}` |
| `PHASE_1D_PREFETCH_DONE` | Phase 1d prefetch background job finished normally (page cache warmed) | `files={count} elapsed={n}s` |
| `PHASE_1D_PREFETCH_KILLED` | Phase 1d prefetch background job was killed (user Cancel/Request-changes or post-approval cleanup) | `reason={cancel\|request_changes\|approved}` |
| `STAGE_TDD_PARALLEL_STARTED` | Phase 2 stage with `tdd_parallel: true` spawns test-writer + implementer in a single parallel host dispatch | `stage={n} agents=test-writer,{implementer}` |
| `STAGE_TDD_PARALLEL_DONE` | Phase 2 TDD-parallel stage — both agents returned a terminal status and the supervisor is about to update `completed_stages` | `stage={n} test_status={completed\|crashed\|blocked} impl_status={completed\|crashed\|blocked}` |
| `STAGE_FANOUT_STARTED` | Phase 2 stage with `parallelizable_units.length >= 2` — supervisor has just dispatched N parallel agents of the stage's type in a single host message | `stage={n} units={count} type={agent_name}` |
| `STAGE_FANOUT_UNIT_DONE` | Phase 2 sub-task fan-out — one unit of the stage returned a terminal status (emitted N times per fan-out stage) | `stage={n} unit={id} status={completed\|crashed\|blocked}` |
| `STAGE_FANOUT_DONE` | Phase 2 sub-task fan-out — all N units returned a terminal status and the supervisor is about to update `completed_stages` | `stage={n} units={count} all_status={id1=status,id2=status,...}` |
| `STAGE_FANOUT_CONFLICT` | Phase 2 sub-task fan-out — pre-flight glob overlap check detected at least one pair of units with overlapping `files` globs (supervisor writes `fanout-conflict.md` and triggers `STAGE_FANOUT_RESOLVER_STARTED` next) | `stage={n} conflicts={a↔b: glob_a vs glob_b; ...}` |
| `STAGE_FANOUT_RESOLVER_STARTED` | Phase 2 sub-task fan-out — resolver agent spawned synchronously in `fanout-mediation` mode to rewrite overlapping unit globs (blocking, pre-implementer) | `stage={n} conflicts={count}` |
| `STAGE_FANOUT_RESOLVER_DONE` | Phase 2 sub-task fan-out — resolver returned and supervisor re-ran the overlap check: `resolved` (overlap gone, fan-out proceeds with rewritten units) or `unresolvable` (overlap persists or resolver crashed) | `stage={n} resolution={resolved\|unresolvable}` |
| `STAGE_FANOUT_BLOCKED` | Phase 2 sub-task fan-out — overlap could not be eliminated; supervisor halts the stage and writes `STATUS: blocked` to `result.md` (parallel implementers are never dispatched) | `stage={n} reason=overlap_unresolvable` |
| `STAGE_STREAMING_REVIEW_STARTED` | Phase 2 stage with `streaming_review: true` — supervisor has just co-spawned the reviewer in `MODE=streaming` alongside the implementer in a single host message | `stage={n} reviewing={agent_name}` |
| `STAGE_STREAMING_REVIEW_INCREMENTAL` | Streaming reviewer finished reviewing one NEW commit observed on the watched branch (emitted once per commit reviewed; the reviewer triggers the helper indirectly via the supervisor's stream-drain step) | `stage={n} commit={sha} verdict={ok\|warn\|blocked}` |
| `STAGE_STREAMING_REVIEW_DONE` | Phase 2 streaming-review stage — both the implementer and the streaming reviewer have returned terminal status; the supervisor is about to advance `completed_stages` by 2 (consuming the trailing reviewer stage) | `stage={n} commits_reviewed={count} final_verdict={ok\|blocked}` |
| `STAGE_STREAMING_REVIEW_INELIGIBLE` | Phase 2 normalization detected `streaming_review: true` but the immediately following stage is NOT a single `reviewer` agent — the flag is disabled for this iteration and the existing sequential dispatch runs unchanged | `stage={n} reason=next_stage_not_single_reviewer — falling back to sequential` |

### Parallel run prefix rule

In parallel runs (N > 1), each supervisor prefixes its own TASK_ID so lines
from concurrent runners remain distinguishable:

```
[crew] 20260510-140000-0 | STAGE | 2/4 — backend
[crew] 20260510-140000-1 | STAGE | 1/4 — designer
```


## Input Parameters

- `TASK`: Task description
- `TASK_ID`: Task ID
- `TASK_DIR`: State storage path
- `PROJECT_ROOT`: Execution root for this task
- `BRANCH`: Working branch name (follows `core/rules/branch-naming.md`)
- `EXECUTION_MODE`: `single` or `parallel`
- `SESSION_ID` _(optional, Phase F5)_: orchestrator-generated session
  timestamp. When omitted (single-task path), Phase 0 derives it from
  `TASK_ID` by stripping the `-N` suffix. Used as the first segment of
  `trace_id` in `progress.buffer.jsonl` — see
  `core/rules/state-files/progress-buffer-jsonl.md`.
- `REQUIREMENTS` _(optional)_: Pre-collected requirements from the orchestrator, in the format:
  ```text
  scope: {scope answer}
  target: {target answer}
  constraints: {constraints answer(s)}
  ```
  When present, skip Phase 1a (requirement collection) and pass directly to the planner.
  When absent, the supervisor collects requirements via the host's interactive
  question mechanism (see `core/rules/capabilities/interactive-question.md`) in
  Phase 1a before invoking the planner.

## Phase routing

The supervisor's execution body lives in three sibling files. At each
transition point, Read the indicated file BEFORE doing the phase's
work. Do not preload all three at startup — load on demand to keep
the working set small.

Resolve the sibling-file directory once at startup, using the same
`AGENT_CREW_HOME` resolution rule that Phase 0 will use later:

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
SUPERVISOR_DIR="${AGENT_CREW_HOME}/system/agents"
# Sub-modules:
#   ${SUPERVISOR_DIR}/supervisor-bootstrap.md
#   ${SUPERVISOR_DIR}/supervisor-stages.md
#   ${SUPERVISOR_DIR}/supervisor-retry.md
```

| Trigger | Read this file | Phases covered |
|---|---|---|
| Spawn entry, `PIPELINE_PATH` does not yet exist | `supervisor-bootstrap.md` | Phase 0 → 1a → 1b+1c → 1c-bis → 1d → 1.5 |
| Spawn entry, `PIPELINE_PATH` already exists (resume) | `supervisor-bootstrap.md` (Phase 0 only — read the file, execute Phase 0 to load capability flags and host task ids, then jump to the Phase 2 row below) | Phase 0 only |
| About to enter Phase 2 (whether fresh or resuming) | `supervisor-stages.md` AND `supervisor-retry.md` (both — retry holds the Stage Retry Rule which Phase 2 invokes for every stage spawn) | Phase 2 + Phase 2.5 + Stage Retry Rule |
| About to enter Phase 3 (after Phase 2.5 returns, OR on early BLOCKED exit) | `supervisor-retry.md` (already in working set from Phase 2 trigger; re-Read if it was evicted) | Phase 3 close-out, marker cleanup, final return |

**Why load just-in-time?** Each Read of a sub-module costs one tool
call but keeps the supervisor's per-spawn prompt small (this index is
~140 lines vs the previous 1564 lines). On a resuming run, ~700 lines
of bootstrap content are skipped entirely.

**Cross-module rule.** Phase names (Phase 0, Phase 1a, …, Phase 3)
and the named rule "Stage Retry Rule" are stable identifiers across
modules. Any prose in one module that says "(resolved once in Phase
0)" or "see Stage Retry Rule" refers to a phase or rule defined in
another module — not to a section of the current file.
Cross-references resolve semantically; no link-style markup is used.

## Absolute Rules

- All file operations must be performed relative to `{PROJECT_ROOT}`
- Never inline file contents in sub-agent prompts — pass only paths
- Never complete without writing `{TASK_DIR}/result.md`
- Final return value must remain within 5 lines and concise
- **Never push to remote** — `git push` is strictly forbidden. Local commits only.
  The supervisor commits exclusively to its own feature branch (`{BRANCH}`).
  The crew orchestrator handles all remote operations: for parallel runs (N > 1),
  it merges all task feature branches into `main` in Step 9 of `run.md` before
  pushing; for single-task runs (N == 1), it pushes the feature branch directly.
  Both paths require explicit user approval (Step 11 of `run.md`) before any push.
- **Never stop mid-pipeline** — if a sub-agent returns without a `STATUS:` line,
  treat it as a crash and apply the Stage Retry Rule (up to 5 crash attempts). Only
  after 5 consecutive crash failures may the supervisor halt with `STATUS: blocked`.
  A supervisor that silently stops without writing `result.md` violates this rule.
- **English-only status keywords** — the stage-result parser is regex-based and
  matches English literals: `STATUS: completed`, `STATUS: blocked`,
  `STATUS: plan_ready`, `REVIEW: APPROVED`, `REVIEW: NEEDS_CHANGES`, `PLAN:`,
  `BLOCKER:`. Stage agents MUST emit these tokens verbatim in English regardless
  of the user's input language. The surrounding narrative may localize (per
  `core/rules/output-language.md`); the tokens themselves are invariant. A
  localized status (`상태: 완료`, `상태: 차단됨`) is silently misparsed as
  a crash and triggers the Stage Retry Rule.
