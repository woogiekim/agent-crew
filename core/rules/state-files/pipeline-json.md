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

### TDD parallel stage form

A single stage may opt into the **TDD parallel** dispatch contract by
using the object form below instead of a bare string or array:

```json
{
  "stages": [
    { "agents": ["backend"], "tdd_parallel": true },
    ["reviewer"]
  ]
}
```

When `tdd_parallel: true`, the supervisor co-spawns `test-writer`
alongside every agent listed in `agents` (single message, parallel
host dispatch). Both must reach `STATUS: completed` before the stage's
`completed_stages` counter increments. Either failure path triggers
the Stage Retry Rule per agent (selective retry).

Backwards compatibility: `tdd_parallel` defaults to `false`. The two
legacy stage shapes (`"backend"` as a bare string, `["designer",
"backend"]` as a list) continue to mean "no TDD parallel — sequential
spawn(s)". A stage object with `tdd_parallel: false` (or omitted) is
functionally identical to writing the `agents` list directly as the
stage entry. See `core/agents/supervisor-stages.md` § TDD Parallel
Dispatch for the spawn semantics.

### Sub-Task Fan-Out stage form (`parallelizable_units`)

A single stage may also opt into **sub-task fan-out** (a.k.a. "mini
fan-out within a single supervisor") by attaching a
`parallelizable_units` array to the object form. Each unit describes
one independent slice of the stage's work, and the supervisor spawns
one agent of the stage's type per unit in a single host message:

```json
{
  "stages": [
    {
      "agents": ["backend"],
      "parallelizable_units": [
        { "id": "orders",   "files": ["src/api/orders/**"],   "brief": "Add CRUD endpoints for orders." },
        { "id": "products", "files": ["src/api/products/**"], "brief": "Add CRUD endpoints for products." },
        { "id": "carts",    "files": ["src/api/carts/**"],    "brief": "Add CRUD endpoints for carts." }
      ]
    },
    ["reviewer"]
  ]
}
```

Unit object shape:

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Short slug (`u1`, `orders`, `products`). Unique within the stage. Used as the unit key in `stage_agent_status` writes and progress event details. |
| `files` | array of string | yes (may be `[]`) | Shell-style glob list of files the unit will touch. Used by the planner's pre-flight overlap check and by the supervisor's MVP conflict logger. May be empty if the unit creates only new files in a fresh subtree. |
| `brief` | string | yes | 1–2 sentence sub-task description handed to the unit's agent in place of the full stage prompt. |

Dispatch contract (see `core/agents/supervisor-stages.md` § Sub-Task
Fan-Out Dispatch for full pseudocode):

- `parallelizable_units` is **optional**. When absent, or when its
  length is `<= 1`, the stage runs exactly as it does today
  (single agent, or the existing parallel-agents / TDD parallel form).
  Pre-existing pipelines that omit the field are entirely unaffected.
- When length `N >= 2`, the supervisor spawns N agents of the stage's
  type (the first entry in `agents`) in a single host message —
  the same parallel-spawn convention used by the existing Parallel
  Agents and TDD Parallel paths.
- Each unit-agent receives the unit's `brief` and `files` glob list
  as additional inputs; per-unit completion is recorded in
  `stage_agent_status["<i>"]["<agent>:<unit_id>"]`.
- `completed_stages` advances only after **all N** units reach
  `completed`. Crashed units trigger per-unit (not whole-stage) retry
  via the Stage Retry Rule.

### Reviewer opt-out stage form (`requires_test_execution`)

A reviewer stage may opt out of Issue #3's test-execution requirement
by encoding itself as the object form with
`requires_test_execution: false`. The supervisor extracts this flag
when spawning the reviewer and passes it as the
`REQUIRES_TEST_EXECUTION` input — the reviewer then SKIPS Phase 0
(runner discovery), Phase 1 (test execution), and Phase 1.5
(cross-process path agreement check), running only the static review
(pre-Issue-#3 behavior).

```json
{
  "stages": [
    ["documenter"],
    { "agents": ["reviewer"], "requires_test_execution": false }
  ]
}
```

Backwards compatibility: `requires_test_execution` defaults to `true`.
When the field is absent — including all pipelines emitted before
Issue #3 — the supervisor passes `REQUIRES_TEST_EXECUTION: true` and
the reviewer runs the full test-execution path. Existing pipelines
keep working; the new behavior is purely additive.

Set the field to `false` ONLY for stages that genuinely have no
testable surface (docs-only, `.gitignore` / config-only, comment-only
edits). See `core/agents/planner.md` § Reviewer opt-out
(`requires_test_execution`) for the strict criteria. Setting `false`
on a code-touching stage defeats the Issue #3 quality loop and is a
planner discipline violation.

### Streaming Review stage form (`streaming_review`)

A stage object may also opt into **streaming review** by setting
`streaming_review: true`. When the flag is true AND the *next* stage in
`stages` is a single `reviewer` agent, the supervisor co-spawns the
reviewer in `MODE=streaming` alongside this stage's agent(s) in a single
host message. The reviewer polls `git log <pre-stage-head>..HEAD`
incrementally as new commits land, terminating once this stage's
implementer reports `completed` (one final drain follows). On joint
success, `completed_stages` advances by **2** in one update — the
trailing reviewer stage is consumed by the streaming dispatch and is
NOT re-run.

```json
{
  "stages": [
    { "agents": ["backend"], "streaming_review": true },
    ["reviewer"]
  ]
}
```

Backwards compatibility: `streaming_review` defaults to `false`. When
the field is absent, when it is false, or when the next stage is not a
single `reviewer` agent, dispatch is unchanged — the implementer runs
to completion and the reviewer stage spawns sequentially as before. See
`core/agents/supervisor-stages.md` § Streaming Review Dispatch for the
full spawn semantics and the termination/drain protocol.

### Interaction with `tdd_parallel`, `parallelizable_units`, and `streaming_review`

`tdd_parallel`, `parallelizable_units`, and `streaming_review` are
independent flags on the same stage-object form. The truth table the
supervisor honors (per implementer stage; `streaming_review` is then
overlaid on top — see the second table below):

| `tdd_parallel` | `parallelizable_units.length` | Dispatch |
|---|---|---|
| absent / false | absent / `<= 1` | Legacy single-agent (or bare-array parallel-agents) dispatch. |
| true | absent / `<= 1` | TDD Parallel — co-spawn test-writer + first implementer. |
| absent / false | `>= 2` | Sub-Task Fan-Out — N implementers, one per unit. |
| true | `>= 2` | Combined: N implementers spawned (one per unit) AND a single test-writer co-spawned for the stage (writes tests covering the contract shared across units). Documented as opt-in advanced mode in `core/agents/planner.md` § When to set parallelizable_units. |

For MVP, the planner is instructed to set **at most one** of
`tdd_parallel` / `parallelizable_units` per stage unless the
implementer-side contract is genuinely shared across units. When both
are set the supervisor still dispatches correctly, but the planner's
pre-flight checks become harder to reason about.

`streaming_review` is **orthogonal** to the two flags above and stacks
on top of the dispatch the truth table selects. The supervisor adds one
extra parallel reviewer agent to the single host message that the
selected dispatch would already issue:

| `streaming_review` | Selected dispatch (from table above) | Effective agents co-spawned in one host message |
|---|---|---|
| absent / false | any | unchanged — reviewer runs as a separate later stage |
| true | Legacy single-agent | implementer + reviewer (`MODE=streaming`) |
| true | TDD Parallel | test-writer + implementer + reviewer (3 concurrent) |
| true | Sub-Task Fan-Out (N units) | N implementers + reviewer (reviewer watches the single combined branch — for MVP, no per-unit reviewer fan-out) |
| true | TDD Parallel + Sub-Task Fan-Out (combined) | test-writer + N implementers + reviewer (advanced mode; documented but not auto-recommended) |

`streaming_review: true` is only honored when the *immediately
following* stage is a single `reviewer` agent (no other agents in that
stage). When the trailing stage is missing, contains more than one
agent, or names a non-reviewer agent, the supervisor logs a one-line
warning and falls through to the dispatch the first table selects
(reviewer runs sequentially in its own stage as today). This keeps the
flag safe to set even when the analyst guessed wrong about the
trailing-stage shape.

JSON Schema: `${AGENT_CREW_HOME}/schemas/pipeline.schema.json`. The
schema sets `additionalProperties: true` because dynamic-agent shapes
and capability-gated fields evolve faster than the schema does.

### Field catalog

| Field | Type | Required | Producer | Notes |
|---|---|---|---|---|
| `schema_version` | integer (const 1) | optional in v1 | analyst (post-F4) | Pre-F4 pipeline.json omits this field; validators tolerate absence. |
| `task` | string | yes | analyst Step 6 | Original task description (mirror of `register.json.task`). |
| `stages` | array | yes | analyst Step 6 | 2D array — outer = sequential, inner = parallel-within-stage. Each inner element may be (a) a bare string (legacy single-agent stage), (b) an array of strings (parallel-within-stage), or (c) an object `{ agents: [string,...], tdd_parallel: bool, parallelizable_units: [...], streaming_review: bool, requires_test_execution: bool }` (TDD parallel form and/or sub-task fan-out and/or streaming review and/or reviewer opt-out — see the four stage-form sections below). Consumers normalize: strings → `[stage]`, arrays → as-is, objects → `stage["agents"]` plus the `tdd_parallel`, `parallelizable_units`, `streaming_review`, and `requires_test_execution` flags. |
| `completed_stages` | integer | yes (starts at 0) | analyst Step 6, supervisor-stages | 0-based count of stages whose terminal state was successful completion. Drives the resume logic in Phase 0. |
| `needs_creation` | array of objects | yes (may be `[]`) | analyst Step 6 / planner Step 3c | Per-entry: `{name, reason, role}`. Drives Phase 1.5 dynamic agent creation. |
| `stage_agent_status` | object | optional (created on first parallel write) | supervisor-stages Phase 2 | Outer key = 1-based stage index as a string; inner key = agent name (legacy / TDD parallel form) or `agent:unit_id` (sub-task fan-out form); value = `completed \| crashed \| blocked`. |
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

One supervisor process owns one `pipeline.json`. However, during
**sub-task fan-out** (`parallelizable_units` with N >= 2), multiple
parallel unit agents may each return and trigger a `stage_agent_status`
write in rapid succession within the same supervisor. A naive
`json.dump(open(path, "w"))` approach (truncate-then-write) risks data
loss if two concurrent writes interleave.

### Atomic write requirement

**All writes to `pipeline.json` MUST use the tempfile + rename pattern.**
This is the same approach used by the `register_update` helper in
`supervisor-bootstrap.md`. The pattern guarantees that readers always
observe a complete, consistent JSON document:

```python
import json, os, tempfile

def write_pipeline_atomic(path: str, data: dict) -> None:
    """Write pipeline.json atomically via tempfile + os.replace()."""
    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".pipeline.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)   # atomic on POSIX (rename(2))
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise
```

Supervisor-stages.md encodes this as the `pipeline_write_atomic` helper
and uses it for all write sites:

- **Per-agent intermediate write** (parallel stages, fan-out unit status)
- **Combined stage-end write** (`stage_agent_status` + `completed_stages`)
- **Resolver-mediation write** (rewriting `parallelizable_units` after
  the resolver returns a resolved unit list)

Pre-F4 single-agent sequential pipelines were safe with truncate-then-write
(no concurrent writers within the same supervisor). The atomic pattern
is fully backward-compatible and is now the required pattern for all write
sites to support the fan-out paths introduced later.

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
