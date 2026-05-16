# Supervisor — Stage Execution (Phase 2 + Phase 2.5)

> This module is read by the `supervisor` agent at the start of stage
> execution. Read it together with `supervisor-retry.md` (which holds
> the Stage Retry Rule that Phase 2 invokes for every stage spawn).
>
> Phase 2 is the stage-loop dispatcher; Phase 2.5 is the Stage Action
> Gate that always runs after Phase 2 (whether or not any stage returned
> a PLAN block).
>
> Phase names referenced from here (Phase 0, Phase 1c-bis, Phase 3) are
> defined in `supervisor-bootstrap.md` and `supervisor-retry.md`.

---

### Phase 2: Execute stages

Execute the `stages` from `pipeline.json` sequentially.
Skip stages already included in `completed_stages`.

At Phase 2 entry — before the stage loop begins — bump the register:

```bash
register_update current_phase phase_2
```

**Devops skip rule**: When iterating stages, if the stage agent is `devops`
(or a stage list that contains `devops`), **do not spawn it here**. Skip it
and let Phase 2.5 handle the devops stage exclusively. This ensures the
approval gate in Phase 2.5 is always reached before devops runs.

**Phase F5 — Loop variable convention.** At the top of each stage iteration
(both single and parallel), set the supervisor-local variables that the
`log_progress` helper consults via `${VAR:-default}` to populate the
structured buffer's `stage`, `agent`, and `attempt` fields:

```bash
STAGE_INDEX="${i}"          # 1-based stage index (matches existing {i} placeholder)
STAGE_AGENT="${agent_name}" # currently-running stage agent's name
RETRY_ATTEMPT=1             # reset per stage; Stage Retry Rule bumps it per retry
STAGE_START_EPOCH="$(date +%s)"  # Phase I11 — stage-timeout reference point
```

For parallel stages (`### Parallel Agents` below), set `STAGE_AGENT` per
inner-loop iteration so each parallel agent's emits carry the correct
agent name. `STAGE_START_EPOCH` is set ONCE per stage (not per parallel
agent) so the timeout budget applies to the slowest agent in the stage,
not to each parallel agent individually. At the end of the stage
iteration (after `STAGE_DONE`), `unset STAGE_INDEX STAGE_AGENT
RETRY_ATTEMPT STAGE_START_EPOCH` so subsequent Phase 2.5 and Phase 3
events emit with `stage=0`, `agent=""`, `attempt=0`.

#### Quality Loop Rule (resolved once in Phase 0, reused here)

`QUALITY_RULE_PATH` was already resolved in Phase 0. Use the variable as-is.
Do not re-derive `AGENT_CREW_HOME` or re-construct this path.

Pass `QUALITY_RULE_PATH` to every stage agent prompt (see format below).
After each stage returns, check its `STATUS` field:

- `STATUS: completed` → mark stage done and continue.
- `STATUS: plan_ready` → the agent has written a PLAN block instead of
  executing. Stop Phase 2 iteration immediately and proceed to Phase 2.5
  to collect the plan and run the approval gate.
- `STATUS: BLOCKED` → halt the pipeline immediately. Write the blocker
  detail to `{TASK_DIR}/result.md` and return `STATUS: blocked` to the
  orchestrator.

Do **not** silently skip a BLOCKED stage or proceed as if it completed.


#### Stage Retry Rule — reference

The Stage Retry Rule body lives in `supervisor-retry.md`. The Phase 2
stage loop invokes it for every stage spawn. Summary:

- Validation failure (criteria checked, output incorrect): retry up to **3 times**.
- Crash (no STATUS returned): retry up to **5 times** before BLOCKED.
- Token-truncation (P7 — capability-gated): 1 resume with checkpoint
  hint, then fall through to crash budget.

See `supervisor-retry.md` § Stage Retry Rule for full pseudocode and the
P7 host-status crash classifier.

#### Custom Agent Dispatch

Before spawning any stage agent, determine whether it is a builtin or custom agent:

BUILTIN_AGENTS = [planner, designer, frontend, backend, devops, resolver, reviewer, supervisor, documenter]

If the agent name is NOT in BUILTIN_AGENTS:
  1. Read its definition from `${AGENT_CREW_HOME}/agents/{name}.md`
  2. Prepend the full file content to the agent prompt as a system preamble:

     ```
     You are the {name} agent. Your definition and instructions follow:

     {full content of ~/.agent-crew/agents/{name}.md}

     ---
     Now execute your assigned work with the parameters below.
     ```

  3. Append the standard stage prompt (TASK_DIR, PROJECT_ROOT, HANDOFF_PATH, QUALITY_RULE_PATH).

If the agent name IS a builtin: use the standard stage prompt format as-is (the host already knows the builtin agent definitions).

If the custom agent file does not exist at invocation time:
  - Do NOT proceed.
  - Write BLOCKED to result.md: "Custom agent '{name}' was not created in Phase 1.5 — file missing at ${AGENT_CREW_HOME}/agents/{name}.md"
  - Return STATUS: blocked to orchestrator.

#### Stage progress emits

Before spawning each stage agent (where `{i}` is 1-based stage index and `{total}` is the
total stage count from `pipeline.json`):

```
[crew] {TASK_ID} | STAGE | {i}/{total} — {agent_name}
```

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | STAGE | {i}/{total} — {agent_name}" >> "${TASK_DIR}/progress.log"
```

If `HAS_TASK_TOOLS == 1` AND `pipeline.json` contains `host_task_ids[i-1][agent_name]`
(populated by Phase 1c-bis), also transition the per-stage host task to
`in_progress` so the DAG mirror reflects live state:

```text
TaskUpdate(taskId=host_task_ids[i-1][agent_name], status="in_progress")
```

If the key is absent (DAG mirror disabled, `task_tools=false`, or earlier
`TaskCreate` failed silently): skip the call. The file-based `STAGE` emit above
is always the canonical record.

After the stage agent returns and its result is recorded:

```
[crew] {TASK_ID} | STAGE_DONE | {agent_name} — {APPROVED|NEEDS_CHANGES|N/A}
```

```bash
log_progress "STAGE_DONE" "{agent_name} — {APPROVED|NEEDS_CHANGES|N/A}"

