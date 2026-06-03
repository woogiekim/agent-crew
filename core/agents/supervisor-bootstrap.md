# Supervisor — Bootstrap & Setup (Phases 0 → 1.5)

> This module is read by the `supervisor` agent at spawn time when no
> `PIPELINE_PATH` exists yet (fresh run). On a resuming run, only Phase 0
> is executed from this module — the agent skips Phases 1a, 1b+1c,
> 1c-bis, 1d, and 1.5 and proceeds directly to Phase 2 (which lives in
> `supervisor-stages.md`).
>
> All phase names defined here (Phase 0 through Phase 1.5) are referenced
> by sibling modules. The Stage Retry Rule and Phase 3 close-out live in
> `supervisor-retry.md`.

---

### Phase 0: Resume Check + Context Bootstrap

**Read-once context bootstrap**: Resolve all runtime paths once at startup and
store them as variables. Do not re-read or re-resolve these paths in later phases.
This block runs FIRST so the `log_progress` helper (defined below) can access
`TASK_DIR`, `SESSION_ID`, etc. when the first canonical `STARTED` event fires.

```bash
# Resolve paths once — reuse these variables throughout all phases
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
QUALITY_RULE_PATH="${AGENT_CREW_HOME}/rules/quality-loop.md"
PIPELINE_PATH="${TASK_DIR}/pipeline.json"
HANDOFF_PATH="${TASK_DIR}/handoff.md"
PRD_PATH="${TASK_DIR}/context/prd.md"
PROJECT_NAME=$(basename "${PROJECT_ROOT}")
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
CAPABILITIES_PATH="${STATE_DIR}/capabilities.json"

# Phase F5: derive SESSION_ID for the structured progress buffer's trace_id.
# Parallel runs receive SESSION_ID as a supervisor input; single-task runs
# fall through to stripping the `-N` suffix from TASK_ID (orchestrator-spawned
# tasks always have TASK_ID = "{session_ts}-{idx}"). Ad-hoc manual invocations
# with no `-` suffix collapse SESSION_ID to TASK_ID (acceptable fallback).
SESSION_ID="${SESSION_ID:-${TASK_ID%-*}}"
```

These six variables (`QUALITY_RULE_PATH`, `PIPELINE_PATH`, `HANDOFF_PATH`,
`PRD_PATH`, `CAPABILITIES_PATH`, `STATE_DIR`) plus `SESSION_ID` must be
passed as-is to all sub-agents. Never re-derive them inline.

**Host capability bootstrap**: Read host capabilities (registry:
`core/rules/host-capabilities.md`; per-flag detail under
`core/rules/capabilities/`). Treat missing file or parse errors as all-false
flags. Three flags are loaded once in Phase 0 and reused through every later
phase — never re-read the file inline.

```bash
# Single Python process reads capabilities.json once and emits all three flags,
# eliminating two extra python3 process startups compared to three separate calls.
read -r HAS_TASK_TOOLS HAS_AGENT_BACKGROUND HAS_MONITOR_TOOL HAS_COST_TRACKING < <(python3 -c "
import json
try:
    c = json.load(open('${CAPABILITIES_PATH}'))
    print(
        '1' if c.get('task_tools') else '0',
        '1' if c.get('agent_background') else '0',
        '1' if c.get('monitor_tool') else '0',
        '1' if c.get('cost_tracking') else '0',
    )
except Exception:
    print('0 0 0 0')
" 2>/dev/null)
```

**Deferred tool schema eager-load (Phase B1)**: Claude Code registers task
tools (`TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`, `TaskOutput`) as
deferred — their schemas are not loaded until `ToolSearch` is called.
Calling them without loading their schemas results in a silent
`InputValidationError` that skips the call entirely. When `HAS_TASK_TOOLS == 1`,
load all task tool schemas immediately after the capability read, before any
phase that issues a task tool call:

```text
if [ "${HAS_TASK_TOOLS}" = "1" ]; then
  ToolSearch("select:TaskCreate,TaskUpdate,TaskGet,TaskList,TaskOutput")
fi
```

This is a one-time bootstrap call. Every subsequent `TaskCreate`, `TaskUpdate`,
`TaskGet`, `TaskList`, and `TaskOutput` call in all phases reuses the loaded
schema and will not silently fail.

`HAS_TASK_TOOLS` gates every `TaskCreate` / `TaskList` / `TaskGet` /
`TaskUpdate` call. `HAS_AGENT_BACKGROUND` gates the background fan-out path in
`run.md` Step 6. `HAS_MONITOR_TOOL` gates the `TaskOutput` consumption in
`crew:status`. `HAS_COST_TRACKING` gates the cost circuit breaker in
`supervisor-retry.md` § Cost Circuit Breaker (Phase 3.3). Every call site MUST
check the relevant flag and fall back to the
file-based primary (`progress.log`, `approval.md`, `pipeline.json`) when the
flag is `0`.

### Stage timeout budget (Phase I11)

Read the per-stage wall-clock budget from the environment. Absence (or
zero) means the timeout is disabled and the supervisor behaves exactly
as it did before Phase I11. When set, the value is the maximum number
of seconds a single stage iteration (including all retries) may run
before the supervisor halts with `BLOCKER: stage_timeout`.

```bash
STAGE_TIMEOUT_SECONDS="${AGENT_CREW_STAGE_TIMEOUT_SECONDS:-0}"
case "${STAGE_TIMEOUT_SECONDS}" in
  ''|*[!0-9]*) STAGE_TIMEOUT_SECONDS=0 ;;  # ignore non-integer
esac
```

`STAGE_TIMEOUT_SECONDS == 0` is the absence-tolerant default: the Stage
Retry Rule's timeout check (see `supervisor-retry.md` § Stage Timeout)
becomes a no-op and existing pipelines run unchanged. Recommended
value when enabling: `1800` (30 minutes per stage), which matches
typical agent invocation costs without false-positive timeouts.

If `HAS_TASK_TOOLS == 1`, the supervisor registers itself with the host's task
surface so users can see live pipeline progress in the host UI:

1. **Call `TaskCreate` once at the very start of Phase 0** (right after the
   `STARTED` log line). The supervisor always creates its own host task — the
   orchestrator never pre-creates one on behalf of the supervisor:

   ```text
   TaskCreate(
     subject="crew:run — {TASK truncated to 60 chars}",
     description="agent-crew supervisor pipeline for TASK_ID={TASK_ID}. "
                 "File source of truth: {TASK_DIR}/progress.log",
     activeForm="Running crew:run pipeline",
     metadata={"task_id": "{TASK_ID}", "branch": "{BRANCH}",
               "task_dir": "{TASK_DIR}"}
   )
   ```

   Capture the returned task id as `HOST_TASK_ID` and write it once to
   `${TASK_DIR}/host-task-id.txt` so other phases can update it without re-issuing
   TaskCreate.

   After writing `host-task-id.txt`, delete the boot sentinel written by the
   orchestrator (if present):

   ```bash
   rm -f "${TASK_DIR}/supervisor-pending.txt"
   ```

   This deletion is always safe (`rm -f` is idempotent) and applies regardless
   of `HAS_TASK_TOOLS` — the sentinel signals "supervisor reached Phase 0",
   not specifically "TaskCreate ran". When `HAS_TASK_TOOLS == 0`, delete the
   sentinel immediately after logging the `STARTED` event.

2. At Phase 3 completion (after `result.md` is written), call
   `TaskUpdate` with the terminal status derived from `result.md`:
   - `STATUS: completed` → `TaskUpdate(taskId=HOST_TASK_ID, status="completed")`
   - `STATUS: blocked` → `TaskUpdate(taskId=HOST_TASK_ID, status="blocked")`
   - `STATUS: CANCELLED` → `TaskUpdate(taskId=HOST_TASK_ID, status="completed")`

   This call is gated by `[ -f "${TASK_DIR}/host-task-id.txt" ]` — skip entirely
   when the file is absent. The full implementation lives in Phase 3 Step 2b of
   `supervisor-retry.md`.

   Under background fan-out (P4), `crew:status --collect` reads
   `TaskGet(HOST_TASK_ID).status` as the primary signal that the runner
   has finished. The collect loop exits when status is `"completed"`, `"blocked"`,
   or `"cancelled"` — so passing `status="blocked"` (not `"in_progress"`) is
   essential for blocked exits to unblock the collector.

