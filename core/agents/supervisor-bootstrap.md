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

`HAS_TASK_TOOLS` gates every `TaskCreate` / `TaskList` / `TaskGet` /
`TaskUpdate` call. `HAS_AGENT_BACKGROUND` gates the background fan-out path in
`run.md` Step 6. `HAS_MONITOR_TOOL` gates the `TaskOutput` consumption in
`crew:status`. `HAS_COST_TRACKING` gates the cost circuit breaker in
`supervisor-retry.md` § Cost Circuit Breaker (Phase 3.3). Every call site MUST
check the relevant flag and fall back to the
file-based primary (`progress.log`, `approval.md`, `pipeline.json`) when the
flag is `0`.

If `HAS_TASK_TOOLS == 1`, the supervisor registers itself with the host's task
surface so users can see live pipeline progress in the host UI:

1. **Check whether the orchestrator already pre-created a parent host task.**
   When the runner is spawned via P4 background fan-out (`agent_background=1`,
   for any task count including `N == 1`), the orchestrator pre-creates the
   parent host task and passes its id as `HOST_TASK_ID` in the runner's
   input. In that case, skip the `TaskCreate` call below and reuse the
   provided id:

   ```bash
   if [ -n "${HOST_TASK_ID:-}" ]; then
     # Background fan-out path — parent task pre-created by orchestrator
     echo "${HOST_TASK_ID}" > "${TASK_DIR}/host-task-id.txt"
   else
     # Inline path — runner creates its own parent task
     # (call TaskCreate as documented below, capture id, persist)
     :
   fi
   ```

2. **Otherwise, call `TaskCreate` once at the very start of Phase 0** (right
   after the `STARTED` log line):

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

3. At Phase 3 completion (after `result.md` is written), call
   `TaskUpdate(taskId=HOST_TASK_ID, status="completed")`. On `STATUS: blocked` or
   `STATUS: CANCELLED`, leave the host task as `in_progress` and append a final
   progress event — the host task list itself remains the responsibility of the
   human operator to clean up, so the runner does not delete it.

   Under background fan-out (P4), the orchestrator's Step 7 result collection
   reads `TaskGet(HOST_TASK_ID).status` as the primary signal that the runner
   has finished, so this final `TaskUpdate` is what unblocks the
   orchestrator's collection loop. The status transition is observable
   instantly without polling `result.md`.

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
    PHASE|STAGE)                                        _status="in_progress" ;;
    STAGE_DONE|COMPLETED|HANDOFF_PAGEDOUT)              _status="completed" ;;
    BLOCKED|COST_BLOCKED|HANDOFF_PAGEOUT_FAILED)        _status="failed" ;;
    RETRY)                                              _status="retry" ;;
    HANDOFF_PAGEOUT_SKIPPED)                            _status="skipped" ;;
    COST_WARN|HANDOFF_PAGEOUT)                          _status="warn" ;;
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
    "1": {"designer": "completed", "backend": "completed"},
    "2": {"frontend": "completed"}
  }
}
```

This prevents restarting already-finished agents when resuming after an interrupt.

### Phase 1: Analysis + Planning

> **Skip this entire Phase 1 (1a, 1b+1c, 1d) and Phase 1.5 when resuming** (i.e.,
> when `PIPELINE_PATH` already existed at Phase 0). Jump directly to Phase 2 using
> the `completed_stages` and `stage_agent_status` read in Phase 0.

#### Phase 1a: Requirement Collection Gate

Emit before checking:

```
[crew] {TASK_ID} | PHASE | 1a — Requirement collection
```

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | PHASE | 1a — Requirement collection" >> "${TASK_DIR}/progress.log"
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

Run the sufficiency check first. The check is a deterministic Python snippet
that scores the TASK string against three signals (scope, target, constraints)
and returns either `SUFFICIENT` (synthesize REQUIREMENTS inline, no agent
spawn) or `AMBIGUOUS` (fall through to the agent in single-round mode).

```python
import re

