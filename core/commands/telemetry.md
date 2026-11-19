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
- `TOKENS`         — token totals summed across
                     `${STATE_DIR}/cost/${TASK_ID}.jsonl`; a row's
                     `total_tokens` is used when present, otherwise
                     `input_tokens + output_tokens` is used
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
| `${STATE_DIR}/cost/${TASK_ID}.jsonl` (Phase 3.3+ and host-bridge token ingestion) | Full cost-tracking adapters, plus bridge runs whose CLI output exposes token usage | Token totals |

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

## JSON lifecycle 표시

기존 `status`와 텍스트 출력은 유지한다. `--format json`의 각 task에는 다음
읽기 전용 필드를 추가한다.

- `objective_status`: `open | completed | blocked | cancelled`. terminal
  `result.md`가 register보다 우선한다.
- `execution_status`: `running | idle | waiting_user | terminal`.
- `idle_reason`: `legacy_unowned`, `lease_expired`, `invalid_lease` 또는 register의
  명시적 idle 사유. idle이 아니거나 사유가 없으면 `null`이다.
- `last_heartbeat_at`, `lease_expires_at`: register 원문을 전달하며 부재는 `null`이다.
- `resumable`: objective가 `open`이고 execution이 `idle` 또는 `waiting_user`이면
  `true`인 표시 값이다. 실행 허가나 자동 재개를 뜻하지 않는다.

UTC lease가 현재보다 미래이며 600초 이내이면 `running`이다. 현재와 같거나
이전이면 `lease_expired`, 파싱 불가·timezone 부재·600초 초과 미래이면
`invalid_lease`이다. lease와 명시적 상태가 없는 legacy task는
`open/idle/legacy_unowned`로 표시한다. 승인 대기와 명시적 `waiting_user`는
대기 상태이며 종료 objective는 항상 `terminal`이다.

JSON summary에는 `by_execution_status`별 개수와
`expired_execution_leases`·`invalid_execution_leases` 개수를 추가한다.
`core/scripts/execution_lifecycle.py`는 순수 판단·복사 전이 helper이며, 이 조회는
owner/lease를 기록하거나 실행기를 호출하지 않는다. 기존 품질 판정과 TDD 증거는
이 표시로 변경하거나 보완하지 않는다.