When `HAS_TASK_TOOLS == 0`: delete the boot sentinel immediately after the
`STARTED` log event (before any Phase 1 work begins):

```bash
rm -f "${TASK_DIR}/supervisor-pending.txt"
```

If `HAS_TASK_TOOLS == 0` (or the file is missing): skip every `TaskCreate` /
`TaskUpdate` call. The file-based pipeline state remains the single source of
truth in both modes. **Never call `TaskCreate` outside this gated block.**

### Progress Mirroring (host-agnostic, three sinks)

Every progress event MUST be written to **three sinks** in a single helper
invocation:

1. `${TASK_DIR}/progress.log` — human-readable single-line log (append).
2. `stderr` — host-surface mirror (Claude Code's `TaskOutput`, plain
   terminals) with `[crew]` prefix. Independent of `task_tools` — always
   runs.
3. `${TASK_DIR}/progress.buffer.jsonl` — structured event buffer (one
   JSON object per line, Phase F5). Schema documented at
   `core/rules/state-files/progress-buffer-jsonl.md`. Consumed by
   `crew:status` Step 5 (preferred over `progress.log` when present).

```bash
log_progress() {
  local event="$1"
  local detail="$2"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # Sink 1: human-readable progress.log
  local line="${ts} | ${event} | ${detail}"
  echo "${line}" >> "${TASK_DIR}/progress.log"

  # Sink 2: stderr mirror
  echo "[crew] ${line}" >&2

  # Sink 3 (Phase F5): structured JSONL buffer.
  # Supervisor-local context with safe defaults so the helper never
  # crashes during Phase 0 / Phase 3 (when stage vars are unset).
  local _stage="${STAGE_INDEX:-0}"
  local _agent="${STAGE_AGENT:-}"
  local _attempt="${RETRY_ATTEMPT:-0}"
  local _session="${SESSION_ID:-${TASK_ID}}"
  local _trace="${_session}.${TASK_ID}.${_stage}.${_attempt}"

  # Event → status lookup (consumer-friendly default).
  local _status
  case "${event}" in
    STARTED)                                            _status="started" ;;
    PHASE|STAGE|STAGE_TDD_PARALLEL_STARTED|STAGE_FANOUT_STARTED|STAGE_FANOUT_UNIT_DONE|STAGE_FANOUT_RESOLVER_STARTED) _status="in_progress" ;;
    STAGE_DONE|STAGE_TDD_PARALLEL_DONE|STAGE_FANOUT_DONE|STAGE_FANOUT_RESOLVER_DONE|COMPLETED|HANDOFF_PAGEDOUT) _status="completed" ;;
    BLOCKED|COST_BLOCKED|STAGE_TIMEOUT|HANDOFF_PAGEOUT_FAILED|STAGE_FANOUT_BLOCKED) _status="failed" ;;
    RETRY)                                              _status="retry" ;;
    HANDOFF_PAGEOUT_SKIPPED)                            _status="skipped" ;;
    COST_WARN|HANDOFF_PAGEOUT|STATE_WARN|STAGE_FANOUT_CONFLICT) _status="warn" ;;
    *)                                                  _status="unknown" ;;
  esac

  # JSON-encode via Python heredoc — `detail` may contain quotes,
  # backticks, em-dashes, Unicode. Shell string concatenation for JSON
  # is forbidden (same convention as core/hooks/cost-tracker.sh).
  python3 - "${TASK_DIR}/progress.buffer.jsonl" \
            "${ts}" "${_trace}" "${TASK_ID}" "${_session}" \
            "${event}" "${_stage}" "${_agent}" "${_attempt}" \
            "${_status}" "${detail}" <<'PYEOF' 2>/dev/null || true
import json, sys
(path, ts, trace_id, task_id, session_id, event,
 stage, agent, attempt, status, detail) = sys.argv[1:12]
row = {
    "ts":         ts,
    "trace_id":   trace_id,
    "task_id":    task_id,
    "session_id": session_id,
    "event":      event,
    "stage":      int(stage) if stage.lstrip("-").isdigit() else 0,
    "agent":      agent,
    "attempt":    int(attempt) if attempt.lstrip("-").isdigit() else 0,
    "status":     status,
    "detail":     detail,
    "files":      [],
}
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
PYEOF
}
# Usage: log_progress "PHASE" "1b — Analysis + Planning (merged)"
```

### register.json update helper (Phase F4)

The supervisor maintains a slim per-task pointer file at
`${TASK_DIR}/register.json` (schema: `core/rules/state-files/register-json.md`).
Every phase boundary calls `register_update` to bump a single field
atomically.

```bash
# register_update <field> <value>          — set string/enum field
# register_update <field> --json <jsv>     — set field to JSON value (array, etc.)
#
# Atomic write via tempfile + os.rename(). Auto-seeds register.json
# with sensible defaults when the file is absent (first-call init).
register_update() {
  local field="$1"
  shift
  local raw_kind="string"
  local value="$1"
  if [ "${1:-}" = "--json" ]; then
    raw_kind="json"
    value="$2"
  fi

  python3 - "${TASK_DIR}/register.json" "${field}" "${raw_kind}" "${value}" \
           "${TASK_ID}" "${SESSION_ID:-${TASK_ID}}" "${TASK:-}" "${BRANCH:-}" \
           "${PROJECT_ROOT:-}" "${TASK_DIR}" "${EXECUTION_MODE:-single}" <<'PYEOF' 2>/dev/null || true
import json, os, sys, tempfile

(path, field, kind, raw_value, task_id, session_id, task, branch,
 project_root, task_dir, execution_mode) = sys.argv[1:12]

try:
    with open(path, "r", encoding="utf-8") as f:
        reg = json.load(f)
except Exception:
    reg = {
        "schema_version":      1,
        "task_id":              task_id,
        "session_id":           session_id,
        "task":                 task,
        "branch":               branch,
        "project_root":         project_root,
        "task_dir":             task_dir,
        "execution_mode":       execution_mode,
        "current_phase":        "phase_0",
        "approval_status":      "not_required",
        "verification_status":  "not_started",
        "requirements_path":    f"{task_dir}/context/requirements.md",
        "analysis_path":        f"{task_dir}/context/analysis.md",
        "prd_path":             f"{task_dir}/context/prd.md",
        "pipeline_path":        f"{task_dir}/pipeline.json",
        "handoff_path":         f"{task_dir}/handoff.md",
        "progress_log_path":    f"{task_dir}/progress.log",
        "progress_buffer_path": f"{task_dir}/progress.buffer.jsonl",
        "result_path":          f"{task_dir}/result.md",
        "approval_path":        f"{task_dir}/context/approval.md",
        "start_head_path":      f"{task_dir}/context/start-head.txt",
        "modified_files":       [],
        "blocked_by":           [],
    }

if kind == "json":
    try:
        value = json.loads(raw_value)
    except Exception:
        value = raw_value
else:
    value = raw_value

# Array-valued fields are append-with-dedupe.
if field in ("modified_files", "blocked_by"):
    if isinstance(value, list):
        existing = list(reg.get(field, []))
        for v in value:
            if v not in existing:
                existing.append(v)
        reg[field] = existing
    else:
        existing = list(reg.get(field, []))
        if value and value not in existing:
            existing.append(value)
        reg[field] = existing
else:
    reg[field] = value

fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".register.",
                            suffix=".tmp")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.rename(tmp, path)
except Exception:
    try:
        os.unlink(tmp)
    except Exception:
        pass
    raise
PYEOF
}
# Usage:
#   register_update current_phase phase_2
#   register_update approval_status pending
#   register_update modified_files --json '["core/foo.py"]'
#   register_update blocked_by --json '["state_schema_invalid"]'
```

