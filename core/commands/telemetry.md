# crew:telemetry — Pipeline timing, retry, and throughput report

Aggregates per-task progress + cost data into a wall-clock-duration,
retry-count, and token-usage summary across recent runs. Read-only —
walks `${STATE_DIR}/tasks/*/` and never mutates state.

The provider-neutral aggregator is
`core/scripts/telemetry-aggregate.py`. This command is a thin wrapper.
It works on every adapter (no capability gating). Token usage is
populated only when `cost_tracking=true`; timing and retry data
require `progress.buffer.jsonl` (Phase F5+).

## Modes

| User intent | Invocation |
|---|---|
| 10 most-recent tasks (default) | (no args) |
| One specific task | `--task-id TASK_ID` |
| All tasks in one session | `--session-id SESSION_ID` |
| N most-recent tasks | `--recent N` |
| Date-bounded | `--since YYYY-MM-DD --until YYYY-MM-DD` |
| Machine-readable | `--format json` |

## Execution

```bash
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"

if [ ! -d "${STATE_DIR}/tasks" ]; then
  echo "No tasks found. Run crew:setup or crew:run first."
  exit 0
fi

python3 "${AGENT_CREW_HOME}/scripts/telemetry-aggregate.py" \
  --state-dir "${STATE_DIR}" \
  "$@"
```

## What the report shows

Per-task columns:

- `TASK ID`        — `{YYYYMMDD}-{HHMMSS}[-{idx}]`
- `STATUS`         — `completed | blocked | running` (derived from
                     `register.json.current_phase`)
- `PHASE`          — `register.json.current_phase` (terminal value
                     for completed/blocked tasks)
- `DUR`            — wall-clock duration from `STARTED` to terminal
                     event (`COMPLETED`/`BLOCKED`)
- `STAGES`         — `{completed}/{emitted}` (completed from
                     `pipeline.json.completed_stages`; emitted from
                     `STAGE` event count in `progress.buffer.jsonl`)
- `RETRY`          — `RETRY` event count
- `TOKENS`         — `input_tokens + output_tokens` summed across
                     `${STATE_DIR}/cost/${TASK_ID}.jsonl` (when
                     `cost_tracking=true`; `—` otherwise)
- `TASK`           — original task description (truncated to 60 chars)

Aggregate footer:

- Task count breakdown (total / completed / blocked / running)
- Duration mean + median across completed tasks
- Total retries, total tokens
- Blocker histogram (`validation_budget_exceeded=2`,
  `cost_budget_exceeded=1`, etc.)

## Capability notes

The script reads three independent data sources per task:

| Source | When populated | Effect on report |
|---|---|---|
| `register.json` (Phase F4+) | Every task | Status, current phase, blockers |
| `progress.buffer.jsonl` (Phase F5+) | Every task | Duration, stage/retry counts |
| `${STATE_DIR}/cost/${TASK_ID}.jsonl` (Phase 3.3+, `cost_tracking=true`) | Claude host with the capability flag | Token totals |

Any missing source renders as `—` in the column; the script never
errors on absence. Pre-F4/F5 task directories show partial data
gracefully.

## Cross-references

- `core/scripts/telemetry-aggregate.py` — implementation
- `core/scripts/cost-aggregate.py` — sibling aggregator for the
  per-call token detail view (used by `crew:cost`)
- `core/rules/state-files/register-json.md` — terminal-state contract
- `core/rules/state-files/progress-buffer-jsonl.md` — event-buffer
  contract
- `core/rules/capabilities/cost-tracking.md` — token-usage contract