# Phase F4: append modified files to register (deduplicated).
MODFILES=$(cd "${PROJECT_ROOT}" && git status --short 2>/dev/null \
            | awk '{print $2}' \
            | python3 -c "import sys, json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))")
register_update modified_files --json "${MODFILES}"

# Phase F4: reviewer-stage verification status bump.
if [ "${STAGE_AGENT}" = "reviewer" ]; then
  case "${STAGE_RESULT:-}" in
    APPROVED)       register_update verification_status passed ;;
    NEEDS_CHANGES)  register_update verification_status failed ;;
    *)              register_update verification_status skipped ;;
  esac
fi
```

At reviewer-stage entry (immediately before the STAGE emit, where
`${STAGE_AGENT} == "reviewer"`), mark verification as running:

```bash
if [ "${STAGE_AGENT}" = "reviewer" ]; then
  register_update verification_status running
fi
```

If `HAS_TASK_TOOLS == 1` AND the per-stage host task id is present, mirror the
terminal state:

```text
# On successful completion:
TaskUpdate(taskId=host_task_ids[i-1][agent_name], status="completed")
# On crash exhaustion or BLOCKED:
TaskUpdate(taskId=host_task_ids[i-1][agent_name], status="blocked")
```

Skip silently when the id is absent. `pipeline.json.stage_agent_status` remains
the single source of truth that other consumers (resume logic, `crew:status`
fallback) read.

Use `APPROVED` when the reviewer accepted the output, `NEEDS_CHANGES` when the reviewer
requested changes (quality loop), or `N/A` for non-reviewer stages.

When a BLOCKED result is detected, emit before writing result.md:

```
[crew] {TASK_ID} | BLOCKED | {one-line blocker summary}
```

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | BLOCKED | {one-line blocker summary}" >> "${TASK_DIR}/progress.log"
```

When the Stage Retry Rule triggers a retry (agent crash, no STATUS line), emit:

```
[crew] {TASK_ID} | RETRY | attempt {n} — {reason}
```

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | RETRY | attempt {n} — {reason}" >> "${TASK_DIR}/progress.log"
```

#### Agent prompt format (never inline file contents)

```text
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {PROJECT_ROOT}
HANDOFF_PATH: {TASK_DIR}/handoff.md
QUALITY_RULE_PATH: {QUALITY_RULE_PATH}

Read the handoff content directly from HANDOFF_PATH.
Read the PRD directly from {TASK_DIR}/context/prd.md.
Read and apply the quality loop rule from QUALITY_RULE_PATH before reporting completion.
Perform the assigned work.
All file operations must be performed relative to {PROJECT_ROOT}.
```

### Single Agent

Spawn using the format above in blocking mode.

### Parallel Agents

(When a stage contains two or more agents)

Invoke multiple agent/delegation calls simultaneously in a single response when the host AI tool supports it.

**Parallelism opportunities**: The following stage compositions are safe to run
concurrently (they write to independent output files and do not share handoff.md):
- `["designer", "backend"]` — designer writes `design-spec.md`; backend writes
  domain model and API code. Neither depends on the other's output within the stage.
- Any stage where all agents are annotated with `do not modify handoff.md`.

The `reviewer` stage is always sequential (runs after all prior stages complete).
The `devops` stage is always sequential (requires prior stage artifacts).

Additional instruction:

```text
Do not modify handoff.md.
Save outputs only to your own result files.
```

**Per-agent completion tracking (parallel stages only):** After each agent in a
parallel stage responds, immediately record its result in `PIPELINE_PATH` under
`stage_agent_status`. For parallel stages this intermediate write is necessary
because multiple agents may crash independently:

```bash
python3 -c "
import json
p = json.load(open('${PIPELINE_PATH}'))
p.setdefault('stage_agent_status', {}).setdefault('${i}', {})['${agent_name}'] = '${status}'
json.dump(p, open('${PIPELINE_PATH}', 'w'), ensure_ascii=False, indent=2)
"
```

Where `${status}` is `completed`, `crashed`, or `blocked` based on the agent response.

**Sequential stage batching**: For stages that contain only a single agent,
skip the intermediate per-agent write above. Instead, write a single combined
update that sets both `stage_agent_status` and `completed_stages` in one
`json.dump` call after the agent returns. This halves the number of pipeline.json
writes for typical sequential pipelines.

**Selective retry for crashed parallel agents:** If one or more agents in a parallel
stage crash (no `STATUS:` line), do not restart the entire stage. Only retry the
failed agents using the Stage Retry Rule (up to 5 crash attempts each). Agents that
returned `STATUS: completed` are not re-invoked.

After all agents in the stage have reached a terminal state (`completed` or exhausted
retries), update `completed_stages` only if **all** agents completed successfully.
For parallel stages, use a single combined write (not two separate reads/writes):

```bash
python3 -c "
import json
p = json.load(open('${PIPELINE_PATH}'))
stage_status = p.get('stage_agent_status', {}).get('${i}', {})
all_done = all(v == 'completed' for v in stage_status.values())
if all_done:
    p['completed_stages'] = $((i+1))
    json.dump(p, open('${PIPELINE_PATH}', 'w'), ensure_ascii=False, indent=2)