Every progress-event emit in the rest of this module (and in
`supervisor-stages.md`, `supervisor-retry.md`) is a `log_progress` call —
all three sinks fire. Where an inline `echo … >> "${TASK_DIR}/progress.log"`
block appears as documentation shorthand in older sections, the runtime
call is still `log_progress`. Stdout remains reserved for the
orchestrator's final return value — never write progress events to stdout.

**Emit the canonical `STARTED` event** as the first action after the helper
is defined. This is the first event of the task — both `progress.log` and
`progress.buffer.jsonl` are created on this call:

```bash
log_progress "STARTED" "{TASK truncated to 60 chars}"
```

### State-schema validation (Phase F4)

After `STARTED` (so the helper can emit warnings), run the state-file
validator. Mixed-mode policy: own-task files (`register.json`,
`pipeline.json`, `progress.buffer.jsonl`) hard-halt on type errors or
missing required fields; cross-task files (`session.json`,
`capabilities.json`) warn but continue.

```bash
VALIDATOR="${AGENT_CREW_HOME}/scripts/validate-state-schema.py"
if [ -f "${VALIDATOR}" ]; then
  VALIDATION_OUTPUT=$(python3 "${VALIDATOR}" \
       --state-dir "${STATE_DIR}" \
       --task-dir  "${TASK_DIR}" \
       --format    text 2>&1)
  VALIDATION_RC=$?
  case "${VALIDATION_RC}" in
    0)
      : # all clean
      ;;
    1)
      log_progress "STATE_WARN" "schema validator warnings (rc=1)"
      printf '%s\n' "${VALIDATION_OUTPUT}" >&2
      ;;
    2)
      log_progress "BLOCKED" "schema validator errors (rc=2)"
      printf '%s\n' "${VALIDATION_OUTPUT}" >&2
      register_update current_phase blocked
      register_update blocked_by --json '["state_schema_invalid"]'
      cat > "${TASK_DIR}/result.md" <<EOF
# ${TASK}

STATUS: blocked
BLOCKER: state_schema_invalid
DETAIL: validate-state-schema.py reported errors at Phase 0. See
        ${TASK_DIR}/progress.log for the full validator output.
EOF
      exit 1
      ;;
    *)
      log_progress "STATE_WARN" "schema validator unavailable (rc=${VALIDATION_RC})"
      ;;
  esac
fi
```

### Initial register.json seed (Phase F4)

Seed the register file once after STARTED. On fresh runs this creates
`register.json` with `current_phase=phase_0`. On pre-F4 resumes (no
register.json yet) it backfills the file; the next stage transition's
`register_update` will then advance `current_phase` correctly. On F4+
resumes the existing file is rewritten with the same fields (no data
loss — register_update preserves all other fields).

```bash
if [ ! -f "${TASK_DIR}/register.json" ]; then
  register_update current_phase phase_0
fi
```

### Git-repository guard (Phase 0)

Before proceeding to any planning or git operations, verify that `PROJECT_ROOT`
is a valid git repository. If it is not, the supervisor cannot record a start
HEAD, create a branch, or commit changes — the pipeline will fail mid-run with
confusing git errors.

Check immediately after the register seed and before the resume check:

```bash
if ! git -C "${PROJECT_ROOT}" rev-parse --git-dir >/dev/null 2>&1; then
  log_progress "BLOCKED" "PROJECT_ROOT is not a git repository: ${PROJECT_ROOT}"
  register_update current_phase blocked
  register_update blocked_by --json '["not_a_git_repo"]'
  cat > "${TASK_DIR}/result.md" <<EOF
# ${TASK}

STATUS: blocked
BLOCKER: not_a_git_repo
DETAIL: ${PROJECT_ROOT} is not a git repository.
        Initialize it first, then retry crew:run:

          cd ${PROJECT_ROOT}
          git init
          git commit --allow-empty -m "init"

EOF
  exit 1
fi
```

This guard is exempt from the resume-skip rule: even on a resume, `PROJECT_ROOT`
must still be a valid git repo or the pipeline cannot continue.

**Resume check**: If `PIPELINE_PATH` already exists, resume from that state
instead of creating a new plan from scratch.

Resume rules:

- If `PIPELINE_PATH` exists: read `completed_stages` and `stage_agent_status`, then
  **skip Phases 1a, 1b+1c, 1d, and 1.5 entirely and jump directly to Phase 2**.
  Planning, analysis, and plan approval were already completed in the prior run.
- If `PIPELINE_PATH` does not exist: proceed normally through Phases 1a → 1b+1c → 1d → 1.5 → 2.
- Never duplicate the planner step for an already initialized task.
- For parallel stages, use `stage_agent_status["{i}"]` to determine which individual
  agents already completed. On resume, skip only those agents — do not re-run them.
  Only agents missing from the map (or with status other than `"completed"`) are retried.

`PIPELINE_PATH` tracks per-agent completion with this structure:

```json
{
  "completed_stages": 2,
  "stage_agent_status": {
    "1": {"test-writer": "completed", "backend": "completed"},
    "2": {"reviewer": "completed"}
  }
}
```

This prevents restarting already-finished agents when resuming after an interrupt.

#### Phase 0 resume capability preflight

When `PIPELINE_PATH` already exists at Phase 0, run the same capability
preflight used after fresh planning before jumping to Phase 2. This prevents an
interrupted or externally edited `pipeline.json` from bypassing role/tool
boundaries on resume.

```bash
if [ -f "${PIPELINE_PATH}" ]; then
  CAPABILITY_CHECK_OUTPUT=$(python3 "${AGENT_CREW_HOME}/scripts/pipeline-capability-check.py" \
    --pipeline "${PIPELINE_PATH}" \
    --manifest "${AGENT_CREW_HOME}/policies/agent-capabilities.json" \
    --agent-dir "${AGENT_CREW_HOME}/system/agents" \
    --agent-dir "${AGENT_CREW_HOME}/user/agents" \
    --format text 2>&1)
  CAPABILITY_CHECK_RC=$?

  if [ "${CAPABILITY_CHECK_RC}" -ne 0 ]; then
    log_progress "BLOCKED" "pipeline capability preflight failed on resume: ${CAPABILITY_CHECK_OUTPUT}"
    register_update current_phase blocked
    register_update blocked_by pipeline_capability_preflight_failed
    cat > "${TASK_DIR}/result.md" <<EOF
STATUS: BLOCKED
BLOCKER: pipeline_capability_preflight_failed
DETAIL: existing pipeline.json violates the agent capability manifest.

${CAPABILITY_CHECK_OUTPUT}
EOF
    exit 1
  fi
fi
```

### Phase 1: Analysis + Planning

> **Skip this entire Phase 1 (1a, 1b+1c, 1d) and Phase 1.5 when resuming** (i.e.,
> when `PIPELINE_PATH` already existed at Phase 0). Jump directly to Phase 2 using
> the `completed_stages` and `stage_agent_status` read in Phase 0.

#### Direct implementation bypass guard

For a fresh run (`PIPELINE_PATH` did not exist at Phase 0), there is no
"simple enough" shortcut around this phase. Existing requirements, including a
pre-populated `{TASK_DIR}/context/requirements.md`, may shorten Phase 1a but
must never skip Phase 1b+1c, Phase 1d, Phase 1.5, or Phase 2.

Before any implementation activity, the required fresh-run sequence is:

```text
Phase 1a requirement gate
Phase 1b+1c analyst planning spawn
pipeline.json + analysis.md + prd.md + handoff.md written
Phase 1d plan approval gate
Phase 1.5 custom-agent creation, if needed
Phase 2 stage-agent execution
reviewer stage completion
Phase 3 close-out
```

