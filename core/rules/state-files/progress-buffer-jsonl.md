# progress.buffer.jsonl — Structured Progress Event Buffer

The supervisor writes every progress event in two forms:

- **Human-readable**: `${TASK_DIR}/progress.log` (single-line `ts | EVENT | detail` rows)
- **Structured**: `${TASK_DIR}/progress.buffer.jsonl` (one JSON object per line, this file)

Both sinks are fed by a single `log_progress` helper in
`core/agents/supervisor-bootstrap.md` Phase 0. The two files share an event
stream — every event appears in both — but the JSONL buffer is the
machine-parseable source of truth for `crew:status` aggregations and any
future telemetry tooling.

## File Location

```
${STATE_DIR}/tasks/${TASK_ID}/progress.buffer.jsonl
```

Where `STATE_DIR = ${AGENT_CREW_HOME}/state/${PROJECT_NAME}`. Sits alongside
the existing `progress.log` in the per-task directory. Created on first
`log_progress` call (helper uses `>>` append; no preflight `touch`). Wiped
by `crew:setup` reset (same path glob as `progress.log`); preserved by
`crew:update`.

Related trace files live in the same task directory:

- `tool-events.jsonl` — native tool calls keyed by `trace_id`, with redacted
  action summaries, start/end timestamps, exit/status, token usage reference,
  and failure class.
- `delegation.jsonl` — provider-neutral delegation lineage with `span_id`,
  `parent_span_id`, `agent_role`, `unit_id`, and `delegated_by`. Host task DAGs
  mirror this state; they are not the source of truth.

## Line Schema

Canonical shape:

```json
{
  "ts":         "2026-05-16T01:23:45Z",
  "trace_id":   "20260516-012345.20260516-012345-0.2.3",
  "task_id":    "20260516-012345-0",
  "session_id": "20260516-012345",
  "event":      "STAGE_DONE",
  "stage":      2,
  "agent":      "backend",
  "attempt":    3,
  "status":     "completed",
  "detail":     "backend stage — APPROVED",
  "files":      []
}
```

One JSON object per line, UTF-8, `\n` terminator. No trailing whitespace.

### Field catalog

| Field | Type | Required | Source / Rationale |
|---|---|---|---|
| `ts` | string (ISO-8601 UTC, seconds + `Z`) | yes | `date -u +%Y-%m-%dT%H:%M:%SZ` |
| `trace_id` | string | yes | `${SESSION_ID}.${TASK_ID}.${STAGE_INDEX}.${RETRY_ATTEMPT}` — see below |
| `task_id` | string | yes | denormalized from supervisor input (greppable without parsing `trace_id`) |
| `session_id` | string | yes | parallel runs: passed from orchestrator; single runs: derived as `${TASK_ID%-*}` |
| `event` | string | yes | one of the 13-event vocabulary from `supervisor.md` event catalog |
| `stage` | integer | optional | 1-based stage index; `0` for non-stage events (Phase 0/1d/3, cost breaker) |
| `agent` | string | optional | currently-running stage agent's name; empty when not in a stage |
| `attempt` | integer | optional | 1-based retry counter within the current stage; `0` for non-stage events |
| `status` | string | optional | derived from `event` (lookup table in the helper); recommended values: `started`, `in_progress`, `completed`, `failed`, `cancelled`, `retry`, `skipped`, `warn` |
| `detail` | string | optional | free-text second arg to `log_progress`; preserved verbatim, JSON-encoded safely |
| `files` | array of strings | optional | reserved for future per-event file-attachment tracking (Phase J13); currently always `[]` |

## trace_id Format

```
{SESSION_ID}.{TASK_ID}.{STAGE_INDEX}.{RETRY_ATTEMPT}
```

The 4-tuple is unique per (session, task, stage, retry-attempt). Two events
emitted within the same attempt **share the same trace_id** — this is
intentional, they correlate (e.g., `STAGE` emit + `STAGE_DONE` emit + any
`RETRY` emit fired from within the same crash-budget tick).

Derivation rules:

| Component | Source | Fallback |
|---|---|---|
| `SESSION_ID` | passed by orchestrator (`run.md` Step 4) | derived as `${TASK_ID%-*}` (strips the `-N` task-index suffix, recovering the timestamp prefix the orchestrator generated) |
| `TASK_ID` | supervisor input (always present) | n/a |
| `STAGE_INDEX` | supervisor sets at Phase 2 stage-loop entry | `0` when not in a stage |
| `RETRY_ATTEMPT` | supervisor sets at retry-loop entry; bumps per retry | `0` when not in a stage |