"
```

After parallel stage completion, verify only file existence (never read contents):

```bash
ls "${TASK_DIR}/context/"
```

Pass information indirectly to the next stage agent through `HANDOFF_PATH`.

### TDD Parallel Dispatch

A stage may opt into the **TDD parallel** form by encoding itself as
the object `{ "agents": [...], "tdd_parallel": true }` instead of the
bare string / bare array forms. The schema doc
(`core/rules/state-files/pipeline-json.md` § TDD parallel stage form)
shows the wire shape. The dispatch contract below is what Phase 2 runs
at stage entry.

#### Normalization

At the top of each stage iteration, normalize the stage entry into
five locals — `STAGE_AGENTS`, `STAGE_TDD_PARALLEL`, `STAGE_UNITS_COUNT`,
`STAGE_STREAMING_REVIEW`, and (for the existing parallel-agents path)
`STAGE_AGENT` per inner-loop iteration. The units detail itself is
read from `PIPELINE_PATH` on demand by the Sub-Task Fan-Out path; the
count suffices to route dispatch.

```bash
# Read the current stage entry shape from PIPELINE_PATH and normalize.
read -r STAGE_AGENTS STAGE_TDD_PARALLEL STAGE_UNITS_COUNT STAGE_STREAMING_REVIEW < <(python3 -c "
import json
p = json.load(open('${PIPELINE_PATH}'))
stage = p['stages'][${i} - 1]
if isinstance(stage, str):
    agents = [stage]; tdd = False; units = 0; stream = False
elif isinstance(stage, list):
    agents = stage;   tdd = False; units = 0; stream = False
elif isinstance(stage, dict):
    agents = stage.get('agents', [])
    tdd    = bool(stage.get('tdd_parallel', False))
    units  = len(stage.get('parallelizable_units', []) or [])
    stream = bool(stage.get('streaming_review', False))
else:
    agents = []; tdd = False; units = 0; stream = False
print(' '.join(agents), '1' if tdd else '0', units, '1' if stream else '0')
")

# Streaming-review eligibility check: the flag is only honored when the
# IMMEDIATELY following stage is a single `reviewer` agent. Otherwise the
# supervisor logs one warning and disables the flag for this iteration —
# the existing dispatch paths run unchanged.
if [ "${STAGE_STREAMING_REVIEW}" = "1" ]; then
  NEXT_STAGE_OK=$(python3 -c "
import json
p = json.load(open('${PIPELINE_PATH}'))
stages = p.get('stages', [])
nxt_idx = ${i}  # 1-based ${i} indexes the next stage at offset 0+i in stages
if nxt_idx >= len(stages):
    print('0'); raise SystemExit
nxt = stages[nxt_idx]
if isinstance(nxt, str):
    agents = [nxt]
elif isinstance(nxt, list):
    agents = nxt
elif isinstance(nxt, dict):
    agents = nxt.get('agents', [])
else:
    agents = []
print('1' if agents == ['reviewer'] else '0')
")
  if [ "${NEXT_STAGE_OK}" != "1" ]; then
    log_progress "STAGE_STREAMING_REVIEW_INELIGIBLE" \
      "stage=${i} reason=next_stage_not_single_reviewer — falling back to sequential"
    STAGE_STREAMING_REVIEW=0
  fi
fi
```

Dispatch routing:

- `STAGE_UNITS_COUNT >= 2` selects the **Sub-Task Fan-Out** path
  documented in § Sub-Task Fan-Out Dispatch below. If
  `STAGE_TDD_PARALLEL == 1` is also set, the combined-mode rule in
  that section applies.
- `STAGE_UNITS_COUNT <= 1` AND `STAGE_TDD_PARALLEL == 1` selects the
  TDD parallel path below.
- Both `0` → fall through to the existing Single / Parallel Agents
  paths above — no regression for any pre-existing pipeline.json
  (including every pipeline that predates this feature).
- `STAGE_STREAMING_REVIEW == 1` (independent overlay) → after the
  selected dispatch composes its agent prompts, the supervisor ALSO
  composes a `reviewer` prompt in `MODE=streaming` and issues all
  agent calls (selected-dispatch agents + reviewer) in the same single
  host message. On joint success, the trailing reviewer stage is
  consumed: `completed_stages` advances by **2** instead of 1. See §
  Streaming Review Dispatch below for the spawn protocol.

#### Dispatch — both agents in one host message

When `STAGE_TDD_PARALLEL == 1`:

1. Compose **two** agent prompts (test-writer + each implementer in
   `STAGE_AGENTS`) using the standard Agent prompt format above. The
   test-writer prompt carries `STAGE_INDEX` and `IMPLEMENTER_AGENT`
   inputs so its commit message can reference both.

2. Emit the start event **before** dispatch:

   ```bash
   log_progress "STAGE_TDD_PARALLEL_STARTED" "stage=${i} agents=test-writer,${STAGE_AGENTS// /,}"
   ```

3. Issue both Agent tool calls in a **single response** (the host's
   parallel-spawn semantics — the same convention the existing
   Parallel Agents path uses). The supervisor's response message
   contains one Agent call per parallel partner; the host dispatches
   them concurrently.

   MVP scope: each TDD parallel stage carries exactly one implementer.
   `STAGE_AGENTS` may legally hold more than one entry (the schema
   allows it), but only the first implementer is co-spawned with
   test-writer in MVP. Stages with two or more implementers + TDD
   parallel are a follow-up; for MVP, the planner is instructed
   (`core/agents/planner.md` § TDD Parallel Stages and the analyst
   equivalent) to keep `agents` to a single entry when
   `tdd_parallel: true`.

4. The test-writer prompt MUST instruct the agent to read the spec
   only (it MUST NOT read the implementer's source). The
   `core/agents/test-writer.md` definition encodes this rule — the
   supervisor's only obligation is to pass `TASK_DIR`, `PROJECT_ROOT`,
   `HANDOFF_PATH`, `QUALITY_RULE_PATH`, `STAGE_INDEX`, and
   `IMPLEMENTER_AGENT` so the agent has the inputs it needs.

5. Wait for **both** agent calls to return. Per-agent status writes
   into `pipeline.json.stage_agent_status["${i}"]` use the same
   intermediate-write block documented in § Parallel Agents above:

   ```bash
   # Repeat for each of: test-writer and ${impl_agent}
   python3 -c "
   import json
   p = json.load(open('${PIPELINE_PATH}'))
   p.setdefault('stage_agent_status', {}).setdefault('${i}', {})['${agent_name}'] = '${status}'
   json.dump(p, open('${PIPELINE_PATH}', 'w'), ensure_ascii=False, indent=2)
   "
   ```

6. Emit the done event with both per-agent statuses:

   ```bash
   log_progress "STAGE_TDD_PARALLEL_DONE" \
     "stage=${i} test_status=${TEST_STATUS} impl_status=${IMPL_STATUS}"
   ```

7. Advance `completed_stages` only when **both** statuses are
   `completed`. If either is `crashed`, apply the Stage Retry Rule
   (`supervisor-retry.md`) to that agent only — selective retry, do
   not re-spawn the agent that already completed. If either is
   `blocked`, halt the pipeline per the BLOCKED Recovery contract.

#### File-conflict handling

The test-writer writes to the project's test directory; the implementer
writes to the project's source directory. The two output sets are
disjoint by convention, so resolver invocation is normally not
required.

If a `git commit` from either agent fails because of a merge conflict
on the same file (rare — typically only when the implementer creates a
test-adjacent fixture in the test directory, or the test-writer
extends an existing test file the implementer also touched), the
supervisor invokes the `resolver` agent before retrying the failed
agent — the same convention used for parallel-write conflicts in the
existing Parallel Agents path. The resolver's input is the
`git status` output identifying the conflicted paths; no other
plumbing change is needed.

#### Sequential-path fall-through

When `STAGE_TDD_PARALLEL == 0` (the absence case — bare string or
bare array stage entries), Phase 2 dispatch is unchanged from the
behavior documented in § Single Agent and § Parallel Agents above. The
TDD parallel block is opt-in by stage encoding; no pipeline that
predates this feature is affected.

### Sub-Task Fan-Out Dispatch

A stage entry may opt into **sub-task fan-out** ("mini fan-out within
a single supervisor") by attaching a
`parallelizable_units: [{id, files, brief}, ...]` array to the object
stage form. The schema doc
(`core/rules/state-files/pipeline-json.md` § Sub-Task Fan-Out stage
form) shows the wire shape. The dispatch contract below is what Phase
2 runs at stage entry when `STAGE_UNITS_COUNT >= 2`.

This is distinct from `crew:run N>1` supervisor-level fan-out: that
spawns N independent supervisors (one per task); this spawns N
parallel agents of the **same** type within a single supervisor's
single stage.

#### Read the unit list

When `STAGE_UNITS_COUNT >= 2`, load the units detail from
`PIPELINE_PATH` once at stage entry:

```bash
UNITS_JSON=$(python3 -c "
import json
p = json.load(open('${PIPELINE_PATH}'))
stage = p['stages'][${i} - 1]
print(json.dumps(stage.get('parallelizable_units', [])))
")
# UNITS_JSON is a JSON array of {id, files, brief}; STAGE_AGENTS holds
# the agent type to spawn (use STAGE_AGENTS[0] — the implementer).
```

#### Pre-flight overlap check (MVP — log only)

Walk the unit list once and detect any pair of units whose `files`
globs overlap. Overlap is rare when the planner did its job; when it
happens the supervisor logs the conflict (and surfaces it later in
`result.md` via the close-out report) but still proceeds with the
fan-out. Auto-invoking `resolver` on detected overlap is a documented
follow-up; for MVP we rely on the planner-side check.

```bash
OVERLAPS=$(python3 -c "
import json, fnmatch
units = json.loads('''${UNITS_JSON}''')
out = []
for i, a in enumerate(units):
    for b in units[i+1:]:
        for ga in a.get('files', []):
            for gb in b.get('files', []):
                if fnmatch.fnmatch(ga, gb) or fnmatch.fnmatch(gb, ga):
                    out.append(f\"{a['id']}↔{b['id']}: {ga} vs {gb}\")
print('; '.join(out))
")
if [ -n "${OVERLAPS}" ]; then
  log_progress "STAGE_FANOUT_CONFLICT" "stage=${i} conflicts=${OVERLAPS}"
  echo "${OVERLAPS}" >> "${TASK_DIR}/context/fanout-conflicts.log"
fi
```

The conflict log is appended (never truncated) so multiple stages with
fan-out can each contribute. The Phase 3 close-out reads this file (if
present) and surfaces a "## Fan-Out Conflicts (detected, not
auto-resolved)" section in `result.md`.

#### Dispatch — N agents in one host message

When `STAGE_UNITS_COUNT >= 2`:

1. Resolve the implementer agent name: `IMPL_AGENT="${STAGE_AGENTS%% *}"`
   (first entry in `STAGE_AGENTS`). For MVP, only the first entry is
   used as the fan-out type — multi-type fan-out within a single stage
   is a follow-up.

2. Compose **N** agent prompts, one per unit, using the standard
   Agent prompt format above. Each prompt additionally carries
   `UNIT_ID`, `UNIT_BRIEF`, and `UNIT_FILES` so the agent knows its
   sub-slice of the stage:

   ```text
   TASK_DIR: {TASK_DIR}
   PROJECT_ROOT: {PROJECT_ROOT}
   HANDOFF_PATH: {TASK_DIR}/handoff.md
   QUALITY_RULE_PATH: {QUALITY_RULE_PATH}
   UNIT_ID: {unit.id}
   UNIT_BRIEF: {unit.brief}
   UNIT_FILES: {comma-separated unit.files globs}

   You are running as a sub-task fan-out unit of stage {i}. Read the
   handoff and PRD as usual, then perform ONLY the work described in
   UNIT_BRIEF, scoped to the file globs in UNIT_FILES. Do not touch
   files outside UNIT_FILES — other parallel units own those globs.
   Do not modify handoff.md (sibling units are writing concurrently).
   ```

3. Emit the start event **before** dispatch:

   ```bash
   log_progress "STAGE_FANOUT_STARTED" \
     "stage=${i} units=${STAGE_UNITS_COUNT} type=${IMPL_AGENT}"
   ```

4. Issue all N Agent tool calls in a **single response** — the same
   host parallel-spawn convention used by § Parallel Agents and § TDD
   Parallel Dispatch above. The supervisor's response message
   contains one Agent call per unit; the host dispatches them
   concurrently.

   Combined mode (`STAGE_TDD_PARALLEL == 1` AND
   `STAGE_UNITS_COUNT >= 2`): co-spawn **one** `test-writer` in the
   same response alongside the N implementer units. The test-writer
   covers the contract that is shared across units. This is the
   advanced combination documented in
   `core/rules/state-files/pipeline-json.md` § Interaction with
   `tdd_parallel`; for MVP the planner is steered toward setting at
   most one of the two flags per stage.

5. As each unit returns, record its terminal status in
   `pipeline.json.stage_agent_status` under a composite key
   `<agent>:<unit_id>` so per-unit retries are addressable:

   ```bash
   # Repeat for each unit as it terminates.
   python3 -c "
   import json
   p = json.load(open('${PIPELINE_PATH}'))
   key = '${IMPL_AGENT}:${UNIT_ID}'
   p.setdefault('stage_agent_status', {}).setdefault('${i}', {})[key] = '${status}'
   json.dump(p, open('${PIPELINE_PATH}', 'w'), ensure_ascii=False, indent=2)
   "
   log_progress "STAGE_FANOUT_UNIT_DONE" \
     "stage=${i} unit=${UNIT_ID} status=${status}"
   ```

   In combined mode, the test-writer's status is recorded under its
   own (non-composite) key `test-writer`, matching the existing TDD
   parallel convention.

6. Wait for **all N** unit calls (plus the test-writer in combined
   mode) to return. Emit the done event:

   ```bash
   log_progress "STAGE_FANOUT_DONE" \
     "stage=${i} units=${STAGE_UNITS_COUNT} all_status=${ALL_STATUS_CSV}"
   ```

   `ALL_STATUS_CSV` is a compact summary like
   `orders=completed,products=completed,carts=crashed` so a downstream
   log reader can identify which unit failed without reading
   `pipeline.json`.

7. Advance `completed_stages` only when **every** unit (and, in
   combined mode, the test-writer) is `completed`:

   ```bash
   python3 -c "
   import json
   p = json.load(open('${PIPELINE_PATH}'))
   stage_status = p.get('stage_agent_status', {}).get('${i}', {})
   all_done = stage_status and all(v == 'completed' for v in stage_status.values())
   if all_done:
       p['completed_stages'] = ${i}
       json.dump(p, open('${PIPELINE_PATH}', 'w'), ensure_ascii=False, indent=2)
   "
   ```

#### Selective per-unit retry

If one or more units (or the combined-mode test-writer) crash, do NOT
re-spawn the whole fan-out. Apply the Stage Retry Rule
(`supervisor-retry.md`) **per unit** — only failed units get retried.
Units that returned `STATUS: completed` are not re-invoked.

The retry-key vocabulary widens to include the composite
`<agent>:<unit_id>` form so the retry counter and the host-task DAG
mirror (when enabled) both address the correct sub-task. The Stage
Retry Rule's crash and validation budgets (5 / 3) apply per unit, not
per stage.

If, after exhausting retries, any unit remains `crashed` or `blocked`,
the stage as a whole is BLOCKED — apply the standard BLOCKED Recovery
contract (write result.md, halt).

#### File-conflict handling (MVP)

Each unit's `files` globs SHOULD be disjoint by planner contract. When
two units' git commits land on the same path (which the planner's
overlap check should have prevented), the supervisor logs the
conflict to `${TASK_DIR}/context/fanout-conflicts.log` (the same file
written by the pre-flight overlap check) and surfaces it in
`result.md`. MVP scope does not auto-invoke the `resolver` agent —
that integration is a documented follow-up. The user (or a manual
follow-up task) can invoke `resolver` against the conflict log
post-hoc.

#### Sequential-path fall-through

When `STAGE_UNITS_COUNT <= 1` (absent field, or length-1 array), Phase
2 dispatch is unchanged — the TDD-parallel routing or the Single /
Parallel Agents path applies depending on `STAGE_TDD_PARALLEL` and the
agents-list shape. The Sub-Task Fan-Out block is opt-in by stage
encoding; no pipeline that predates this feature is affected.

### Streaming Review Dispatch

A stage entry may opt into **streaming review** by setting
`streaming_review: true` on the object stage form (see
`core/rules/state-files/pipeline-json.md` § Streaming Review stage
form). When the normalization block above sets
`STAGE_STREAMING_REVIEW == 1` (eligibility confirmed — the *next*
stage is a single `reviewer` agent), the supervisor co-spawns the
reviewer in `MODE=streaming` alongside this stage's selected dispatch
in a single host message. The reviewer polls `git log
<pre-stage-head>..HEAD` as new commits land, terminating once this
stage's implementer reports `completed`. On joint success the trailing
reviewer stage is **consumed** — `completed_stages` advances by 2 in
one update.

This overlay is orthogonal to § Single Agent, § Parallel Agents, § TDD
Parallel Dispatch, and § Sub-Task Fan-Out Dispatch: any of those paths
may carry the streaming reviewer in the same host message.

#### Capture the pre-stage HEAD

The reviewer needs an immutable starting point for its `git log` poll.
Capture HEAD **before** issuing the host dispatch:

```bash
PRE_STAGE_HEAD=$(git -C "${PROJECT_ROOT}" rev-parse HEAD 2>/dev/null || echo "")
echo "${PRE_STAGE_HEAD}" > "${TASK_DIR}/context/streaming-review-head-${i}.txt"
```

The per-stage filename allows multiple streaming-review stages in a
single pipeline to coexist (each reviewer reads its own HEAD file).
The Phase 3 close-out preserves these files for audit; no per-stage
cleanup is required.

#### Dispatch — selected agents + reviewer in one host message

1. The selected dispatch (Single Agent / Parallel Agents / TDD Parallel
   / Sub-Task Fan-Out) composes its N agent prompts as documented in
   the section it owns. **Do not modify** those prompts — the streaming
   overlay only adds one extra agent to the same host message.

2. Compose the reviewer prompt using the standard Agent prompt format
   above, with three additional inputs:

   ```text
   TASK_DIR: {TASK_DIR}
   PROJECT_ROOT: {PROJECT_ROOT}
   HANDOFF_PATH: {TASK_DIR}/handoff.md
   QUALITY_RULE_PATH: {QUALITY_RULE_PATH}
   MODE: streaming
   PRE_STAGE_HEAD: {captured value}
   WATCH_STAGE_INDEX: {i}
   WATCH_AGENT: {first entry of STAGE_AGENTS — the implementer to poll}

   You are running as the streaming reviewer for stage {i}. Poll
   `git log PRE_STAGE_HEAD..HEAD` on branch {BRANCH} every 15 seconds.
   Review each NEW commit incrementally per your streaming-mode
   workflow (see core/agents/reviewer.md § Streaming Mode). Terminate
   when pipeline.json.stage_agent_status["{i}"]["{WATCH_AGENT}"] ==
   "completed" OR a STAGE_DONE line for {WATCH_AGENT} appears in
   progress.log. Then do one final drain poll and emit the aggregate
   REVIEW verdict.
   ```

   In Sub-Task Fan-Out combined mode, `WATCH_AGENT` is the unqualified
   implementer name (`STAGE_AGENTS[0]`); the reviewer watches the
   whole branch so per-unit commits are covered by the same `git log`
   poll without needing per-unit awareness.

3. Emit the start event **before** dispatch:

   ```bash
   log_progress "STAGE_STREAMING_REVIEW_STARTED" \
     "stage=${i} reviewing=${STAGE_AGENTS%% *}"
   ```

4. Issue all agent calls (selected-dispatch agents + reviewer) in a
   **single response** — the same host parallel-spawn convention used
   by § Parallel Agents, § TDD Parallel Dispatch, and § Sub-Task
   Fan-Out Dispatch. The supervisor's response message contains one
   Agent call per partner; the host dispatches them concurrently.

5. As the streaming reviewer's incremental work proceeds, each
   per-commit verdict is appended to
   `${TASK_DIR}/context/review-stream.md` by the reviewer (the running
   ledger format is documented in `core/agents/reviewer.md`). The
   supervisor does NOT need to poll the ledger — the reviewer
   completes when the implementer's `stage_agent_status` flips to
   `completed`, and emits its own
   `STAGE_STREAMING_REVIEW_INCREMENTAL` log lines via the helper as it
   reviews each commit. The supervisor's only obligation during dispatch
   is to wait for both/all agents to return.

#### Per-agent terminal status

Reuse the per-agent intermediate-write block from § Parallel Agents
verbatim — one write per partner as it terminates. The reviewer's
status key is the literal string `reviewer` under
`stage_agent_status["${i}"]`, matching the TDD parallel convention
(test-writer / implementer use their own un-prefixed names).

#### Advance `completed_stages` by 2

On the joint-success path (every selected-dispatch agent + the
reviewer all reach `completed`), the trailing reviewer stage is
consumed. Use a single combined write that advances `completed_stages`
by **2** in one operation:

```bash
python3 -c "
import json
p = json.load(open('${PIPELINE_PATH}'))
stage_status = p.get('stage_agent_status', {}).get('${i}', {})
all_done = stage_status and all(v == 'completed' for v in stage_status.values())
if all_done:
    # Consume both this stage and the trailing reviewer stage in one write.
    p['completed_stages'] = ${i} + 1
    json.dump(p, open('${PIPELINE_PATH}', 'w'), ensure_ascii=False, indent=2)
"
```

> The `+ 1` (not `+ 2`) reflects that `${i}` is 1-based: this stage's
> completion sets `completed_stages = ${i}`, and consuming the trailing
> reviewer stage sets it to `${i} + 1`. The stage loop's existing
> "skip stages already in `completed_stages`" rule then skips the
> reviewer stage at iteration `${i} + 1` automatically — no second
> spawn occurs.

Emit the done event with the reviewer's final verdict (extracted from
the reviewer agent's `REVIEW: APPROVED | NEEDS_CHANGES` return line,
mapped to `ok` / `blocked` for the event detail):

```bash
COMMITS_REVIEWED=$(wc -l < "${TASK_DIR}/context/review-stream.md" 2>/dev/null | tr -d ' ' || echo 0)
log_progress "STAGE_STREAMING_REVIEW_DONE" \
  "stage=${i} commits_reviewed=${COMMITS_REVIEWED} final_verdict=${REVIEWER_VERDICT}"
```

Where `${REVIEWER_VERDICT}` is `ok` when the reviewer returned
`REVIEW: APPROVED` and `blocked` when it returned `REVIEW:
NEEDS_CHANGES`. The reviewer's `verification_status` register update
(see § Stage progress emits — Phase F4 reviewer-stage verification
status bump) ALSO fires for the streaming reviewer, using the
reviewer's `REVIEW:` line exactly as in the sequential `final` path.

#### Selective retry semantics

If the implementer crashes but the reviewer completed cleanly (or the
inverse), apply the Stage Retry Rule to the failed agent only —
selective retry, matching the § TDD Parallel Dispatch convention. A
reviewer that crashes mid-stream is restarted from the same
`PRE_STAGE_HEAD` (the file written above is the source of truth — no
re-derivation needed) so it can re-traverse all commits the previous
attempt already covered. The reviewer's streaming mode is idempotent
on `review-stream.md`: it appends-with-dedupe on commit SHA, so a
restart does not duplicate findings.

If, after exhausting retries, either the implementer or the reviewer
remains crashed/blocked, the stage as a whole is BLOCKED — apply the
standard BLOCKED Recovery contract (write result.md, halt). In that
case `completed_stages` is NOT advanced; on resume the supervisor
re-enters this stage from scratch and re-issues the streaming dispatch
(reading `PRE_STAGE_HEAD` again, possibly re-capturing it if the file
is missing).

#### Termination trade-off (documented)

Streaming review may flag issues in commits that get fixed up by later
commits in the same stage (e.g. an early commit introduces a TODO that
the implementer resolves three commits later). The reviewer's
streaming mode re-checks the running ledger on each commit and demotes
prior findings whose target file/line has been re-touched in a later
commit (`core/agents/reviewer.md` § Streaming Mode — Re-check rule).
This is best-effort; the final aggregate `review.md` is the
authoritative verdict and is re-derived from the current branch HEAD
at termination, not from the running ledger alone.

#### Sequential-path fall-through

When `STAGE_STREAMING_REVIEW == 0` (the absence case — missing field,
false value, or ineligible trailing stage), Phase 2 dispatch is
unchanged. The reviewer stage runs sequentially in its own iteration
of the stage loop, exactly as documented in § Single Agent. The
Streaming Review Dispatch block is opt-in by stage encoding; no
pipeline that predates this feature is affected.

#### Post-stage handoff page-out (Phase 3.5, opt-in)

After each stage's terminal completion has been recorded
(`completed_stages` incremented, `STAGE_DONE` emitted), measure
`handoff.md` and conditionally invoke the documenter in `MODE=page-out`
to keep the per-stage working set bounded. The supervisor never reads
`handoff.md` contents directly — only its size via `wc -m`.

**Default: disabled.** When `AGENT_CREW_HANDOFF_AUTO_PAGEOUT` is unset
or any value other than `1`, skip the entire block — do not measure,
do not log. Behavior is identical to pre-3.5.

When enabled:

```bash
if [ "${AGENT_CREW_HANDOFF_AUTO_PAGEOUT:-0}" = "1" ]; then
  HANDOFF_SIZE=$(wc -m < "${TASK_DIR}/handoff.md" 2>/dev/null | tr -d ' ' || echo 0)
  THRESHOLD="${AGENT_CREW_HANDOFF_PAGEOUT_THRESHOLD:-8000}"
  if [ "${HANDOFF_SIZE:-0}" -gt "${THRESHOLD}" ] 2>/dev/null; then
    # Stateless counter: count existing handoff-*.md archives, add 1.
    ARCHIVE_NUM=$(ls "${TASK_DIR}/archive/handoff-"*.md 2>/dev/null | wc -l | tr -d ' ')
    ARCHIVE_NUM=$((ARCHIVE_NUM + 1))
    log_progress "HANDOFF_PAGEOUT" "size=${HANDOFF_SIZE} threshold=${THRESHOLD} → archive/handoff-${ARCHIVE_NUM}.md"
    # Spawn documenter in page-out mode (sequential, blocking).
    # Prompt format:
    #   TASK_DIR: {TASK_DIR}
    #   PROJECT_ROOT: {PROJECT_ROOT}
    #   HANDOFF_PATH: {TASK_DIR}/handoff.md
    #   QUALITY_RULE_PATH: {QUALITY_RULE_PATH}
    #   MODE: page-out
    #   ARCHIVE_NUM: {ARCHIVE_NUM}
    #   HANDOFF_SIZE: {HANDOFF_SIZE}
    # On STATUS: completed → log HANDOFF_PAGEDOUT with pre/post sizes.
    # On STATUS: BLOCKED → log HANDOFF_PAGEOUT_FAILED and continue.
  fi
fi
```

Per `core/rules/quality-loop.md` § Page-Out As Hygiene Operation:

- The page-out call **counts** against the cost circuit breaker total
  (light-tier LLM call). If the cost breaker is already at `exceeded`,
  skip the page-out (log `HANDOFF_PAGEOUT_SKIPPED | reason=cost_exceeded`)
  and continue with the un-paged handoff.
- The page-out call **does not** have its own validation/crash retry
  budget. On `STATUS: BLOCKED` or crash, log `HANDOFF_PAGEOUT_FAILED`
  and continue. Page-out failures NEVER increment the just-completed
  stage's retry counters and NEVER fail the pipeline.
- Page-out is **out of band** of stage retries.

**Re-entrancy guard.** The page-out invocation does not itself trigger a
nested page-out check. Even if the documenter's digest were larger than
the threshold (it should not be), the next size check fires only after
the *next* stage completes — never recursively inside the page-out
spawn.

**After the stage loop completes (all non-devops stages done), proceed to Phase 2.5 — do NOT skip to Phase 3.** Phase 2.5 is always entered after Phase 2, whether or not any stage returned `STATUS: plan_ready`.

---

### Phase 2.5: Stage Action Gate

At Phase 2.5 entry, bump the register:

```bash
register_update current_phase phase_2_5
```

The supervisor owns all approval decisions for its pipeline. Stage agents
(devops, reviewer, etc.) MUST NOT issue their own host interactive question
mechanism (see `core/rules/capabilities/interactive-question.md`) for deploy,
merge, push, or destructive operations. Instead they write a PLAN block and wait.

**This phase runs unconditionally after Phase 2 completes.** Do not treat it as conditional on receiving a PLAN: block — it always runs. Within this phase:
- **Step 2** (collect PLAN blocks) runs only when at least one stage returned `STATUS: plan_ready`.
- **Step 3** (devops approval gate) always runs when `EXECUTION_MODE == single`, regardless of whether any stage returned a PLAN: block.

#### Step 1 — Always display the implementation summary

```text
## 🛠️ Implementation Summary

\`\`\`
Branch  : {BRANCH}  ({N} commits)
Commits :
  {git -C PROJECT_ROOT log --oneline HEAD ^main, up to 10 lines}
\`\`\`

> No remote push has occurred yet.
```

Collect the commit log:

```bash
git -C "${PROJECT_ROOT}" log --oneline HEAD ^main 2>/dev/null | head -10
```

#### Step 2 — Collect PLAN blocks from stage agents

When a stage agent returns a `PLAN:` block (instead of executing), the supervisor:

1. Collects PLAN blocks from all stage agents in the current execution group
2. Writes a consolidated plan to `{TASK_DIR}/context/action-plan.md`:

   ```markdown
   # Action Plan

   ## Stage: {stage_name}

   ### Planned Actions
   {list of planned commands from PLAN block}

   ### Risk
   {none | low | medium | high}

   ### Reversible
   {yes | no}
   ```

3. If `EXECUTION_MODE == parallel`: writes `PLAN_READY` to
   `{TASK_DIR}/context/approval.md`. The file is the canonical artifact the
   orchestrator's fan-in reads; it MUST always be written even when host tasks
   are also used.

   **P1 — capability-gated event wait (preferred path when `HAS_TASK_TOOLS == 1`).**
   When the parent host task exists (its id was written to
   `${TASK_DIR}/host-task-id.txt` in Phase 0), the supervisor additionally
   signals plan-readiness via the host task surface and waits on event
   transition instead of polling the file every 5 seconds:

   ```text
   # Carry the action plan and the readiness marker on the parent host task so
   # the orchestrator's TaskList fan-in (P2) can detect "all PLAN_READY" in one
   # round-trip. metadata.action_plan_path keeps the plan body file-based.
   TaskUpdate(
     taskId=$(cat "${TASK_DIR}/host-task-id.txt"),
     status="blocked",
     metadata={
       "task_id": TASK_ID,
       "stage": "plan_ready",
       "action_plan_path": "${TASK_DIR}/context/action-plan.md"
     }
   )

   # Wait on host event transition. TaskGet returns instantly on state change
   # (no polling cadence to choose). Loop with a short fallback sleep so the
   # path remains correct even if TaskGet returns immediately.
   ELAPSED=0
   while [ $ELAPSED -lt 60 ]; do
     HOST_STATUS=$(TaskGet(taskId).status)
     # in_progress = APPROVED, cancelled = CANCELLED, anything else keep waiting
     if [ "$HOST_STATUS" = "in_progress" ]; then
       echo "APPROVED" > "${TASK_DIR}/context/approval.md"
       break
     fi
     if [ "$HOST_STATUS" = "cancelled" ]; then
       echo "CANCELLED" > "${TASK_DIR}/context/approval.md"
       break
     fi
     # Long-poll: TaskGet wake-on-change is preferred but a 1-second guard
     # bounds the busy-wait if the host returns synchronously.
     sleep 1
     ELAPSED=$((ELAPSED + 1))
   done
   ```

   **Fallback when `HAS_TASK_TOOLS == 0`** (or any TaskGet/TaskUpdate call
   raises): the legacy file-poll loop is the primary path, unchanged from
   pre-P1 behavior:

   ```bash
   echo "PLAN_READY" > "${TASK_DIR}/context/approval.md"
   ELAPSED=0
   while [ $ELAPSED -lt 60 ]; do
     RESULT=$(cat "${TASK_DIR}/context/approval.md" 2>/dev/null)
     if echo "$RESULT" | grep -q "^APPROVED$\|^CANCELLED$"; then
       break
     fi
     sleep 5
     ELAPSED=$((ELAPSED + 5))
   done
   if ! echo "$RESULT" | grep -q "^APPROVED$"; then
     echo "CANCELLED" > "${TASK_DIR}/context/approval.md"
   fi
   ```

   Both paths converge on the same `approval.md` artifact, so any consumer that
   reads the file after the wait sees identical content regardless of which
   wakeup mechanism fired. The file write is the contract; the host call is
   only the wakeup signal.

4. If `EXECUTION_MODE == single`: the supervisor issues the structured
   user-choice intent (per `core/rules/capabilities/interactive-question.md`)
   directly (see Step 3 below) and writes the result to `approval.md` itself.

#### Step 3 — Conditional approval gate (N == 1, devops stage only)

This step applies only when `EXECUTION_MODE == single`.

Check whether the pipeline contains a `devops` stage (use the cached
`PIPELINE_PATH` variable resolved in Phase 0 — do not re-derive the path):

```bash
python3 -c "
import json
p = json.load(open('${PIPELINE_PATH}'))
has_devops = any('devops' in stage for stage in p.get('stages', []))
print('yes' if has_devops else 'no')
"
```

**If no devops stage is present:** skip this gate entirely and proceed to Phase 3.
Branches remain local; the crew orchestrator or user can push manually.

**If a devops stage is present:** emit a **structured user-choice intent** (per
`core/rules/capabilities/interactive-question.md`) to request approval before
executing the devops stage. Do not run the devops stage without approval. This
is the single consolidated approval gate for this pipeline — do not delegate it
to the devops agent.

Question:
- header: "Deploy"
- question: "Implementation is complete. Review the action plan above. Approve to run the devops stage (CI/CD + git push), or cancel to skip deployment and keep commits local."
- options:
  - label: "Approve"
    description: "Run devops stage now"
  - label: "Cancel"
    description: "Skip devops, keep commits local"

If **Approve**:
  - Write `APPROVED` to `{TASK_DIR}/context/approval.md` (canonical artifact).
  - Update register: `register_update approval_status approved`.
  - If `HAS_TASK_TOOLS == 1` and `${TASK_DIR}/host-task-id.txt` exists, also
    transition the parent host task to `in_progress` so any devops-poll-loop
    based on `TaskGet` (P1) wakes up immediately:

    ```text
    TaskUpdate(taskId=$(cat "${TASK_DIR}/host-task-id.txt"), status="in_progress")
    ```

    The file write remains the contract — the host call is only a wakeup
    signal. Skip silently when the capability flag is `0`.
  - Spawn the devops stage agent now using the standard agent prompt format.
  - After the devops agent returns, check its `STATUS` field:
    - `STATUS: completed` → devops stage succeeded. Proceed to Phase 3.
    - `STATUS: plan_ready` → the devops agent submitted a secondary plan
      (e.g. it needs further confirmation for a specific destructive sub-step).
      Collect its PLAN block, write it to `{TASK_DIR}/context/action-plan.md`
      (appending under a new `## Sub-plan` section), and repeat the
      structured user-choice intent loop (Step 3) for the sub-plan before continuing.
    - `STATUS: BLOCKED` → write the blocker to `{TASK_DIR}/result.md` and
      return `STATUS: blocked` to the orchestrator.
    - No STATUS line → treat as a crash; apply the Stage Retry Rule (up to 5
      crash attempts). After 5 failures, write BLOCKED to result.md and stop.

If **Cancel**:
  - Write `CANCELLED` to `{TASK_DIR}/context/approval.md`.
  - Update register: `register_update approval_status cancelled`.
  - If `HAS_TASK_TOOLS == 1` and `${TASK_DIR}/host-task-id.txt` exists, also
    transition the parent host task to `cancelled` so a `TaskGet` waiter wakes
    immediately and stops blocking:

    ```text
    TaskUpdate(taskId=$(cat "${TASK_DIR}/host-task-id.txt"), status="cancelled")
    ```
  - Mark the devops stage as skipped (do not update `completed_stages` for it).
  - Print the branch name so the user can push manually later.
  - Proceed directly to Phase 3 without running the devops stage.


---

After Phase 2.5 returns (approve, cancel, or skip), transition to
Phase 3 — `supervisor-retry.md` is already in the working set (loaded
for Stage Retry Rule access during Phase 2); re-Read if it was evicted.