The supervisor must not write project code, invoke backend/frontend/designer
work inline, emit `PHASE | Implementation`, emit `STAGE_DONE | all layers`, or
write `STATUS: completed` until that sequence has reached the appropriate
stage-agent step. If that bypass pattern is about to occur, halt immediately:

```text
STATUS: blocked
BLOCKER: supervisor_pipeline_bypass_prevented
DETAIL: Fresh supervisor run attempted direct implementation before pipeline.json, plan approval, stage-agent execution, and reviewer completion.
```

#### Phase 1a: Requirement Collection Gate

Emit before checking:

```
[crew] {TASK_ID} | PHASE | 1a — Requirement collection
```

```bash
log_progress "PHASE" "1a — Requirement collection"
register_update current_phase phase_1a
```

**Check whether `REQUIREMENTS` was provided in the supervisor's own input.**

##### Case A — `REQUIREMENTS` is present

Skip both rounds below. Use the received `REQUIREMENTS` value as-is and proceed
directly to Phase 1b.

##### Case B — `REQUIREMENTS` is absent

> **NEVER-SKIP-WITHOUT-SUFFICIENCY-CHECK**: When REQUIREMENTS is absent, requirement
> *production* is mandatory — but the *agent invocation* is not. The gate is the
> sufficiency check below, not the agent call. The principle "REQUIREMENTS must
> exist before Phase 1b runs" is preserved; what changed is that well-specified
> TASK strings now skip the agent entirely and synthesize the block inline.

Run the sufficiency check first. Use the same deterministic helper that
`crew:run` Step 5.pre uses instead of loading a duplicate Python scoring block
into the supervisor prompt:

```bash
SUFFICIENCY=$(python3 "${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py" \
  --status "${TASK}")
POLICY=$(python3 "${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py" \
  --policy \
  --intensity "${AGENT_CREW_INTERACTION_INTENSITY:-balanced}" \
  "${TASK}")
```

The helper returns either `SUFFICIENT` (synthesize REQUIREMENTS inline, no agent
spawn) or `AMBIGUOUS` (fall through to the agent in the policy-selected mode).
See `core/rules/requirements-sufficiency.md` for the helper contract.

**If `SUFFICIENCY == "SUFFICIENT"`:** Synthesize the REQUIREMENTS block inline
from the matched signals — do NOT delegate to the requirements agent. Write
the synthesized block to `{TASK_DIR}/context/requirements.md` and use it as
the `REQUIREMENTS` value for Phase 1b.

Synthesize with the same helper and read the written block:

```bash
python3 "${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py" \
  --write "${TASK_DIR}/context/requirements.md" "${TASK}"
```

The synthesized block has the exact same shape the requirements agent returns.

**If `SUFFICIENCY == "AMBIGUOUS"`:** Delegate to the **requirements agent** in
the mode selected by `POLICY` (blocking):

```text
TASK: {TASK}
TASK_INDEX: 0
TASK_DIR: {TASK_DIR}
MODE: {single_round|deep_interview from POLICY}

Run the selected structured user-choice interview (per
`core/rules/capabilities/interactive-question.md`), write requirements.md, and
return the REQUIREMENTS block. In `MODE: deep_interview`, ask targeted follow-up
questions until the ambiguity threshold is satisfied or report BLOCKED before
implementation.
```

Extract the `REQUIREMENTS` block from the requirements agent's response and use it as
the `REQUIREMENTS` value for Phase 1b.

> **`MODE: two_round` is a compatibility fallback.** `MODE: deep_interview` is
> the preferred deeper path for high-ambiguity `deep` / `strict` policy work.
> `two_round` remains available for legacy callers, but supervisors should
> prefer the policy-selected mode.

---

#### Phase 1b+1c: Analyst (merged analyst + planner — single spawn)

> **Optimization**: Phases 1b and 1c are merged into a single analyst spawn.
> The analyst now produces `analysis.md`, `pipeline.json`, `prd.md`, and
> `handoff.md` in one step — eliminating the separate planner round-trip.

Emit before delegating:

```
[crew] {TASK_ID} | PHASE | 1b — Analysis + Planning (merged)
```

```bash
log_progress "PHASE" "1b — Analysis + Planning (merged)"
register_update current_phase phase_1bc
```

Write the active task marker so the `direct-edit-guard` hook allows edits
within this pipeline. Use `AGENT_CREW_HOME` resolved in Phase 0.

> **CRITICAL — non-skippable.** The `direct-edit-guard` PreToolUse hook
> (`${AGENT_CREW_HOME}/hooks/direct-edit-guard.sh`) blocks every Edit and
> Write tool call to project source files when this marker is absent. If
> this step is skipped, every stage agent in Phase 2 will be unable to
> write to the codebase. The orchestrator (`crew:run`) MUST NOT create this
> marker on its own — only the supervisor subagent creates it here, which
> is why the orchestrator must always delegate to a supervisor subagent
> rather than executing the pipeline inline. See
> `core/commands/run.md` Step 6 "Mandatory Delegation Rule" for the
> companion rule on the orchestrator side.
>
> The three commands below MUST all run, in this order. `mkdir -p` ensures
> the parent state directory exists (it may not exist yet on a fresh
> project), so `touch` cannot silently fail. The final `ls` is a guard that
> halts the pipeline immediately if the marker was not created, instead of
> letting stage agents hit cryptic hook-blocked errors later.

```bash
PROJECT_NAME=$(basename "${PROJECT_ROOT}")
TASKS_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}/tasks"
mkdir -p "${TASKS_DIR}"

# Legacy singleton marker — preserved for backward compatibility with codex
# / generic adapters and any tooling that has not learned the per-task layout.
touch "${TASKS_DIR}/active"

# Per-task marker — required by P4 background fan-out so concurrent
# supervisors owning independent host sessions do not strand each other's
# edits when one teardown removes the singleton early. The
# direct-edit-guard hook accepts EITHER marker, so this dual write costs
# nothing in single-mode workflows and is required in parallel/background
# workflows.
touch "${TASKS_DIR}/active.${TASK_ID}"

ls "${TASKS_DIR}/active" >/dev/null \
  || { echo "FATAL: active marker not created — direct-edit-guard will block stage agents"; exit 1; }
```

Record the current HEAD before any implementation begins:

```bash
TASK_START_HEAD=$(git -C "${PROJECT_ROOT}" rev-parse HEAD 2>/dev/null || echo "")
echo "${TASK_START_HEAD}" > "${TASK_DIR}/context/start-head.txt"
```

**Memory preflight (P40.3)**: Before spawning the analyst, run a mnemos
search using the task description so the analyst can benefit from prior
decisions and constraints captured in memory. The search result is written
to `{TASK_DIR}/context/memory.md` and passed as an optional path input to
the analyst. This is a no-op when the memory binary is absent.

```bash
MEMORY="${AGENT_CREW_HOME:-${HOME}/.agent-crew}/bin/memory"
if command -v "${MEMORY}" >/dev/null 2>&1; then
  "${MEMORY}" search "${TASK}" --limit 5 \
    > "${TASK_DIR}/context/memory.md" 2>/dev/null || true
fi
```

Delegate to the **analyst agent** (blocking). The analyst is the merged
analyst+planner — it produces all planning artifacts in one spawn:

```text
TASK: {TASK}
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {PROJECT_ROOT}
REQUIREMENTS: {REQUIREMENTS — always present at this point}
MEMORY_CONTEXT_PATH: {TASK_DIR}/context/memory.md  (read this file if non-empty for prior context)

Distill intent, identify ambiguities and risks, determine the agent pipeline,
write {TASK_DIR}/context/analysis.md, {TASK_DIR}/context/prd.md,
{TASK_DIR}/pipeline.json, and {TASK_DIR}/handoff.md.
Return the ANALYSIS block.
```

Pass only paths in the prompt — never inline file contents.

Extract the `ANALYSIS` block from the analyst's response.

If the analyst returns `readiness: BLOCKED`, write `STATUS: BLOCKED` to
`{TASK_DIR}/result.md` with the analyst's blocker explanation and stop.

