# register.json — Task State Pointer File

Per-task hot-slot pointer file. The supervisor and external tooling
consult `register.json` for the answer to "what is the current state of
this task?" without having to parse `pipeline.json` (execution graph) or
the per-stage handoff content (`handoff.md`). Introduced in Phase F4.

Pointer-only by design: this file does NOT duplicate the execution-graph
content of `pipeline.json` or the freeform stage content of `handoff.md`.
It cleanly separates "what is the current state of this task" from "what
is the execution plan and how have stages progressed".

## File Location

```
${STATE_DIR}/tasks/${TASK_ID}/register.json
```

Where `STATE_DIR = ${AGENT_CREW_HOME}/state/${PROJECT_NAME}`. Sits
alongside `pipeline.json`, `progress.log`, `progress.buffer.jsonl`, and
the `context/`, `archive/` subdirectories in the per-task directory.

Created on Phase 0 of every new task (after path resolution, before
capability bootstrap). Updated atomically at each phase boundary via
the `register_update` helper in `core/agents/supervisor-bootstrap.md`.
Wiped by `crew:setup` reset (same path glob as the rest of the task
directory); preserved across `crew:update`.

## Schema

Canonical shape:

```json
{
  "schema_version":      1,
  "task_id":             "20260516-012345-0",
  "session_id":          "20260516-012345",
  "task":                "implement order API",
  "branch":              "feat/implement-order-api",
  "project_root":        "/path/to/project",
  "task_dir":            "/path/to/state/.../tasks/20260516-012345-0",
  "execution_mode":      "single",
  "current_phase":       "phase_2",
  "approval_status":     "pending",
  "verification_status": "not_started",
  "requirements_path":   "{task_dir}/context/requirements.md",
  "analysis_path":       "{task_dir}/context/analysis.md",
  "prd_path":            "{task_dir}/context/prd.md",
  "pipeline_path":       "{task_dir}/pipeline.json",
  "handoff_path":        "{task_dir}/handoff.md",
  "progress_log_path":   "{task_dir}/progress.log",
  "progress_buffer_path":"{task_dir}/progress.buffer.jsonl",
  "result_path":         "{task_dir}/result.md",
  "approval_path":       "{task_dir}/context/approval.md",
  "start_head_path":     "{task_dir}/context/start-head.txt",
  "modified_files":      [],
  "blocked_by":          []
}
```

JSON Schema: `${AGENT_CREW_HOME}/schemas/register.schema.json`.

### Field catalog

| Field | Type | Required | Source / Rationale |
|---|---|---|---|
| `schema_version` | integer (const 1) | yes | bumped on incompatible field changes; readers tolerate higher versions with a warning |
| `task_id` | string | yes | matches the supervisor's `TASK_ID` input; pattern `{YYYYMMDD}-{HHMMSS}[-{idx}]` |
| `session_id` | string | yes | derived as `${TASK_ID%-*}` when not passed by the orchestrator |
| `task` | string | yes | original task description |
| `branch` | string | yes | working branch name per `core/rules/branch-naming.md` |
| `project_root` | string (absolute path) | yes | may be a worktree path in `parallel` execution mode |
| `task_dir` | string (absolute path) | yes | self-referential; useful for tooling that received only register.json |
| `execution_mode` | enum `single \| parallel` | yes | matches the `EXECUTION_MODE` supervisor input |
| `current_phase` | enum (see below) | yes | updated at each phase boundary |
| `approval_status` | enum `not_required \| pending \| approved \| cancelled` | yes | bumped by Phase 1d and Phase 2.5 gates |
| `verification_status` | enum `not_started \| running \| passed \| failed \| skipped` | yes | bumped by reviewer stage entry/exit |
| `requirements_path` ... `start_head_path` | string | optional | path pointers populated from supervisor-bootstrap variables; the files themselves may not exist yet |
| `modified_files` | array of strings | optional (default `[]`) | cumulative list of files modified by stage agents, deduplicated; populated from `git status --short` diff against `start-head.txt` |
| `blocked_by` | array of strings | optional (default `[]`) | populated only when `current_phase == blocked`; multi-entry when multiple sub-causes apply |

### `current_phase` enum

| Value | Set at |
|---|---|
| `phase_0` | initial Phase 0 write |
| `phase_1a` | Phase 1a entry (requirement collection) |
| `phase_1bc` | Phase 1b+1c entry (analyst merged spawn) |
| `phase_1c_bis` | Phase 1c-bis entry (per-stage host task DAG mirror) |
| `phase_1d` | Phase 1d entry (plan approval gate) |
| `phase_1_5` | Phase 1.5 entry (dynamic agent creation) |
| `phase_2` | Phase 2 entry (stage execution) |
| `phase_2_5` | Phase 2.5 entry (stage action gate) |
| `phase_3` | Phase 3 entry (close-out) |
| `completed` | Phase 3 successful exit |
| `blocked` | any BLOCKED Recovery path |

## Lifecycle

### Created

Initial write happens in `supervisor-bootstrap.md` Phase 0, after path
resolution and before capability bootstrap. Initial state:

- `current_phase = phase_0`
- `approval_status = not_required` (later bumped to `pending` if a gate fires)
- `verification_status = not_started`
- all `*_path` fields populated from the resolved Phase 0 variables
- `modified_files = []`
- `blocked_by = []`

### Updated

Each phase boundary calls the `register_update` helper (defined in
`supervisor-bootstrap.md` Phase 0, sibling to `log_progress`). The
helper performs an atomic read-modify-tempfile-rename sequence so
concurrent supervisors (in parallel mode, each owning its own
`register.json`) never race — and a crash mid-write never corrupts the
file.

Write sites:

| Phase / event | Field bumped | New value |
|---|---|---|
| Phase 0 init | `current_phase` | `phase_0` |
| Phase 1a entry | `current_phase` | `phase_1a` |
| Phase 1b+1c entry | `current_phase` | `phase_1bc` |
| Phase 1c-bis entry | `current_phase` | `phase_1c_bis` |
| Phase 1d entry | `current_phase`, `approval_status` | `phase_1d`, `pending` |
| Phase 1d approve | `approval_status` | `approved` |
| Phase 1d cancel | `approval_status`, `current_phase` | `cancelled`, `blocked` |
| Phase 1.5 entry | `current_phase` | `phase_1_5` |
| Phase 2 entry | `current_phase` | `phase_2` |
| Reviewer STAGE entry | `verification_status` | `running` |
| Reviewer STAGE_DONE (APPROVED) | `verification_status` | `passed` |
| Reviewer STAGE_DONE (NEEDS_CHANGES + budget exhausted) | `verification_status` | `failed` |
| Each STAGE_DONE | `modified_files` | union with `git status --short` diff |
| Phase 2.5 entry | `current_phase` | `phase_2_5` |
| Phase 2.5 devops-gate prompt | `approval_status` | `pending` |
| Phase 2.5 devops-gate approve | `approval_status` | `approved` |
| Phase 2.5 devops-gate cancel | `approval_status` | `cancelled` |
| Phase 3 entry | `current_phase` | `phase_3` |
| Phase 3 success exit | `current_phase` | `completed` |
| BLOCKED Recovery any path | `current_phase`, `blocked_by` | `blocked`, `[reason]` |

The non-reviewer pipelines (analysis-only, tooling-only with no
reviewer stage) finish with `verification_status = skipped`. The
register helper sets this once Phase 3 starts and no reviewer ran.

## Concurrency

A single supervisor process owns one `register.json`. Multiple
supervisors run in their own task directories — no shared file. The
atomic-write helper (tempfile + `os.rename()`) guarantees:

1. A reader that opens the file mid-write either sees the old version
   or the new version, never a truncated middle state.
2. A supervisor crash between read and rename leaves the prior file
   intact.

Same assumption as `pipeline.json` (which uses similar JSON dump in
the supervisor-stages.md Phase 2 write block) — F4 strengthens the
guarantee for register.json specifically because every phase boundary
writes it.

## Consumer Contract

Consumers (primarily `core/commands/status.md` and external tooling):

| Situation | Behavior |
|---|---|
| File absent | Pre-F4 task directory. Fall back to parsing `pipeline.json` + `progress.log`. |
| File present, `schema_version == 1` | Validate against `register.schema.json`. |
| File present, `schema_version > 1` | Forward-compat: render best-effort, warn but do not abort. |
| Required field missing | Warn to stderr; treat as malformed; fall back to file-by-file parsing. |
| Optional field missing | Apply default (`modified_files = []`, `blocked_by = []`, optional path = ""). |
| Unknown `current_phase` enum value | Forward-compat: render verbatim. |
| Malformed JSON | Skip; warn once per file; never abort the caller. |

## Forward Compatibility

The schema is **strict additive only** (`additionalProperties: false`).
F4 controls every register.json write site, so unknown fields are a
defect — not a forward-compat surface. Future phases that need new
fields:

1. Bump `schema_version`.
2. Add the field with explicit type + default + position in the
   register_update helper.
3. Update `register.schema.json`.
4. Update this doc's field catalog.

The validator must continue to accept v1 files for one full refactor
phase after a bump (i.e., bumps are advisory; old files remain valid
until explicitly removed).

## Related Files

Producer:

- `core/agents/supervisor-bootstrap.md` Phase 0 (initial write + `register_update` helper definition)
- `core/agents/supervisor-stages.md` (Phase 2 per-stage updates)
- `core/agents/supervisor-retry.md` (Phase 3 + BLOCKED Recovery final updates)

Consumers:

- `core/commands/status.md` Step 1d (prefer register.json for state
  detection; fall back to pipeline.json + progress.log on absence)
- `core/scripts/validate-state-schema.py` (Phase F4 schema validator)

Sibling state-file docs:

- `core/rules/state-files/progress-buffer-jsonl.md`
- `core/rules/state-files/pipeline-json.md`
- `core/rules/state-files/session-json.md`
- `core/rules/state-files/capabilities-json.md`

Schema:

- `core/schemas/register.schema.json`