def sufficiency_check(task: str) -> str:
    """Return 'SUFFICIENT' if scope, target, and constraints can be inferred
    with high confidence from TASK alone; otherwise 'AMBIGUOUS'."""
    t = task.lower()

    # Question-word veto — any question word means we must ask the user.
    question_markers = ["?", "how should", "what about", "which ", "should i",
                        "shall i", "do you think"]
    if any(m in t for m in question_markers):
        return "AMBIGUOUS"

    # Signal 1: scope inferable
    backend_kw = ("backend", "api", "server", "endpoint", "database",
                  "domain model", "schema")
    ui_kw = ("frontend", "ui ", "component", " page ", "css", "styling",
             "layout")
    tooling_kw = ("docs", "documentation", "readme", "markdown", "config",
                  "script", "refactor", "spec", "tooling", "pipeline",
                  "agent", "hook")
    scope_hit = any(k in t for k in backend_kw + ui_kw + tooling_kw)

    # Signal 2: target inferable
    has_file_path = re.search(
        r"[a-zA-Z0-9_./-]+\.(md|py|ts|tsx|js|jsx|sh|json|yml|yaml)",
        task,
    ) is not None
    has_branch_ref = re.search(
        r"\b(feat|fix|docs|chore|refactor|test)/[a-z0-9-]+",
        task,
    ) is not None
    has_quoted_name = '"' in task or "`" in task
    has_concrete_pointer = re.search(
        r"\bthe [a-z]+ (agent|hook|command|step|phase|rule|gate|file|module)",
        t,
    ) is not None
    target_hit = (has_file_path or has_branch_ref or has_quoted_name
                  or has_concrete_pointer)

    # Signal 3: constraints inferable
    has_perf = re.search(r"\d+\s*(ms|s\b|mb|gb|req/s|qps|rps)", t) is not None
    has_mvp = any(k in t for k in ("mvp", "minimal", "v1 ", "scope-limit",
                                   "scope limit"))
    has_dep = any(k in t for k in ("no new deps", "no new dependencies",
                                   "existing stack", "existing tech stack",
                                   "use only"))
    constraint_hit = has_perf or has_mvp or has_dep

    if scope_hit and target_hit and constraint_hit:
        return "SUFFICIENT"
    return "AMBIGUOUS"
```

This is the **same algorithm** that `crew:run` Step 5.pre uses; the two must
stay in sync (any change to one MUST be mirrored to the other).

**If `SUFFICIENCY == "SUFFICIENT"`:** Synthesize the REQUIREMENTS block inline
from the matched signals — do NOT delegate to the requirements agent. Write
the synthesized block to `{TASK_DIR}/context/requirements.md` and use it as
the `REQUIREMENTS` value for Phase 1b.

Inline synthesis rule (mirrors `crew:run` Step 5.pre):

- `scope`: `"Backend API"` / `"UI only"` / `"Full-stack"` / `"Tooling / docs / config"`
  based on which keyword family matched.
- `target`: `"Developer tooling or API"` for the tooling-family scope;
  `"End-user product feature"` for quoted-name / component-name dominant;
  `"Internal team / admin tooling"` for admin/dashboard keywords; otherwise
  `"Other / not yet defined"`.
- `constraints`: union of matched constraint signal labels
  (`"Performance / scalability"`, `"MVP scope"`,
  `"Use existing tech stack only"`).

The synthesized block has the exact same shape the requirements agent returns:

```text
REQUIREMENTS: |
  scope: {synthesized scope}
  target: {synthesized target}
  constraints: {comma-separated synthesized constraints}
  followup: (none)
  sufficiency: HIGH
  inline_synthesis: true
```

**If `SUFFICIENCY == "AMBIGUOUS"`:** Delegate to the **requirements agent** in
single-round mode (blocking):

```text
TASK: {TASK}
TASK_INDEX: 0
TASK_DIR: {TASK_DIR}
MODE: single_round