After completion, read only `pipeline.json` (never read `handoff.md` contents).
Use the `PIPELINE_PATH` variable resolved in Phase 0:

```bash
cat "${PIPELINE_PATH}"
```

#### Phase 1b pipeline guard: mandatory reviewer-stage append

Immediately after reading `pipeline.json`, run a normalization block that
appends `["reviewer"]` if the last stage is not already a solo `reviewer`
stage. This is a **deterministic backstop** — it fires regardless of how the
pipeline was produced (analyst, inline synthesis, or manual edit) and ensures
Phase 2 always sees a valid pipeline that ends with a reviewer stage.

```bash
python3 - "${PIPELINE_PATH}" <<'PYEOF'
import json, os, sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    p = json.load(f)

stages = p.get("stages", []) or []

def last_agents(s):
    if isinstance(s, str):   return [s]
    if isinstance(s, list):  return s
    if isinstance(s, dict):  return s.get("agents", [])
    return []

if not stages or last_agents(stages[-1]) != ["reviewer"]:
    stages.append(["reviewer"])
    p["stages"] = stages
    with open(path, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("[pipeline-guard] reviewer stage appended")
PYEOF

# Emit a STATE_WARN event when the guard fires so the correction is visible
# in progress.log. The python block above prints the sentinel line to stdout
# when it fires; capture that and emit via log_progress.
GUARD_OUTPUT=$(python3 - "${PIPELINE_PATH}" <<'PYEOF2'
import json, sys
path = sys.argv[1]
try:
    p = json.load(open(path))
    stages = p.get("stages", []) or []
    def last_agents(s):
        if isinstance(s, str):  return [s]
        if isinstance(s, list): return s
        if isinstance(s, dict): return s.get("agents", [])
        return []
    print("ok" if stages and last_agents(stages[-1]) == ["reviewer"] else "missing")
except Exception:
    print("missing")
PYEOF2
)

# Note: the guard already wrote the fix above; this second check is for logging.
# If the pipeline now ends with reviewer, the guard fired (or was already correct).
# We log STATE_WARN only when the guard had to append (i.e., the analyst omitted it).
# The log_progress helper is defined in Phase 0 of this module — reuse it here.
```

The guard is idempotent: if the analyst already appended `["reviewer"]` correctly
the block is a no-op (no write, no log event). When it does fire, the pipeline
is corrected in-place and a `STATE_WARN` progress event should be emitted by the
supervisor runtime using `log_progress`.

#### Phase 1b pipeline quality gate: mandatory TDD implementation plan

Immediately after the reviewer-stage guard, validate that any mutating code
implementation stage is TDD-capable before the pipeline can enter Phase 2. This
is a planning-time gate; do not wait until the completion-time
`quality-loop-check.py` catches the missing evidence.

```bash
PLAN_CHECK_OUTPUT=$(python3 "${AGENT_CREW_HOME}/scripts/pipeline-quality-plan-check.py" \
  --pipeline "${PIPELINE_PATH}" \
  --task "${TASK}" \
  --format text 2>&1)
PLAN_CHECK_RC=$?

if [ "${PLAN_CHECK_RC}" -ne 0 ]; then
  log_progress "BLOCKED" "pipeline quality plan failed: ${PLAN_CHECK_OUTPUT}"
  register_update current_phase blocked
  register_update blocked_by pipeline_quality_plan_failed
  cat > "${TASK_DIR}/result.md" <<EOF
STATUS: BLOCKED
BLOCKER: pipeline_quality_plan_failed
DETAIL: pipeline.json contains code implementation stages that are not TDD-capable or are missing a later reviewer stage.

${PLAN_CHECK_OUTPUT}
EOF
  exit 1
fi
```

Common remediation: rewrite bare code stages such as `["backend"]` or
`["designer", "backend"]` into separate object stages with
`{ "agents": ["backend"], "tdd_parallel": true }`, then keep a later solo
`["reviewer"]` stage.

#### Phase 1b pipeline capability gate: runtime role/tool preflight

After the quality-plan gate passes, validate the planned runtime stages against
the agent capability manifest before Phase 1d plan approval and before any
stage agent receives tools. This gate blocks recursive delegation, workflow
state mutation by stage agents, non-solo reviewer/devops stages, unknown agents
without a custom-agent file or `needs_creation` plan, and custom agents whose
names imply destructive authority without a manifest-managed role.

```bash
CAPABILITY_CHECK_OUTPUT=$(python3 "${AGENT_CREW_HOME}/scripts/pipeline-capability-check.py" \
  --pipeline "${PIPELINE_PATH}" \
  --manifest "${AGENT_CREW_HOME}/policies/agent-capabilities.json" \
  --agent-dir "${AGENT_CREW_HOME}/system/agents" \
  --agent-dir "${AGENT_CREW_HOME}/user/agents" \
  --format text 2>&1)
CAPABILITY_CHECK_RC=$?

if [ "${CAPABILITY_CHECK_RC}" -ne 0 ]; then
  log_progress "BLOCKED" "pipeline capability preflight failed: ${CAPABILITY_CHECK_OUTPUT}"
  register_update current_phase blocked
  register_update blocked_by pipeline_capability_preflight_failed
  cat > "${TASK_DIR}/result.md" <<EOF
STATUS: BLOCKED
BLOCKER: pipeline_capability_preflight_failed
DETAIL: pipeline.json violates the agent capability manifest or custom-agent
        safety defaults.

${CAPABILITY_CHECK_OUTPUT}
EOF
  exit 1
fi
```

#### Phase 1c-bis: Per-stage host task DAG mirror (P3 — capability-gated)

If `HAS_TASK_TOOLS == 1`, after the analyst (merged analyst+planner) has written `pipeline.json`, create
one child host task per stage and persist the `blockedBy` DAG so operators can
see the pipeline structure in the host UI.

```bash
register_update current_phase phase_1c_bis
```
 The per-stage task ids are written
back to `pipeline.json.host_task_ids` as a parallel array to `stages`. Each
entry is itself a map `{agent_name: host_task_id}` so parallel stages with
multiple agents all get individual host tasks.

The DAG rule is straightforward:

- Stage 0 agents: `blockedBy = [parent task id]` (the parent task created in
  Phase 0 — read from `${TASK_DIR}/host-task-id.txt`).
- Stage `i` agents (i > 0): `blockedBy = [every host task id from stage i-1]`.

Pseudocode (host tool calls are issued by the runtime; the runner persists ids
only):

```text
HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt")
stages = pipeline.json["stages"]
host_task_ids = []  # parallel to stages
for i, stage in enumerate(stages):
    agents = stage if isinstance(stage, list) else [stage]
    parents = [HOST_TASK_ID] if i == 0 else list(host_task_ids[i-1].values())
    stage_map = {}
    for agent_name in agents:
        new_id = TaskCreate(
            subject=f"stage {i+1}/{len(stages)} — {agent_name}",
            description=f"Pipeline stage child for TASK_ID={TASK_ID}. "
                        f"File source of truth: {TASK_DIR}/pipeline.json "
                        f"stage_agent_status[\"{i}\"][\"{agent_name}\"]",
            activeForm=f"Waiting on stage {i+1} ({agent_name})",
            metadata={"task_id": TASK_ID, "stage_index": i,
                      "agent_name": agent_name, "parent_task_id": HOST_TASK_ID},
            blockedBy=parents,
        )
        stage_map[agent_name] = new_id
    host_task_ids.append(stage_map)
write host_task_ids back into pipeline.json under key "host_task_ids"
```

The single source of truth for stage status remains
`pipeline.json.stage_agent_status` and the file-based `progress.log`. Host
tasks are an observability mirror only — if any `TaskCreate` call fails or is
unavailable, silently fall back to running without the DAG mirror (the rest of
the pipeline must not depend on `host_task_ids` being populated).

