# cost_tracking Capability

## Purpose

Let core measure per-task, per-stage, and per-agent-call token usage so
that the supervisor can apply a **cost circuit breaker** (Phase 3.3 —
implemented) and so that telemetry aggregation (Phase J13 —
implemented, via `core/scripts/telemetry-aggregate.py` and
`crew:telemetry`) can summarize usage across runs. Without this flag,
the quality loop has only retry-count discipline; it cannot stop a
runaway pipeline before it exhausts a token budget.

## Required Adapter Surface (flag=true) — Phase 3.3 schema

The adapter MUST write one JSON line per agent call to:

```
${STATE_DIR}/cost/${TASK_ID}.jsonl
```

Each line has the shape:

```json
{
  "ts":                    "2026-05-16T01:23:45Z",
  "task_id":               "20260516-012345-0",
  "session_id":            "20260516-012345",
  "agent":                 "backend",
  "stage":                 2,
  "model":                 "claude-sonnet-5",
  "tier":                  "balanced",
  "input_tokens":          12345,
  "output_tokens":         6789,
  "total_tokens":          19134,
  "cache_creation_tokens": 0,
  "cache_read_tokens":     0
}
```

**Required:** `ts`, `task_id`, `session_id`, `agent`, `model`,
`input_tokens`, `output_tokens`.

**Optional** (default `0` / `null` / `"unknown"`): `stage`, `tier`,
`total_tokens`, `cache_creation_tokens`, `cache_read_tokens`. When `tier` is
`"unknown"` the aggregator falls back to a model→tier map; the canonical map
lives in `adapters/claude/setup.sh`'s `TIER_TO_MODEL` and is mirrored in
`core/scripts/cost-aggregate.py`'s `MODEL_TIER_FALLBACK`. Hosts that expose only
a total token count may set `input_tokens=0`, `output_tokens=0`,
`total_tokens={measured_total}`, and `usage_granularity="total_only"`.

The adapter MAY also populate the host's task-metadata surface (e.g.
`getTask().metadata.usage`); this is not required and not consumed by
core in Phase 3.3.

**Concurrency.** JSONL append at line granularity is assumed atomic on
local filesystems (the standard POSIX guarantee for writes ≤ `PIPE_BUF`,
typically 4096 bytes; each row is ~250 bytes). Lines from concurrent
writers may interleave in order but each line remains intact and
parseable.

## Consumer Contract (core)

Implemented in Phase 3.3:

- **`core/scripts/cost-aggregate.py`** — provider-neutral reader.
  Modes: `--task-id`, `--session-id`, `--recent N`, default summary.
  Used by `core/commands/cost.md`.
- **Supervisor cost circuit breaker** — `core/agents/supervisor-retry.md`
  § Cost Circuit Breaker. Before each stage spawn and each retry, the
  supervisor calls `cost-aggregate.py --task-id ${TASK_ID} --check-breaker`
  and branches on `ok` / `warn` / `exceeded`. See
  `core/rules/quality-loop.md` § Cost Circuit Breaker for thresholds
  (50% soft warning, 100% hard stop).

Core's input shape is a CLI exit code (`0` / `1` / `2` from
`--check-breaker`) and stdout JSON for richer reads.

## Absence Behavior (flag=false)

No cost tracking; cost data is unavailable to the supervisor's circuit
breaker. The quality loop uses retry-count only (pre-3.3 behavior).
`crew:cost` prints a one-paragraph fallback note and exits cleanly.
The circuit breaker check is gated on the flag — when false, the
supervisor's retry loop is identical to its pre-3.3 form.

## Adapter Examples

| Adapter | cost_tracking | How it is implemented |
|---|---|---|
| claude  | **true** | `core/hooks/cost-tracker.sh` PostToolUse hook writes per-call JSONL under `${STATE_DIR}/cost/${TASK_ID}.jsonl`; `adapters/claude/bin/claude-host-bridge` also records bridge JSON usage through `core/scripts/host-bridge-token-usage.py`. |
| codex   | false | No full token-usage surface is advertised for circuit-breaker enforcement. `adapters/codex/bin/codex-host-bridge` opportunistically records total tokens from CLI output through `core/scripts/host-bridge-token-usage.py` when the bridge runs and the output includes a token summary. |
| generic | false | No token-usage source. |

## Related Files

Producer:

- `adapters/claude/setup.sh` (writes flag `true`; registers
  `cost-tracker.sh` as `PostToolUse`)
- `install.sh` (same registration on fresh install)
- `core/hooks/cost-tracker.sh` (writes per-call JSONL; capability-gated
  by the `cost_tracking` flag the adapter advertises)
- `core/scripts/host-bridge-token-usage.py` (normalizes Claude JSON and Codex
  text bridge usage into the same JSONL cost contract)
- `adapters/claude/bin/claude-host-bridge` and
  `adapters/codex/bin/codex-host-bridge` (opportunistic bridge usage producers)

Consumer:

- `core/scripts/cost-aggregate.py` (provider-neutral reader)
- `core/commands/cost.md` (`crew:cost` user-facing wrapper)
- `core/agents/supervisor-retry.md` § Cost Circuit Breaker
- `core/agents/supervisor-bootstrap.md` Phase 0 capability load
  (`HAS_COST_TRACKING`)
- `core/rules/quality-loop.md` § Cost Circuit Breaker

Cross-flag:

- `hook_system`: Claude's `cost-tracker.sh` is wired via the host's
  PostToolUse hook surface. The capability `hook_system` is now
  `implemented` (Phase G6) and the Claude adapter advertises it true.
  The two flags remain independent on purpose — a future host could
  ship `cost_tracking=true` via a different mechanism (e.g.,
  `getTask().usage`) without `hook_system`.