Run a single-round structured user-choice interview (per
`core/rules/capabilities/interactive-question.md`) (scope + target + constraints
in one call), write requirements.md, and return the REQUIREMENTS block.
```

Extract the `REQUIREMENTS` block from the requirements agent's response and use it as
the `REQUIREMENTS` value for Phase 1b.

> **`MODE: two_round` is a deeper fallback** for rare cases where the
> single-round answers themselves contain ambiguity the agent decides it
> cannot resolve without a domain-specific follow-up. The supervisor does
> NOT request `two_round` directly; only the agent may escalate.

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
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | PHASE | 1b — Analysis + Planning (merged)" >> "${TASK_DIR}/progress.log"
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

Delegate to the **analyst agent** (blocking). The analyst is the merged
analyst+planner — it produces all planning artifacts in one spawn:

```text
TASK: {TASK}
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {PROJECT_ROOT}
REQUIREMENTS: {REQUIREMENTS — always present at this point}

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

#### Phase 1c-bis: Per-stage host task DAG mirror (P3 — capability-gated)

If `HAS_TASK_TOOLS == 1`, after the analyst (merged analyst+planner) has written `pipeline.json`, create
one child host task per stage and persist the `blockedBy` DAG so operators can
see the pipeline structure in the host UI. The per-stage task ids are written
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
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | PHASE | 1d — Plan approval" >> "${TASK_DIR}/progress.log"
```

Read `pipeline.json` (via `PIPELINE_PATH`), `{TASK_DIR}/context/analysis.md`, and
`{TASK_DIR}/context/prd.md` (via `PRD_PATH`):

```bash
python3 -c "
import json, re, sys

# Read pipeline.json
p = json.load(open('${PIPELINE_PATH}'))
stages = p.get('stages', [])
needs_creation = p.get('needs_creation', [])

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
        # Extract **Work**: description (first non-empty line after the marker, max 120 chars)
        work = ''
        work_m = re.search(r'\*\*Work\*\*\s*:?\s*(.+)', body)
        if work_m:
            work = work_m.group(1).strip()[:120]
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

print('STAGES:')
for i, stage in enumerate(stages, 1):
    agents = stage if isinstance(stage, list) else [stage]
    print(f'  Stage {i}: {chr(44).join(agents)}')
    for agent in agents:
        detail = prd_agent_detail.get(agent.lower(), {})
        if detail.get('work'):
            print(f'    Work: {detail[\"work\"]}')
        if detail.get('files'):
            print(f'    Files:')
            for f in detail['files']:
                print(f'      - {f}')
print('NEEDS_CREATION:')
for item in needs_creation:
    print(f'  {item[\"name\"]}')
if not needs_creation:
    print('  none')
" 2>/dev/null
```

Also extract from `analysis.md`:
- `intent:` line → intent summary
- Count of `risk` entries → risk count

Display the plan summary as inline text:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Implementation Plan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task   : {TASK}
Intent : {intent from analysis.md}
Risks  : {risk count} identified

Pipeline:
  Stage 1: {agent_name}
    Work: {work description from prd.md, if available}
    Files:
      - {file path} ({new|modified|removed}, if available)
  Stage 2: {agent_name}
    Work: {work description from prd.md, if available}
    ...

Dynamic agents to create: {needs_creation list or "none"}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

The `Work:` and `Files:` lines appear only when `prd.md` contains per-agent sections.
If `prd.md` is absent or the relevant sections are missing, the display falls back to
showing stage names only (no error).

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

**If Approve:** proceed to Phase 1.5.

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

And append to progress log:

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | COMPLETED | STATUS=CANCELLED" >> "${TASK_DIR}/progress.log"
```

Then return to the orchestrator without executing any pipeline stages.

---

### Phase 1.5: Pre-execution Agent Creation

If the `needs_creation` list is non-empty, emit before creating agents (where `{n}` is the count of agents to create):

```
[crew] {TASK_ID} | PHASE | 1.5 — Creating {n} dynamic agent(s)
```

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | PHASE | 1.5 — Creating {n} dynamic agent(s)" >> "${TASK_DIR}/progress.log"
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