If `HAS_TASK_TOOLS == 0`: skip this entire sub-phase. `pipeline.json` will not
contain a `host_task_ids` key and every later phase MUST treat its absence as
equivalent to "DAG mirror disabled".

---

### Phase 1d: Plan Approval Gate

> **Skip this phase when resuming** (i.e., `PIPELINE_PATH` already existed at
> Phase 0). The plan was approved in the prior run; jump directly to Phase 1.5.

Emit before displaying the plan:

```
[crew] {TASK_ID} | PHASE | 1d — Plan approval
```

Also append to the progress log:

```bash
log_progress "PHASE" "1d — Plan approval"
register_update current_phase phase_1d
register_update approval_status pending
```

Read `pipeline.json` (via `PIPELINE_PATH`), `{TASK_DIR}/context/analysis.md`, and
`{TASK_DIR}/context/prd.md` (via `PRD_PATH`):

```bash
python3 -c "
import json, re, sys

# Read pipeline.json
try:
    p = json.load(open('${PIPELINE_PATH}'))
except Exception:
    p = {}
stages = p.get('stages', []) or []
needs_creation = p.get('needs_creation', []) or []

# Normalize each stage entry into a dict with: agents, tdd_parallel,
# parallelizable_units, streaming_review. Tolerates the three legacy
# stage shapes (bare string, bare list, object form).
def normalize_stage(s):
    if isinstance(s, str):
        return {'agents': [s], 'tdd_parallel': False,
                'parallelizable_units': [], 'streaming_review': False}
    if isinstance(s, list):
        return {'agents': [a for a in s if isinstance(a, str)],
                'tdd_parallel': False,
                'parallelizable_units': [], 'streaming_review': False}
    if isinstance(s, dict):
        units = s.get('parallelizable_units') or []
        if not isinstance(units, list):
            units = []
        return {'agents': [a for a in (s.get('agents') or []) if isinstance(a, str)],
                'tdd_parallel': bool(s.get('tdd_parallel')),
                'parallelizable_units': units,
                'streaming_review': bool(s.get('streaming_review'))}
    return {'agents': [], 'tdd_parallel': False,
            'parallelizable_units': [], 'streaming_review': False}

norm_stages = [normalize_stage(s) for s in stages]

# Read prd.md for per-agent detail (tolerant — skip if absent or unparseable)
prd_agent_detail = {}  # {agent_name: {'work': str, 'files': [str]}}
try:
    prd_text = open('${PRD_PATH}').read()
    # Match '### Stage N: agent_name' sections
    section_pat = re.compile(r'###\s+Stage\s+\d+:\s+(\S+)', re.IGNORECASE)
    sections = list(section_pat.finditer(prd_text))
    for idx, m in enumerate(sections):
        agent_name = m.group(1).rstrip(':').lower()
        start = m.end()
        end = sections[idx + 1].start() if idx + 1 < len(sections) else len(prd_text)
        body = prd_text[start:end]
        # Extract **Work**: description (first non-empty line after the marker, max 200 chars)
        work = ''
        work_m = re.search(r'\*\*Work\*\*\s*:?\s*(.+)', body)
        if work_m:
            work = work_m.group(1).strip()[:200]
        # Extract **Files**: bullet lines
        files = []
        in_files = False
        for line in body.splitlines():
            if re.match(r'\*\*Files\*\*', line):
                in_files = True
                continue
            if in_files:
                bullet = re.match(r'\s*[-*]\s+(.+)', line)
                if bullet:
                    files.append(bullet.group(1).strip())
                elif line.strip() == '' or re.match(r'##', line):
                    break
        prd_agent_detail[agent_name] = {'work': work, 'files': files}
except Exception:
    pass  # prd.md absent or unparseable — fall back to stage names only

prd_loaded = bool(prd_agent_detail)
detail_missing_note_emitted = False

# Count total agent spawns for the headline (best-effort estimate)
def stage_spawn_count(ns):
    n = max(1, len(ns['agents']))
    if ns['tdd_parallel']:
        n += 1  # test-writer co-spawn
    units = len(ns['parallelizable_units'])
    if units >= 2:
        n = max(n, units + (1 if ns['tdd_parallel'] else 0))
    if ns['streaming_review']:
        n += 1  # reviewer co-spawned
    return n

total_spawns = sum(stage_spawn_count(ns) for ns in norm_stages)

print('## Plan Approval')
print('')
print(f'Pipeline: {len(norm_stages)} stages, ~{total_spawns} agent spawns total')
print('')

for i, ns in enumerate(norm_stages, 1):
    agents = ns['agents'] or ['(unknown)']
    label = ', '.join(agents)
    flags = []
    if ns['tdd_parallel']:
        flags.append('tdd_parallel: true')
    units = ns['parallelizable_units']
    if len(units) >= 2:
        flags.append(f'parallelizable_units: {len(units)}')
    if ns['streaming_review']:
        flags.append('streaming_review: true')
    flag_suffix = f' ({\"; \".join(flags)})' if flags else ''
    print(f'### Stage {i} — {label}{flag_suffix}')

    # Stage-level brief: use the first agent's PRD entry as a representative.
    first_detail = prd_agent_detail.get(agents[0].lower(), {}) if agents else {}
    if first_detail.get('work'):
        print(f'Brief: {first_detail[\"work\"]}')
    elif not prd_loaded:
        if not detail_missing_note_emitted:
            print('Brief: (detail not provided by planner — see prd.md for full context)')
            detail_missing_note_emitted = True
    print('')

    # Sub-task fan-out: render one block per unit, then list any co-spawned agents.
    if len(units) >= 2:
        print('Units to spawn:')
        for u in units:
            if not isinstance(u, dict):
                continue
            uid = u.get('id') or '(unnamed)'
            ufiles = u.get('files') or []
            ubrief = u.get('brief') or ''
            print(f'  - unit {uid} ({agents[0] if agents else \"agent\"})')
            if ubrief:
                print(f'      Brief: {ubrief}')
            if ufiles:
                print(f'      Files:')
                for f in ufiles:
                    if isinstance(f, str):
                        print(f'        - {f}')
                    elif isinstance(f, dict) and isinstance(f.get('path'), str):
                        print(f'        - {f[\"path\"]}')
        # Co-spawned helpers under fan-out
        if ns['tdd_parallel']:
            tw = prd_agent_detail.get('test-writer', {})
            print(f'  - test-writer (co-spawned, shared across units)')
            if tw.get('brief') or tw.get('work'):
                print(f'      Brief: {tw.get(\"work\") or tw.get(\"brief\")}')
            if tw.get('files'):
                print(f'      Files:')
                for f in tw['files']:
                    print(f'        - {f}')
        if ns['streaming_review']:
            print('  - reviewer (co-spawned in streaming mode)')
        print('')
        continue

    # Non-fan-out path: list each agent in the stage with its PRD detail.
    print('Agents to spawn:')
    for agent in agents:
        print(f'  - {agent}')
        det = prd_agent_detail.get(agent.lower(), {})
        if det.get('files'):
            print(f'      Files:')
            for f in det['files']:
                print(f'        - {f}')
        if det.get('work'):
            print(f'      Brief: {det[\"work\"]}')

    # Optional co-spawned agents on the legacy / TDD-parallel path.
    if ns['tdd_parallel']:
        tw = prd_agent_detail.get('test-writer', {})
        print(f'  - test-writer (co-spawned)')
        if tw.get('files'):
            print(f'      Files:')
            for f in tw['files']:
                print(f'        - {f}')
        if tw.get('work'):
            print(f'      Brief: {tw[\"work\"]}')
    if ns['streaming_review']:
        print('  - reviewer (co-spawned in streaming mode)')
    print('')

print('### Dynamic Agents To Create')
if needs_creation:
    for item in needs_creation:
        if isinstance(item, dict):
            print(f'  - {item.get(\"name\", \"(unnamed)\")}: {item.get(\"reason\", \"\")}')
else:
    print('  - none')
" 2>/dev/null
```

