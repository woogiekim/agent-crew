# crew:cost — Per-task token usage and budget summary

Aggregates per-call token data captured by the host adapter (see
`core/rules/capabilities/cost-tracking.md`) and prints a per-task,
per-session, or summary report.

The provider-neutral aggregator is `core/scripts/cost-aggregate.py`.
This command is a thin wrapper around it that picks the right mode
based on the user's arguments.

## Modes

| User intent | Invocation |
|---|---|
| Summary of all tasks under the project | (no args) |
| One specific task | `--task-id TASK_ID` |
| All tasks in one session | `--session-id SESSION_ID` |
| N most-recent tasks | `--recent N` |

## Execution

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --prefer-existing-legacy \
  --format shell)"
CAPABILITIES_PATH="${STATE_DIR}/capabilities.json"

# Capability check
HAS_COST=$(python3 -c "
import json
try: print('1' if json.load(open('${CAPABILITIES_PATH}')).get('cost_tracking') else '0')
except Exception: print('0')
" 2>/dev/null)

if [ "${HAS_COST}" != "1" ]; then
  echo "Cost tracking is not advertised for the active host adapter."
  echo "Capabilities file: ${CAPABILITIES_PATH}"
  echo
  echo "On Claude: cost-tracking is enabled when crew:setup runs against the"
  echo "claude adapter. On Codex or generic: exact token usage is not surfaced"
  echo "by the host. The aggregator may still report labeled proxy metrics from"
  echo "local progress, tool, or delegation telemetry; if none exist it prints"
  echo "an explicit unavailable reason instead of implying zero measured usage."
fi

# Build the aggregator invocation from the user's flags
python3 "${AGENT_CREW_HOME}/scripts/cost-aggregate.py" \
  --state-dir "${STATE_DIR}" \
  --format table \
  "$@"
```

## Example output (table mode)

```
Task: 20260516-012345-0
  calls=14  tokens=98,234  (72,118 in / 26,116 out)
  budget=200,000  consumed=49.1%
  by agent:
    analyst        calls= 1  in=  41,210  out=   7,182
    backend        calls= 8  in=  24,116  out=  12,808
    reviewer       calls= 5  in=   6,792  out=   6,126
```

## JSON output

For machine-readable output (e.g., piping into another tool), drop
`--format table` from the invocation above. The aggregator emits JSON
by default. See `core/scripts/cost-aggregate.py --help` for the full
flag set.

## Budget overrides

Per-tier budgets are configurable via env vars (consumed by
`cost-aggregate.py`):

| Tier      | Default budget | Env var                       |
|-----------|---------------:|-------------------------------|
| `xhigh`   |        300,000 | `AGENT_CREW_BUDGET_XHIGH`     |
| `deep`    |        200,000 | `AGENT_CREW_BUDGET_DEEP`      |
| `balanced`|        150,000 | `AGENT_CREW_BUDGET_BALANCED`  |
| `light`   |        100,000 | `AGENT_CREW_BUDGET_LIGHT`     |

The per-task budget is `max(tier_budget)` over the tiers used by the
task's pipeline.

## Absence behavior

When the active adapter advertises `cost_tracking=false` (Codex,
generic), exact host token telemetry is unavailable. The aggregator labels
measured token data separately from proxy metrics. If neither measured token
records nor proxy telemetry are available, output includes an explicit
unavailable reason instead of implying zero usage.

## Related

- `core/rules/capabilities/cost-tracking.md` — capability contract +
  per-call JSONL schema
- `core/rules/quality-loop.md` § Cost Circuit Breaker — the
  supervisor-side enforcement that consumes the same data
- `core/scripts/cost-aggregate.py` — the canonical reader (run with
  `--help` for full flag set)
