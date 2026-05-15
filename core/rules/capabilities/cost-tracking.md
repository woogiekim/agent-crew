# cost_tracking Capability

## Purpose

Let core measure per-task, per-stage, and per-agent-call token usage so
that the quality-loop supervisor can apply a cost circuit breaker
(planned — refactor item 3-A) and so that telemetry aggregation
(planned — refactor item 13) can summarize usage across runs. Without
this flag, the quality loop has only retry-count discipline; it cannot
stop a runaway pipeline before it exhausts a token budget.

## Required Adapter Surface (flag=true)

**Deliberately abstract for Phase A1.** The exact schema is deferred to
refactor Phase E (item 3.3). Adapter MUST advertise *some* mechanism for
emitting per-call token totals to core. Three permissible shapes (the
adapter chooses one):

1. **Per-call file append.** Adapter writes a JSON line to
   `${STATE_DIR}/cost/<taskId>.jsonl` after every agent call. Suggested
   shape:

   ```json
   {
     "ts": "...",
     "agent": "...",
     "stage": "...",
     "input_tokens": 0,
     "output_tokens": 0,
     "cache_creation_tokens": 0,
     "cache_read_tokens": 0
   }
   ```

2. **Host getTask usage exposure.** Adapter populates
   `getTask(taskId).metadata.usage` with token totals. This is the
   canonical path for hosts that already expose usage via their task
   surface (Claude Code's `TaskGet` is such a host).

3. **Adapter-side aggregator.** Adapter ships its own `cost-track.sh`
   hook that writes to the file in shape (1); core simply reads.

The exact schema is decided in Phase E (item 3.3). For Phase A1 this doc
records the abstract surface only.

## Consumer Contract (core)

Consumers are planned but not implemented in Phase A1:

- **`core/scripts/cost-aggregate.py`** (planned, Phase E3.3 — not
  present yet) — reads per-task cost data, emits a crew-wide summary.
  Used by `core/commands/cost.md`.
- **Quality-loop supervisor** (`core/rules/quality-loop.md`, future
  revision in Phase E3.3) — checks the running token total against a
  per-task budget; halts the retry cycle when the threshold is exceeded.

Core's input shape, from its perspective, is a function
`get_task_cost(taskId) -> { input_tokens, output_tokens, ... }` that
core can call. The implementation is the adapter's choice.

## Absence Behavior (flag=false)

No cost tracking; cost data is unavailable to the quality loop. The
quality loop uses retry-count only (today's behavior). `crew:cost`
falls back to the adapter-native cost UI (for example, `claude /cost`)
and prints a note that cost tracking is not advertised for this
adapter.

## Adapter Examples

| Adapter | cost_tracking | How it is implemented |
|---|---|---|
| claude  | planned-true | Existing `core/hooks/cost-tracker.sh` writes per-call JSONL; `TaskGet().usage` also exposes token fields. Schema finalized in Phase E3.3. |
| codex   | false | No token-usage exposure in the current Codex tool surface. May flip to true in a future phase. |
| generic | false | No token-usage source. |

## Related Files

Producer (when flag=true):

- `adapters/claude/setup.sh` (sets the flag)
- `core/hooks/cost-tracker.sh` (writes per-call data — currently
  Claude-specific; a future revision may generalize the writer)

Consumer (planned):

- `core/scripts/cost-aggregate.py` (Phase E3.3 — not present yet)
- `core/commands/cost.md`
- `core/rules/quality-loop.md` (Phase 3-A cost circuit breaker)

Cross-flag:

- `hook_system`: when both flags are true, the adapter can wire
  `cost-tracker.sh` as a `PostToolUse` hook (the current Claude
  wiring). When `hook_system` is false, the adapter ships cost data via
  another mechanism. The two flags are independent on purpose — see
  `hook-system.md`.