When `TASK_ID` has no `-N` suffix (manual / ad-hoc invocations), the
parameter expansion `${TASK_ID%-*}` leaves it unchanged — SESSION_ID then
equals TASK_ID. Acceptable as a fallback; collapses the session/task
distinction to a single id (the trace_id's first two segments duplicate).

## Event Vocabulary

The `event` field uses the supervisor's documented event catalog. See
`core/agents/supervisor.md` § Event catalog for the canonical list. As of
Phase 3.5 the vocabulary is:

- `STARTED`, `PHASE`, `STAGE`, `STAGE_DONE`, `BLOCKED`, `RETRY`,
  `COMPLETED`, `RESUME_REQUESTED`
- `COST_WARN`, `COST_BLOCKED` (Phase 3.3)
- `HANDOFF_PAGEOUT`, `HANDOFF_PAGEDOUT`, `HANDOFF_PAGEOUT_FAILED`,
  `HANDOFF_PAGEOUT_SKIPPED` (Phase 3.5)

New events introduced by future phases are added to the catalog and
automatically flow through the buffer without schema changes.

## Concurrency

JSONL append at line granularity is assumed atomic on local filesystems
(POSIX `write()` ≤ `PIPE_BUF`, typically 4096 bytes; each row is
~250–500 bytes). The supervisor is single-threaded per task. Multiple
supervisors writing to **different** task files do not interfere.
Same assumption as `${STATE_DIR}/cost/${TASK_ID}.jsonl` (see
`core/rules/capabilities/cost-tracking.md` § Concurrency).

## Consumer Contract

Consumers (primarily `core/commands/status.md` Step 5) MUST tolerate:

| Situation | Behavior |
|---|---|
| Required field missing (`ts`, `trace_id`, `task_id`, `event`) | Skip the line; emit one warning to stderr. Never abort the whole rendering. |
| Optional field missing | Apply default: `stage=0`, `agent=""`, `attempt=0`, `status="unknown"`, `detail=""`, `files=[]`. Render normally. |
| Malformed JSON (decode error) | Skip the line; count + emit one summary warning per file. |
| Unknown field present | Preserve in the parsed dict but ignore for rendering. (Forward-compat.) |
| File absent | Fall through to `tail -20 progress.log`. (Pre-F5 task directories have no buffer.) |
| File present but empty | Render "(no events yet)". |

## Producer

`log_progress` helper in `core/agents/supervisor-bootstrap.md` Phase 0
Step 0c. The helper writes to all three sinks (`progress.log`, stderr,
`progress.buffer.jsonl`) from a single invocation. Every event emitted
by the supervisor — Phase 0 bootstrap, Phase 1 analysis, Phase 2 stage
loop, Phase 2.5 approval gates, Phase 3 close-out, cost breaker, handoff
page-out — flows through this helper.

The helper JSON-encodes `detail` via a Python heredoc to handle quotes,
backticks, em-dashes, and Unicode safely. Bash string concatenation for
JSON construction is forbidden (the cost-tracker.sh hook follows the
same pattern for the same reason).

## Forward Compatibility

The schema is **additive**. Future phases that add new event vocabulary
or new fields:

- New events: add to `supervisor.md` event catalog + extend the helper's
  `case` lookup for the `status` default. Consumer tolerates unknown
  events (renders verbatim).
- New fields: add to producer + schema doc. Consumer tolerates unknown
  fields (preserved-but-ignored).
- Field removal: forbidden in v1 of the schema. A breaking schema bump
  would version the file (e.g., `progress.buffer.v2.jsonl`).

## Related Files

Producer:

- `core/agents/supervisor-bootstrap.md` § Phase 0 Step 0c
  (`log_progress` helper definition)

Consumers:

- `core/commands/status.md` Step 5 (renders last 20 events as a
  structured table; preferred over `tail -20 progress.log`)

Sibling event surfaces:

- `core/agents/supervisor.md` § Event catalog (the canonical event
  vocabulary this file populates)
- `core/rules/capabilities/monitor-tool.md` (host-streamed event
  surface; F5's file-based buffer is the fallback path)
- `${TASK_DIR}/progress.log` (human-readable mirror, same event stream)

Sibling state-file docs (Phase F4):

- `core/rules/state-files/register-json.md`
- `core/rules/state-files/pipeline-json.md`
- `core/rules/state-files/session-json.md`
- `core/rules/state-files/capabilities-json.md`

Schema validator (Phase F4):

- `core/scripts/validate-state-schema.py` validates every line
  against the schema above.
- Schema file: `core/schemas/progress-buffer.schema.json`.
