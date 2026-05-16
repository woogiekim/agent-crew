# pipeline.json — Task Execution Graph

The supervisor's source of truth for stage composition and stage
progress. Lives at `{TASK_DIR}/pipeline.json`. Written by the analyst
agent in Phase 1b+1c (merged analyst+planner), then mutated by the
supervisor at each stage boundary.

This file is the **execution graph** half of the per-task state split:
the **pointer state** lives in `register.json` (Phase F4); the
**execution graph** lives here. The two files are jointly the canonical
record of "what was planned" + "how far it has progressed".

## File Location

```
${STATE_DIR}/tasks/${TASK_ID}/pipeline.json
```

Wiped by `crew:setup` reset; preserved across `crew:update`.

## Schema

Canonical shape:

```json
{
  "schema_version":   1,
  "task":             "implement order API",
  "stages":           [["analyst"], ["backend"], ["reviewer"]],
  "completed_stages": 0,
  "needs_creation":   [],
  "stage_agent_status": {
    "1": {"designer": "completed", "backend": "completed"},
    "2": {"frontend": "completed"}
  },
  "host_task_ids":    [
    {"designer": "task-abc", "backend": "task-def"},
    {"frontend": "task-ghi"},
    {"reviewer": "task-jkl"}
  ]
}
```

JSON Schema: `${AGENT_CREW_HOME}/schemas/pipeline.schema.json`. The
schema sets `additionalProperties: true` because dynamic-agent shapes
and capability-gated fields evolve faster than the schema does.

### Field catalog

| Field | Type | Required | Producer | Notes |
|---|---|---|---|---|
| `schema_version` | integer (const 1) | optional in v1 | analyst (post-F4) | Pre-F4 pipeline.json omits this field; validators tolerate absence. |
| `task` | string | yes | analyst Step 6 | Original task description (mirror of `register.json.task`). |
| `stages` | array | yes | analyst Step 6 | 2D array — outer = sequential, inner = parallel-within-stage. Older files may have bare strings as inner elements; consumers normalize `stage if isinstance(stage, list) else [stage]`. |
| `completed_stages` | integer | yes (starts at 0) | analyst Step 6, supervisor-stages | 0-based count of stages whose terminal state was successful completion. Drives the resume logic in Phase 0. |
| `needs_creation` | array of objects | yes (may be `[]`) | analyst Step 6 / planner Step 3c | Per-entry: `{name, reason, role}`. Drives Phase 1.5 dynamic agent creation. |
| `stage_agent_status` | object | optional (created on first parallel write) | supervisor-stages Phase 2 | Outer key = 1-based stage index as a string; inner key = agent name; value = `completed \| crashed \| blocked`. |
| `host_task_ids` | array | optional (capability-gated) | supervisor-bootstrap Phase 1c-bis | Parallel to `stages`. Only present when `task_tools=true` and `TaskCreate` calls succeeded. Absence = DAG mirror disabled. |

## Lifecycle

### Created

Phase 1b+1c — the analyst agent writes the initial pipeline.json with
`stages`, `needs_creation`, `completed_stages=0`, and `task`. No
`stage_agent_status` or `host_task_ids` at this point.

### Mutated

| Phase / event | Field mutated | How |
|---|---|---|
| Phase 1c-bis (capability-gated) | `host_task_ids` | bulk write — one entry per stage, parallel array |
| Phase 2 per-agent completion (parallel stages) | `stage_agent_status["<i>"]["<agent>"]` | intermediate per-agent write |
| Phase 2 stage completion (single-agent or all-parallel-done) | `stage_agent_status` + `completed_stages` | single combined write |
| Phase 2 devops-skip | (no mutation) | devops stage exclusively handled by Phase 2.5 |

The supervisor-stages.md doc § Per-agent completion tracking specifies
exact write blocks.

## Concurrency

One supervisor process owns one `pipeline.json`. The two write paths
inside supervisor-stages.md (per-agent intermediate write, combined
stage-end write) are not atomic in the same sense as the F4
`register_update` helper — they use Python's `json.dump(open(...,
"w"))` which truncates-then-writes. The window for corruption from a
crash is microseconds. For MVP scope, this matches the
`session.json` concurrent-write guarantee documented in
`core/rules/task-injection.md` § Concurrent Write Safety.

The atomic-write upgrade for pipeline.json is **out of scope for F4**.
Future phases that need stronger guarantees should adopt the same
tempfile + rename pattern that `register_update` introduces in F4.

## Consumer Contract

Primary consumers:

- `core/agents/supervisor-bootstrap.md` Phase 0 — read `completed_stages` + `stage_agent_status` to drive resume.
- `core/agents/supervisor-stages.md` Phase 2 — read `stages`, write per-agent + per-stage status.
- `core/agents/supervisor-retry.md` Phase 2 — read `host_task_ids` for P7 crash classification.
- `core/commands/status.md` Step 6 — read `stages` + `completed_stages` for the stages list.

| Situation | Behavior |
|---|---|
| File absent at Phase 0 | Fresh run; supervisor proceeds through Phase 1a → analyst → file written. |
| File absent at Phase 2 (logic error) | BLOCKED — the supervisor halts. |
| `stages` empty | Analysis-only pipeline; Phase 2 is a no-op; Phase 2.5 displays the summary; Phase 3 writes result.md. |
| `host_task_ids` absent | DAG mirror disabled. Every host-tool call in Phase 1c-bis / Phase 2 / supervisor-retry P7 silently falls back to the file-based path. |
| Unknown top-level field | Forward-compat: tolerate. |
| Required field missing or wrong type | BLOCKED — the F4 schema validator catches this in Phase 0 (own-task file = hard halt). |

## Forward Compatibility

The schema is **permissive additive** (`additionalProperties: true`).
The analyst may emit dynamic-agent entries with fields beyond
`{name, reason, role}`. The supervisor preserves them on read-modify
cycles but does not interpret them.

Future phases that need stronger guarantees:

1. Bump `schema_version`.
2. Add explicit field declarations in this doc + schema.
3. Update analyst.md + planner.md + supervisor-* sub-modules.

## Related Files

- `core/agents/analyst.md` § Step 6 (pipeline.json writer)
- `core/agents/planner.md` § Step 4 (legacy planner path; still writes this shape)
- `core/agents/supervisor-bootstrap.md` § Phase 0 resume + Phase 1c-bis
- `core/agents/supervisor-stages.md` § Phase 2 stage execution
- `core/agents/supervisor-retry.md` § Stage Retry Rule (P7 host-status crash classifier)
- `core/scripts/validate-state-schema.py` (Phase F4 schema validator)
- `core/rules/state-files/register-json.md` (sibling pointer state)

Schema:

- `core/schemas/pipeline.schema.json`
