# crew:smm — Shared Mental Model single-view

Renders the whole Shared Mental Model (SMM) for a task as one coherent
read-only block, uniting the five fragmented per-task state sources:

- `pipeline.json`          — execution graph (stages / completed_stages)
- `progress.log`           — human-readable event log
- `progress.buffer.jsonl`  — structured event buffer
- `register.json`          — slim state pointer (phase / approval / verify)
- `handoff.md`             — freeform stage handoff narrative

Issue #129 Finding #2. `crew:status` already prints a compact snapshot and
`crew:telemetry` produces a metrics table, but neither unites the whole SMM
for a task in one block, and neither reads `handoff.md`. `crew:smm` adds the
missing single-view: an enriched, on-demand `crew:status` with clear per-task
sections for N>1 interleaved parallel runs.

The provider-neutral aggregator is `core/scripts/smm-aggregate.py`. This
command is a thin wrapper. It works on every adapter (no capability gating)
and is **READ-ONLY** — it walks `${STATE_DIR}/tasks/*/` and never mutates,
creates, or deletes any state file.

## Modes

| User intent | Invocation |
|---|---|
| 10 most-recent tasks (default) | (no args) |
| One specific task | `--task-id TASK_ID` |
| All tasks in one session (N>1) | `--session-id SESSION_ID` |
| N most-recent tasks | `--recent N` |
| Machine-readable | `--format json` |

Selection precedence (same as `crew:telemetry`): `--task-id` > `--session-id`
> `--recent N`.

## Execution

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
eval "$(python3 "${AGENT_CREW_HOME}/scripts/project_state.py" resolve \
  --agent-crew-home "${AGENT_CREW_HOME}" \
  --project-root "${PROJECT_ROOT}" \
  --prefer-existing-legacy \
  --format shell)"

if [ ! -d "${STATE_DIR}/tasks" ]; then
  echo "No tasks found. Run crew:setup or crew:run first."
  exit 0
fi

python3 "${AGENT_CREW_HOME}/scripts/smm-aggregate.py" \
  --state-dir "${STATE_DIR}" \
  --project-root "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" \
  "$@"
```

## What the view shows

One coherent block per task (a session header line is added when more than one
task matches, so interleaved N>1 runs read cleanly):

- `Task`     — task id + original description
- `Branch`   — working branch (from `register.json`)
- `Status`   — `completed | blocked | cancelled | running | unknown`
- `Phase`    — `register.json.current_phase`
- `Approval` / `Verify` — `approval_status` / `verification_status`
- `Stages`   — `{completed}/{total}` plus a per-stage list with
               `[x]` (done) / `[>]` (current) / `[ ]` (pending) markers
- `Files`    — `register.json.modified_files`
- `Blocked`  — `register.json.blocked_by` (when non-empty)
- `Handoff`  — `handoff.md` line count + heading map, or the literal
               `(handoff not produced yet)` token when absent
- `Recent`   — last up to 5 events from `progress.buffer.jsonl`
               (falling back to `progress.log`)
- `Orchestration` — compact operator-facing summary of:
  - `Memory` — recall status, selected memory count, applied/ignored usage
    decisions, and sent/failed feedback counts from `context/memory-*`
    artifacts.
  - `DAG` — stage count, current stage agents, fan-out units, TDD-parallel
    stages, and streaming-review stages from `pipeline.json`.
  - `Inbox` — structured progress event count, terminal/fan-out events, and
    delegation rows from `progress.buffer.jsonl` and `delegation.jsonl`.
  - `Evolution` — task-local evolution report presence, observed pattern count,
    and proposal status from `context/evolution-report.json`.

`--format json` prints `{"state_dir": str, "tasks": [<smm dict>, ...]}` where
each task dict carries every field above plus a `sources_present` map.

## Degradation

Every source read is absence-tolerant: a missing `pipeline.json` /
`handoff.md` / `register.json` / buffer / log never errors — the matching keys
take documented empty defaults and the `sources_present` flag for that source
is `false`. Pre-F4/F5 task directories render partial data gracefully.

## Capability notes

No capability gating. The view reuses `telemetry-aggregate.py` readers
(`resolve_state_dir`, `read_register`, `read_progress_buffer`,
`read_progress_log`, `list_task_dirs`, `aggregate_task`); it adds only the
`handoff.md` reader and the unified rendering layer — no net-new state schema.

## Cross-references

- `core/scripts/smm-aggregate.py` — implementation
- `core/commands/status.md` — compact live snapshot (the SMM single-view is
  the on-demand expanded counterpart)
- `core/commands/telemetry.md` — sibling read-only aggregator for timing /
  retry / throughput metrics
- `core/rules/state-files/register-json.md` — terminal-state contract
- `core/rules/state-files/progress-buffer-jsonl.md` — event-buffer contract
- `core/rules/state-files/pipeline-json.md` — stage-graph contract
```
