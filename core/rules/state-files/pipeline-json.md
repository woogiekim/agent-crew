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
  "stages":           [{"agents": ["backend"], "tdd_parallel": true}, ["reviewer"]],
  "completed_stages": 0,
  "needs_creation":   [],
  "decision_context": {
    "need_analysis": {
      "can_solve_without_code": "no",
      "existing_project_code": "no",
      "framework_functionality": "no",
      "standard_library": "no",
      "configuration": "no",
      "infrastructure": "no",
      "existing_api": "no",
      "delete_instead": "no"
    },
    "capability_search": [
      "existing_project_code",
      "existing_utilities",
      "language_features",
      "standard_library",
      "framework_features",
      "installed_libraries",
      "platform_capabilities",
      "infrastructure_configuration"
    ],
    "diff_budget": {
      "category": "S",
      "rationale": "Smallest complete change that satisfies every assigned AC."
    },
    "will_do": ["Add the requested endpoint."],
    "will_not_do": ["No schema change.", "No new dependency."],
    "selected_solution": "Small implementation after reuse/configuration search.",
    "new_code_allowed_reason": "No existing capability satisfies the request."
  },
  "stage_agent_status": {
    "1": {"test-writer": "completed", "backend": "completed"}
  },
  "host_task_ids":    [
    {"test-writer": "task-abc", "backend": "task-def"},
    {"reviewer": "task-jkl"}
  ],
  "requires_delegation_fidelity": false,
  "requires_human_acceptance": false,
  "eval_command": ""
}
```

### Minimal-change decision context

`decision_context` records the analyst/planner's minimal-change decision for
mutating implementation work. It is optional for legacy state and non-mutating
pipelines, but newly planned implementation pipelines must include it.

The field is intentionally stored inside `pipeline.json` instead of a separate
proof artifact. It lets the planning-time gate verify that the pipeline tried
reuse, configuration, deletion, platform capabilities, and smaller diffs before
new code.

Planning-time validation:

- `need_analysis` must answer every question.
- `capability_search` must preserve the documented search order.
- `diff_budget.category` must be `XS`, `S`, `M`, `L`, or `XL`.
- `will_do`, `will_not_do`, and `selected_solution` must be non-empty.
- Implementation stages require `new_code_allowed_reason`.
- If any Need Analyzer answer is `yes`, implementation stages are invalid; the
  planner must recommend that non-code/reuse/configuration/deletion route first.
- `L` and `XL` budgets require `smaller_alternatives_rejected`.

### TDD parallel stage form

A single code implementation stage uses the **TDD parallel** dispatch
contract by using the object form below instead of a bare string or
array:

```json
{
  "stages": [
    {
      "agents": ["backend"],
      "tdd_parallel": true,
      "acceptance_criteria": ["AC-001"]
    },
    ["reviewer"]
  ]
}
```

When `tdd_parallel: true`, the supervisor co-spawns `test-writer`
alongside every agent listed in `agents` (single message, parallel
host dispatch). Both must reach `STATUS: completed` before the stage's
`completed_stages` counter increments. Either failure path triggers
the Stage Retry Rule per agent (selective retry).

Coverage contract: `test-writer` owns the stage's
`{TASK_DIR}/context/test-coverage.md` matrix and maps the PRD contract
to 100% changed-surface coverage evidence. The code implementer owns
keeping its implementation inside that matrix, and the immediately
following quality gate owns enforcement. The normal gate is a solo
`["reviewer"]`; the extended QA gate is `qa-owner` in verify mode followed
by a solo `["reviewer"]`.

Planning contract: newly emitted mutating code implementation pipelines
must use this form for each backend, frontend, or custom implementer
stage, each TDD stage must contain exactly one code implementer, every
PRD `AC-*` item must appear in at least one implementation or QA-verification
stage's `acceptance_criteria`, and the pipeline must include a later reviewer
stage. Run
`${AGENT_CREW_HOME}/scripts/pipeline-quality-plan-check.py --pipeline
${TASK_DIR}/pipeline.json` after analyst/planner emission. A failure
such as `implementation_stage_without_tdd_parallel` means the
supervisor must not continue to implementation.

Backwards compatibility: `tdd_parallel` defaults to `false` at the data
format level. The two legacy stage shapes (`"backend"` as a bare
string, `["designer", "backend"]` as a list) continue to mean "no TDD
parallel — sequential spawn(s)" when reading old state, devops-only
pipelines, or non-code stages. They are schema-compatible, but the
planner must not emit them for new code implementation stages. A stage
object with `tdd_parallel: false` (or omitted) is functionally
identical to writing the `agents` list directly as the stage entry. See
`core/agents/supervisor-stages.md` § TDD Parallel Dispatch for the spawn
semantics.

### QA owner stage form (`qa_mode`, `qa_loop_target`)

A pipeline may insert a built-in `qa-owner` stage to separate professional
QA ownership from final code review. QA planning runs before implementation;
QA verification runs after the TDD implementation stage and before the final
reviewer:

```json
{
  "stages": [
    { "agents": ["qa-owner"], "qa_mode": "plan" },
    {
      "agents": ["backend"],
      "tdd_parallel": true,
      "acceptance_criteria": ["AC-001"]
    },
    {
      "agents": ["qa-owner"],
      "qa_mode": "verify",
      "qa_loop_target": "previous_implementation",
      "acceptance_criteria": ["AC-001"]
    },
    ["reviewer"]
  ]
}
```

`qa_mode: "plan"` tells the QA owner to create
`context/qa-test-cases.md` and `context/qa-plan.md` from the PRD and
handoff before implementation starts.

`qa_mode: "verify"` tells the QA owner to execute the planned test cases,
write `context/qa-report.md`, and optionally write `context/qa-defects.md`.
When the QA owner returns `QA_STATUS: needs_changes` and the stage has
`qa_loop_target: "previous_implementation"`, the supervisor loops back to
the preceding implementation/TDD stage. The reviewer still runs after QA
passes and remains the final code quality gate.

Planning contract: a QA verify stage is valid as a quality gate only when it
is immediately followed by a solo reviewer stage. A code implementer followed
by QA verify without a following reviewer fails the planning-time quality
gate with `missing_pipeline_reviewer_after_qa_verify`.

### Optional quality evidence fields

`requires_delegation_fidelity: true` tells the runtime quality-loop gate to
require provider-neutral `delegation.jsonl` and `tool-events.jsonl` evidence
before a mutating completion can pass.

`requires_human_acceptance: true` tells QA/reviewer stages that
`context/human-acceptance-matrix.md` or `.json` must exist before completion.

`eval_command` records an Evaluation-Driven Development command. When present,
the completed task must write `context/evaluation-metrics.json`.

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
| `mutation_scope` | enum `read_only \| workspace_write` | optional (default `workspace_write`) | runtime + analyst | Explicit plan-bound mutation boundary inherited from `register.json`; never inferred from task prose. Validation fails when this value differs from `register.json`, or when a `read_only` plan contains a mutating Agent. |
| `stages` | array | yes | analyst Step 6 | 2D array — outer = sequential, inner = parallel-within-stage. Each inner element may be (a) a bare string (legacy single-agent stage), (b) an array of strings (parallel-within-stage), or (c) an object `{ agents: [string,...], tdd_parallel: bool, parallelizable_units: [...], streaming_review: bool, requires_test_execution: bool, qa_mode: string, qa_loop_target: string }` (TDD parallel form and/or sub-task fan-out and/or streaming review and/or reviewer opt-out and/or QA owner mode — see the stage-form sections above). Consumers normalize: strings → `[stage]`, arrays → as-is, objects → `stage["agents"]` plus the supported flags. |
| `completed_stages` | integer | yes (starts at 0) | analyst Step 6, supervisor-stages | 0-based count of stages whose terminal state was successful completion. Drives the resume logic in Phase 0. |
| `needs_creation` | array of objects | yes (may be `[]`) | analyst Step 6 / planner Step 3c | Per-entry: `{name, reason, role}`. Drives Phase 1.5 dynamic agent creation. |
| `stage_agent_status` | object | optional (created on first parallel write) | supervisor-stages Phase 2 | Outer key = 1-based stage index as a string; inner key = agent name (legacy / TDD parallel form) or `agent:unit_id` (sub-task fan-out form); value = `completed \| crashed \| blocked`. |
| `host_task_ids` | array | optional (capability-gated) | supervisor-bootstrap Phase 1c-bis | Parallel to `stages`. Only present when `task_tools=true` and `TaskCreate` calls succeeded. Absence = DAG mirror disabled. |

## Lifecycle

### Created

Phase 1b+1c — the analyst agent writes the initial pipeline.json with
`stages`, `needs_creation`, `completed_stages=0`, `task`, and the inherited
`mutation_scope`. No
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
- `core/agents/supervisor-retry.md` Phase 3 Step 2b (issue #128) — pass `host_task_ids` plus `host-task-id.txt` plus `result.md` to `core/scripts/reconcile-host-tasks.py`, which emits a plan listing every `(host_task_id, target_status)` transition the supervisor's defensive sweep should perform. The helper is a pure planner and never calls the host directly.
- `core/commands/status.md` Step 3S.bis (snapshot opportunistic) + Step 4S.5 (collect exhaustive) — same `reconcile-host-tasks.py` invocation. These call sites cover the case where a supervisor crashed before its own Phase 3 sweep could run.
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