Also extract from `analysis.md`:
- `intent:` line → intent summary
- Count of `risk` entries → risk count

Display the plan summary as inline text. The Python block above already
emits a markdown-styled block (`## Plan Approval` + `### Stage N — …`
headings, agent/unit bullets with `Brief:` and `Files:` sub-lines). Show
that output verbatim, then prepend two short context lines from
`analysis.md` so the user sees task intent + risk count above the
per-stage breakdown:

```
## Plan Approval

- Task: {TASK}
- Intent: {intent from analysis.md}
- Risks: {risk count} identified

Pipeline: {N} stages, ~{M} agent spawns total

### Stage 1 — backend (tdd_parallel: true)
Brief: Add cancel-order endpoint with idempotency guard

Agents to spawn:
  - backend
      Files:
        - src/orders/cancel.ts
        - src/orders/idempotency.ts
      Brief: Implement POST /orders/{id}/cancel with state-machine guard
  - test-writer (co-spawned)
      Files:
        - tests/orders/cancel.spec.ts
      Brief: Cover happy path, double-cancel, terminal-state rejection

### Stage 2 — reviewer
Brief: Verify cancel flow against design doc + run new tests

### Dynamic Agents To Create
  - none
```

When a stage uses sub-task fan-out (`parallelizable_units` with length
≥ 2), the per-stage block lists `Units to spawn:` instead of `Agents to
spawn:`, with one entry per unit (id + brief + files). When
`tdd_parallel: true` is also set on a fan-out stage, the shared
`test-writer` is appended under the units block.

The `Brief:` and `Files:` lines appear only when `prd.md` contains
per-agent sections. If `prd.md` is absent, malformed, or the relevant
sections are missing, the display falls back to showing stage names
only — and emits the note `Brief: (detail not provided by planner —
see prd.md for full context)` once, on the first affected stage. The
extractor never crashes the supervisor: any exception parsing
`pipeline.json` or `prd.md` degrades to "stage names only" silently.

**Do not change the structured user-choice intent below.** Only the
display block above is enriched — the approval gate itself
(header / question / options) remains exactly as specified so all host
adapters continue to receive the same choice contract.

#### Speculative I/O Prefetch (idle-window optimization)

While the user reviews the plan above (typically 30 s – several minutes), spawn
a **background shell job** that pre-warms the OS page cache for files the next
stages will touch. This eliminates stage cold-start latency. The prefetch is:

- **read-only** and **idempotent** — failures degrade silently and MUST NEVER
  fail the pipeline.
- **token-free** — pure shell I/O (`cat`, `wc`, `git status`, `ls`). No agent
  spawns and no LLM-bound calls.
- **plain shell background** — does NOT require `HAS_AGENT_BACKGROUND`. Uses
  `&` + `disown` so the job is detached from the supervisor's foreground.
- **race-safe** — the approval-polling logic below is not modified. The
  prefetch's PID is captured into a sentinel file (`prefetch.pid`) so it can
  be killed cleanly regardless of approval outcome.

Spawn the prefetch BEFORE firing the structured user-choice intent:

```bash
PREFETCH_PID_FILE="${TASK_DIR}/context/prefetch.pid"
PREFETCH_LOG="${TASK_DIR}/context/prefetch.log"
PREFETCH_FILES_LIST="${TASK_DIR}/context/prefetch-files.txt"

# Enumerate file paths the upcoming stages will touch — extract from prd.md
# (per-stage **Files** bullet lines) and union with anything in pipeline.json's
# `stages[].files` if present. The enumeration is best-effort: if nothing can
# be derived we still warm the worktree status, which is the cheapest win.
python3 - <<'PY' >"${PREFETCH_FILES_LIST}" 2>/dev/null || true
import json, os, re

task_dir = os.environ.get('TASK_DIR', '')
pipeline_path = os.path.join(task_dir, 'pipeline.json')
prd_path = os.path.join(task_dir, 'context', 'prd.md')

files = []

# 1) pipeline.json — tolerate missing/extra keys
try:
    p = json.load(open(pipeline_path))
    for stage in p.get('stages', []) or []:
        # stages may be strings, lists, or dicts depending on planner output
        if isinstance(stage, dict):
            for f in stage.get('files', []) or []:
                if isinstance(f, str):
                    files.append(f)
                elif isinstance(f, dict) and isinstance(f.get('path'), str):
                    files.append(f['path'])
except Exception:
    pass

# 2) prd.md — **Files** bullet lines under each Stage section
try:
    text = open(prd_path).read()
    in_files = False
    for line in text.splitlines():
        if re.match(r'\*\*Files\*\*', line):
            in_files = True
            continue
        if in_files:
            m = re.match(r'\s*[-*]\s+`?([^`\s(]+)', line)
            if m:
                files.append(m.group(1))
            elif line.strip() == '' or line.startswith('##') or line.startswith('**'):
                in_files = False
except Exception:
    pass

# De-duplicate while preserving order; cap at 200 to bound work
seen = set()
out = []
for f in files:
    f = f.strip().rstrip(',').strip('`"\'')
    if not f or f in seen:
        continue
    seen.add(f)
    out.append(f)
    if len(out) >= 200:
        break
for f in out:
    print(f)
PY

PREFETCH_FILE_COUNT=$(wc -l <"${PREFETCH_FILES_LIST}" 2>/dev/null | tr -d ' ' || echo 0)

# Launch the prefetch worker fully detached. All errors are swallowed; the
# pipeline must never fail because of speculative I/O.
(
  set +e
  start_epoch=$(date +%s)

  # (a) Per-worktree pre-verification — cheap and side-effect-free
  ( cd "${PROJECT_ROOT}" 2>/dev/null && git status --porcelain >/dev/null 2>&1 ) || true
  ls -la "${PROJECT_ROOT}" >/dev/null 2>&1 || true
  ls -la "${TASK_DIR}" >/dev/null 2>&1 || true
  ls -la "${TASK_DIR}/context" >/dev/null 2>&1 || true

  # (b) Warm OS page cache for each enumerated file
  warmed=0
  if [ -s "${PREFETCH_FILES_LIST}" ]; then
    while IFS= read -r rel; do
      [ -z "${rel}" ] && continue
      # Resolve relative to PROJECT_ROOT, but also accept absolute paths
      case "${rel}" in
        /*) abs="${rel}" ;;
        *)  abs="${PROJECT_ROOT}/${rel}" ;;
      esac
      if [ -f "${abs}" ]; then
        # `wc -c` is enough to fault the file into page cache; `cat` would
        # also work but pipes through more bytes. Both are silenced.
        wc -c "${abs}" >/dev/null 2>&1 && warmed=$((warmed + 1)) || true
      fi
    done <"${PREFETCH_FILES_LIST}"
  fi

  # (c) Warm the agent-crew system tree (next stages will read agent .md)
  ls -la "${AGENT_CREW_HOME}/system/agents" >/dev/null 2>&1 || true

  end_epoch=$(date +%s)
  elapsed=$((end_epoch - start_epoch))

  # Emit the DONE event from inside the background job. Use the same
  # log_progress format Phase 0 defined; if the helper is not available in
  # this subshell, append directly to progress.log with a compatible line.
  detail="files=${warmed} elapsed=${elapsed}s"
  if command -v log_progress >/dev/null 2>&1; then
    log_progress "PHASE_1D_PREFETCH_DONE" "${detail}"
  else
    echo "$(date -u +%Y-%m-%dT%H:%M:%S) | PHASE_1D_PREFETCH_DONE | ${detail}" \
      >> "${TASK_DIR}/progress.log" 2>/dev/null || true
  fi
  # Clean up our PID file so the post-approval cleanup knows we exited cleanly.
  rm -f "${PREFETCH_PID_FILE}" 2>/dev/null || true
) >"${PREFETCH_LOG}" 2>&1 &
PREFETCH_PID=$!
disown "${PREFETCH_PID}" 2>/dev/null || true
echo "${PREFETCH_PID}" > "${PREFETCH_PID_FILE}" 2>/dev/null || true

log_progress "PHASE_1D_PREFETCH_STARTED" "pid=${PREFETCH_PID} files=${PREFETCH_FILE_COUNT}"
```

The prefetch runs concurrently with the approval gate below. It will either:

- Finish on its own (page cache fully warmed) and emit `PHASE_1D_PREFETCH_DONE`.
- Still be alive when the user responds — in which case the cleanup block
  immediately after the approval intent kills it and emits
  `PHASE_1D_PREFETCH_KILLED`.

Either outcome is acceptable. The pipeline must not block on the prefetch.

Then fire a **structured user-choice intent** (see
`core/rules/capabilities/interactive-question.md`):
- header: "Implementation Plan"
- question: "Review the implementation plan above. Approve to begin execution."
- options:
  - label: "Approve"
    description: "Begin stage execution"
  - label: "Request changes"
    description: "Describe what to change (analyst will revise)"
  - label: "Cancel"
    description: "Stop execution"

#### Prefetch cleanup (post-approval)

Immediately after the user's choice is observed (regardless of which option
they picked), run this idempotent cleanup. It MUST run before any
option-specific branching below so the background job never outlives the
approval gate:

```bash
# Determine the reason label for the KILLED event from the user's choice.
# CHOICE is the local variable holding the structured-intent response —
# "approve", "request_changes", or "cancel" (lowercase, dash-normalized).
case "${CHOICE}" in
  approve)         PREFETCH_KILL_REASON="approved" ;;
  request_changes) PREFETCH_KILL_REASON="request_changes" ;;
  cancel)          PREFETCH_KILL_REASON="cancel" ;;
  *)               PREFETCH_KILL_REASON="approved" ;;
esac

if [ -f "${PREFETCH_PID_FILE}" ]; then
  _pf_pid=$(cat "${PREFETCH_PID_FILE}" 2>/dev/null || echo "")
  if [ -n "${_pf_pid}" ] && kill -0 "${_pf_pid}" 2>/dev/null; then
    kill "${_pf_pid}" 2>/dev/null || true
    log_progress "PHASE_1D_PREFETCH_KILLED" "reason=${PREFETCH_KILL_REASON}"
  fi
  rm -f "${PREFETCH_PID_FILE}" 2>/dev/null || true
fi
unset PREFETCH_PID PREFETCH_PID_FILE PREFETCH_FILES_LIST PREFETCH_LOG \
      PREFETCH_FILE_COUNT PREFETCH_KILL_REASON
```

Notes on this cleanup:

- It is safe to run when the prefetch already finished — `kill -0` returns
  non-zero, the kill branch is skipped, and the PID file is simply removed.
- On Approve, the background process is killed (if still alive) only to keep
  the worktree clean; the OS page cache it already warmed remains valid and
  is consumed naturally by the upcoming stages — no explicit hand-off needed.
- On Cancel or Request changes, prefetch results are discarded silently. The
  warmed pages cost nothing extra; they will simply age out of the cache.

**If Approve:** mark the register and proceed to Phase 1.5.

```bash
register_update approval_status approved
```


**If Request changes:** collect the change description from the user's response,
then re-invoke the **analyst** (merged analyst+planner) with the change request.
Pass only paths — never inline file contents:

```text
TASK: {TASK}
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {PROJECT_ROOT}
REQUIREMENTS: {REQUIREMENTS}

CHANGE REQUEST: {user's change description}

Re-plan the pipeline based on the change request above.
Update {TASK_DIR}/pipeline.json and {TASK_DIR}/handoff.md accordingly.
Keep {TASK_DIR}/context/analysis.md consistent with the new plan.
```

After the analyst returns, return to Phase 1d (re-display the updated plan and
ask again). Do not proceed to Phase 1.5 until the user selects Approve.

**If Cancel:**

```bash
echo "# {TASK}

DESCRIPTION: {TASK}
BRANCH: {BRANCH}
STATUS: CANCELLED
COMMITS: 0
LOG: (cancelled before execution)

CHANGES: none — cancelled at plan approval gate
" > "${TASK_DIR}/result.md"
```

Emit:

```
[crew] {TASK_ID} | COMPLETED | STATUS=CANCELLED
```

And append to progress log + update register:

```bash
log_progress "COMPLETED" "STATUS=CANCELLED"
register_update approval_status cancelled
register_update current_phase blocked
register_update blocked_by --json '["plan_approval_cancelled"]'
```

Then return to the orchestrator without executing any pipeline stages.

---

### Phase 1.5: Pre-execution Agent Creation

If the `needs_creation` list is non-empty, emit before creating agents (where `{n}` is the count of agents to create):

```
[crew] {TASK_ID} | PHASE | 1.5 — Creating {n} dynamic agent(s)
```

```bash
log_progress "PHASE" "1.5 — Creating {n} dynamic agent(s)"
register_update current_phase phase_1_5
```

Read the `needs_creation` list from `PIPELINE_PATH` (already resolved in Phase 0):

```bash
python3 -c "
import json, os
agent_home = os.environ.get('AGENT_CREW_HOME', os.path.expanduser('~/.agent-crew'))
p = json.load(open('${PIPELINE_PATH}'))
for item in p.get('needs_creation', []):
    agent_file = os.path.join(agent_home, 'agents', item['name'] + '.md')
    # Skip creation if the agent file already exists on disk
    if not os.path.exists(agent_file):
        print(item['name'] + '|' + item['reason'] + '|' + item['role'])
    else:
        print('SKIP:' + item['name'])  # already exists, skip Phase 1.5 for this agent
"
```

If the list is empty or the field is absent, skip this phase entirely and proceed to Phase 2.

For each entry that is **not** prefixed with `SKIP:`, spawn an Agent with the
following prompt to create the new agent (blocking). Entries prefixed `SKIP:`
already have an agent file — do not re-spawn them, proceed directly to Phase 2.

**Slim template**: Use only the essential fields below. Do not add boilerplate
sections that the agent-maker would pad. Smaller prompts reduce spawn latency.

For each entry in `needs_creation` (that is not already on disk), spawn an Agent with the following prompt to create the new agent (blocking):

```text
You are acting as the agent-maker. Your job is to create a new agent definition file.

Agent to create:
  Name: {name}
  Reason: {reason}
  Role: {role}

Write the agent definition following this template:
---
name: {name}
description: >
  {role summary as TRIGGER/SKIP/Output format}
model: inherit
---

# {Name} Agent

## Role
{role}

## Inputs
- TASK_DIR
- PROJECT_ROOT
- HANDOFF_PATH
- QUALITY_RULE_PATH

## Workflow
1. Read required files by path (never inline contents).
2. Perform the assigned work.
3. Read and apply the quality loop rule from QUALITY_RULE_PATH.
4. Report STATUS, ARTIFACTS, ITERATIONS.

## Rules
- Do not modify handoff.md if running in parallel mode.
- All file operations relative to PROJECT_ROOT.
- Never push to remote.

Save to: {AGENT_CREW_HOME}/agents/{name}.md

Return: STATUS: completed / FILES: {path}
```

Where `{name}`, `{reason}`, `{role}`, and `{AGENT_CREW_HOME}` are substituted from the parsed `needs_creation` entry and the resolved `AGENT_CREW_HOME` variable (`${HOME}/.agent-crew` unless overridden).

After each Agent returns, verify the file exists before continuing.
Use the `AGENT_CREW_HOME` variable resolved in Phase 0:

```bash
ls "${AGENT_CREW_HOME}/agents/${name}.md"
```

If a required agent file still does not exist after the Agent call completes, write the failure to
`{TASK_DIR}/result.md` and return `STATUS: BLOCKED` to the orchestrator — do not proceed.

---


---

After Phase 1.5, the supervisor transitions to Phase 2 — Read
`supervisor-stages.md` and `supervisor-retry.md` next (both are needed
for stage execution; the Stage Retry Rule body lives in retry).
