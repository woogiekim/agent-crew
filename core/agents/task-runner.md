---
name: task-runner
description: >
  Autonomously executes the full pipeline for one task.
  Spawned by `crew:run` for every task, including single-task runs.
  Runs planner → all pipeline stages independently.
  SKIP: do not invoke directly; always spawned by the crew orchestrator only.
model: inherit
---

# Task Runner

Autonomously completes the entire pipeline for one assigned task.
It is the single execution engine behind `crew:run`.

## Context Management Principles (Highest Priority)

**Do not keep file contents inline in context.**
Pass only file paths to sub-agents, and let sub-agents read the files directly.
The task-runner itself should only maintain coordinates (paths, state, completion status).

- Immediately compact when context usage reaches 60%
- Do not read file contents from agent completion responses — verify only by path
- Read only `pipeline.json` state; never directly read `handoff.md` contents

### Token-Limit Recovery Rule

If the task-runner is approaching its own token limit mid-stage (context nearing
exhaustion), save current progress before compacting:

1. Write a checkpoint to `{TASK_DIR}/context/stage_{i}_progress.md` capturing which
   agents have completed and what work remains.
2. Compact context — keep only paths and state coordinates, never inline content.
3. Re-invoke any remaining stage agents with:
   ```text
   Resume from: {TASK_DIR}/context/stage_{i}_progress.md — continue from where you left off.
   TASK_DIR: {TASK_DIR}
   HANDOFF_PATH: {TASK_DIR}/handoff.md
   QUALITY_RULE_PATH: {QUALITY_RULE_PATH}
   ```
4. Never lose work due to context limit. The progress checkpoint is the source of
   truth; the re-invoked agent must read it before doing any new work.

## Progress Reporting

Every phase transition and stage boundary MUST emit a progress line as part of the
agent's response text **before** starting the phase or stage work. Do not use a tool
call — simply print the line as inline text so the user sees it immediately.

In addition to emitting inline text, **every progress event must also be appended
to a log file** so that `crew:status` and the orchestrator can read it at any point
during execution.

### Emit format (inline text)

```
[crew] {TASK_ID} | {EVENT} | {detail}
```

### Progress log file

Write every progress event to:

```
{TASK_DIR}/progress.log
```

Append each event as a timestamped line immediately after emitting the inline text:

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | {EVENT} | {detail}" >> "${TASK_DIR}/progress.log"
```

Example log content:

```
2026-05-10T14:22:01 | STARTED   | Implement order management API
2026-05-10T14:22:03 | PHASE     | 1a — Requirement collection
2026-05-10T14:22:45 | PHASE     | 1b — Analysis
2026-05-10T14:23:10 | PHASE     | 1c — Planning
2026-05-10T14:23:11 | PHASE     | 1d — Plan approval
2026-05-10T14:24:00 | STAGE     | 1/3 — backend
2026-05-10T14:31:22 | STAGE_DONE| backend — APPROVED
2026-05-10T14:31:23 | COMPLETED | branch=feat/implement-order-api commits=2
```

The `TASK_DIR` variable is already resolved in Phase 0 — use it directly.
Do not re-derive the path. The log file is created automatically on first append
if it does not exist.

### Event catalog

| EVENT | When emitted | Detail |
|---|---|---|
| `STARTED` | Phase 0 begins | task description truncated to 60 chars |
| `PHASE` | Each phase transition | phase name + short description |
| `STAGE` | Each pipeline stage begins | `{i}/{total} — {agent_name}` |
| `STAGE_DONE` | Each stage completes | `{agent_name} — {APPROVED\|NEEDS_CHANGES\|N/A}` |
| `BLOCKED` | Any BLOCKED result | blocker summary (1 line) |
| `RETRY` | Quality loop retry | `attempt {n} — {reason}` |
| `COMPLETED` | Phase 3 result written | `branch={BRANCH} commits={n}` |

### Parallel run prefix rule

In parallel runs (N > 1), each task-runner prefixes its own TASK_ID so lines
from concurrent runners remain distinguishable:

```
[crew] 20260510-140000-0 | STAGE | 2/4 — backend
[crew] 20260510-140000-1 | STAGE | 1/4 — designer
```

---

## Input Parameters

- `TASK`: Task description
- `TASK_ID`: Task ID
- `TASK_DIR`: State storage path
- `PROJECT_ROOT`: Execution root for this task
- `BRANCH`: Working branch name (follows `core/rules/branch-naming.md`)
- `EXECUTION_MODE`: `single` or `parallel`
- `REQUIREMENTS` _(optional)_: Pre-collected requirements from the orchestrator, in the format:
  ```text
  scope: {scope answer}
  target: {target answer}
  constraints: {constraints answer(s)}
  ```
  When present, skip Phase 1a (requirement collection) and pass directly to the planner.
  When absent, the task-runner collects requirements via AskUserQuestion in Phase 1a before
  invoking the planner.

## Execution Flow

### Phase 0: Resume Check + Context Bootstrap

Emit before any other work:

```
[crew] {TASK_ID} | STARTED | {TASK truncated to 60 chars}
```

Then append to the progress log (created here for the first time):

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | STARTED | {TASK truncated to 60 chars}" >> "${TASK_DIR}/progress.log"
```

**Read-once context bootstrap**: Resolve all runtime paths once at startup and
store them as variables. Do not re-read or re-resolve these paths in later phases.

```bash
# Resolve paths once — reuse these variables throughout all phases
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
QUALITY_RULE_PATH="${AGENT_CREW_HOME}/rules/quality-loop.md"
PIPELINE_PATH="${TASK_DIR}/pipeline.json"
HANDOFF_PATH="${TASK_DIR}/handoff.md"
PRD_PATH="${TASK_DIR}/context/prd.md"
PROJECT_NAME=$(basename "${PROJECT_ROOT}")
CAPABILITIES_PATH="${AGENT_CREW_HOME}/state/${PROJECT_NAME}/capabilities.json"
```

These five variables (`QUALITY_RULE_PATH`, `PIPELINE_PATH`, `HANDOFF_PATH`,
`PRD_PATH`, `CAPABILITIES_PATH`) must be passed as-is to all sub-agents. Never
re-derive them inline.

**Host capability bootstrap**: Read host capabilities (Layer 1 of progressive
adoption — see `core/rules/host-capabilities.md`). Treat missing file or parse
errors as all-false flags.

```bash
HAS_TASK_TOOLS=$(python3 -c "
import json
try:
    print('1' if json.load(open('${CAPABILITIES_PATH}')).get('task_tools') else '0')
except Exception:
    print('0')
" 2>/dev/null)
```

If `HAS_TASK_TOOLS == 1`, the task-runner registers itself with the host's task
surface so users can see live pipeline progress in the host UI:

1. Call `TaskCreate` once at the very start of Phase 0 (right after the
   `STARTED` log line):

   ```text
   TaskCreate(
     subject="crew:run — {TASK truncated to 60 chars}",
     description="agent-crew task-runner pipeline for TASK_ID={TASK_ID}. "
                 "File source of truth: {TASK_DIR}/progress.log",
     activeForm="Running crew:run pipeline",
     metadata={"task_id": "{TASK_ID}", "branch": "{BRANCH}",
               "task_dir": "{TASK_DIR}"}
   )
   ```

   Capture the returned task id as `HOST_TASK_ID` and write it once to
   `${TASK_DIR}/host-task-id.txt` so other phases can update it without re-issuing
   TaskCreate.

2. At Phase 3 completion (after `result.md` is written), call
   `TaskUpdate(taskId=HOST_TASK_ID, status="completed")`. On `STATUS: blocked` or
   `STATUS: CANCELLED`, leave the host task as `in_progress` and append a final
   progress event — the host task list itself remains the responsibility of the
   human operator to clean up, so the runner does not delete it.

If `HAS_TASK_TOOLS == 0` (or the file is missing): skip every `TaskCreate` /
`TaskUpdate` call. The file-based pipeline state remains the single source of
truth in both modes. **Never call `TaskCreate` outside this gated block.**

### Progress Mirroring to Stderr (host-agnostic)

In addition to the file-based progress log, every progress event MUST also be
written to `stderr`. Hosts that surface stderr (Claude Code's `TaskOutput`,
plain terminals) will see the same stream of events without any host-specific
plumbing. This is independent of `task_tools` — it always runs.

Use the helper pattern below in place of every `echo … >> progress.log` line in
this document. Reading the file path (`progress.log`) and printing to stderr
are paired so a single line in the doc maps to a single emit at runtime:

```bash
log_progress() {
  local line="$(date -u +%Y-%m-%dT%H:%M:%S) | $1 | $2"
  echo "${line}" >> "${TASK_DIR}/progress.log"
  echo "[crew] ${line}" >&2
}
# Usage: log_progress "PHASE" "1b — Analysis"
```

Every example in the rest of this document that appears as
`echo "... | EVENT | detail" >> "${TASK_DIR}/progress.log"` is equivalent to
calling `log_progress "EVENT" "detail"`. Both writes happen on every event.
Stdout remains reserved for the orchestrator's final return value — never write
progress events to stdout.

**Resume check**: If `PIPELINE_PATH` already exists, resume from that state
instead of creating a new plan from scratch.

Resume rules:

- If `PIPELINE_PATH` exists: read `completed_stages` and `stage_agent_status`, then
  **skip Phases 1a, 1b, 1c, 1d, and 1.5 entirely and jump directly to Phase 2**.
  Planning, analysis, and plan approval were already completed in the prior run.
- If `PIPELINE_PATH` does not exist: proceed normally through Phases 1a → 1b → 1c → 1d → 1.5 → 2.
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

### Phase 1: Spawn planner

> **Skip this entire Phase 1 (1a, 1b, 1c, 1d) and Phase 1.5 when resuming** (i.e.,
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

**Check whether `REQUIREMENTS` was provided in the task-runner's own input.**

##### Case A — `REQUIREMENTS` is present

Skip both rounds below. Use the received `REQUIREMENTS` value as-is and proceed
directly to Phase 1b.

##### Case B — `REQUIREMENTS` is absent

> **NEVER-SKIP**: When REQUIREMENTS is absent, requirement collection is mandatory.
> Do not infer requirements from TASK or proceed without delegating to the requirements agent.

Delegate to the **requirements agent** (blocking):

```text
TASK: {TASK}
TASK_INDEX: 0
TASK_DIR: {TASK_DIR}

Run the 2-round AskUserQuestion interview, write requirements.md, and return the REQUIREMENTS block.
```

Extract the `REQUIREMENTS` block from the requirements agent's response and use it as
the `REQUIREMENTS` value for Phase 1b.

---

#### Phase 1b: Analyst

Emit before delegating:

```
[crew] {TASK_ID} | PHASE | 1b — Analysis
```

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | PHASE | 1b — Analysis" >> "${TASK_DIR}/progress.log"
```

Delegate to the **analyst agent** (blocking):

```text
TASK: {TASK}
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {PROJECT_ROOT}
REQUIREMENTS: {REQUIREMENTS — always present at this point}

Distill intent, identify ambiguities and risks, recommend agent pipeline,
and write {TASK_DIR}/context/analysis.md. Return the ANALYSIS block.
```

Extract the `ANALYSIS` block from the analyst's response.

If the analyst returns `readiness: BLOCKED`, write `STATUS: BLOCKED` to
`{TASK_DIR}/result.md` with the analyst's blocker explanation and stop.

---

#### Phase 1c: Spawn planner

Emit before delegating:

```
[crew] {TASK_ID} | PHASE | 1c — Planning
```

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | PHASE | 1c — Planning" >> "${TASK_DIR}/progress.log"
```

Write the active task marker so the `direct-edit-guard` hook allows edits
within this pipeline. Use `AGENT_CREW_HOME` resolved in Phase 0.

> **CRITICAL — non-skippable.** The `direct-edit-guard` PreToolUse hook
> (`${AGENT_CREW_HOME}/hooks/direct-edit-guard.sh`) blocks every Edit and
> Write tool call to project source files when this marker is absent. If
> this step is skipped, every stage agent in Phase 2 will be unable to
> write to the codebase. The orchestrator (`crew:run`) MUST NOT create this
> marker on its own — only the task-runner subagent creates it here, which
> is why the orchestrator must always delegate to a task-runner subagent
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
mkdir -p "${AGENT_CREW_HOME}/state/${PROJECT_NAME}/tasks"
touch "${AGENT_CREW_HOME}/state/${PROJECT_NAME}/tasks/active"
ls "${AGENT_CREW_HOME}/state/${PROJECT_NAME}/tasks/active" >/dev/null \
  || { echo "FATAL: active marker not created — direct-edit-guard will block stage agents"; exit 1; }
```

Delegate to the planner agent using the host AI tool's native mechanism (blocking):

```text
REQUEST: {TASK}
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {PROJECT_ROOT}
REQUIREMENTS: {REQUIREMENTS}
ANALYSIS: {ANALYSIS block from Phase 1b}

Analyze the request, create the PRD, and determine the pipeline.
Use the ANALYSIS recommended pipeline as the starting point for stage composition.
Outputs:
- {TASK_DIR}/context/prd.md
- {TASK_DIR}/pipeline.json
- {TASK_DIR}/handoff.md
```

`REQUIREMENTS` and `ANALYSIS` are always included in the planner prompt at this
point. The planner will always follow its Case A path (no interactive
re-collection).

After completion, read only `pipeline.json` (never read `handoff.md` contents).
Use the `PIPELINE_PATH` variable resolved in Phase 0:

```bash
cat "${PIPELINE_PATH}"
```

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

Then fire **AskUserQuestion**:
- header: "Implementation Plan"
- question: "Review the implementation plan above. Approve to begin execution."
- options:
  - Approve — begin stage execution
  - Request changes — describe what to change (planner will revise)
  - Cancel — stop execution

**If Approve:** proceed to Phase 1.5.

**If Request changes:** collect the change description from the user's response,
then re-invoke the planner with the change request appended to the original
`ANALYSIS` block:

```text
REQUEST: {TASK}
TASK_DIR: {TASK_DIR}
PROJECT_ROOT: {PROJECT_ROOT}
REQUIREMENTS: {REQUIREMENTS}
ANALYSIS: {ANALYSIS block from Phase 1b}

CHANGE REQUEST: {user's change description}

Re-plan the pipeline based on the change request above.
Update {TASK_DIR}/pipeline.json and {TASK_DIR}/handoff.md accordingly.
```

After the planner returns, return to Phase 1d (re-display the updated plan and
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

### Phase 2: Execute stages

Execute the `stages` from `pipeline.json` sequentially.
Skip stages already included in `completed_stages`.

**Devops skip rule**: When iterating stages, if the stage agent is `devops`
(or a stage list that contains `devops`), **do not spawn it here**. Skip it
and let Phase 2.5 handle the devops stage exclusively. This ensures the
approval gate in Phase 2.5 is always reached before devops runs.

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

#### Stage Retry Rule

Every stage invocation (single or parallel) is wrapped in a retry loop.
Retry limits follow the quality-loop rule (`QUALITY_RULE_PATH`):

- **Validation failure** (STATUS returned but criteria not met): up to **3 retries**.
- **Crash** (no STATUS line returned at all): up to **5 retries**.

**Crash detection:** Any agent invocation that returns without a `STATUS:` line
in its response is treated as a crash — not a clean BLOCKED state.

Retry logic per agent:

```
crash_attempts = 0
while crash_attempts <= 5:
    invoke agent
    if response contains "STATUS: completed":
        break  # success
    elif response contains "STATUS: plan_ready":
        break  # agent submitted a plan — Phase 2.5 will handle approval
    elif response contains "STATUS: BLOCKED":
        halt pipeline — write blocker to result.md and return STATUS: blocked
    else:  # no STATUS line — treat as crash
        crash_attempts += 1
        if crash_attempts > 5:
            write crash details to {TASK_DIR}/result.md
            return STATUS: blocked (reason: agent crashed after 5 attempts)
        re-invoke agent (pass TASK_DIR/HANDOFF_PATH/QUALITY_RULE_PATH only — no inline content)
```

Do not silently swallow a crash. After 5 crash failures on the same agent, report BLOCKED
with the agent name and stage index.

#### Custom Agent Dispatch

Before spawning any stage agent, determine whether it is a builtin or custom agent:

BUILTIN_AGENTS = [planner, designer, frontend, backend, devops, resolver, reviewer, task-runner]

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

After the stage agent returns and its result is recorded:

```
[crew] {TASK_ID} | STAGE_DONE | {agent_name} — {APPROVED|NEEDS_CHANGES|N/A}
```

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | STAGE_DONE | {agent_name} — {APPROVED|NEEDS_CHANGES|N/A}" >> "${TASK_DIR}/progress.log"
```

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

**After the stage loop completes (all non-devops stages done), proceed to Phase 2.5 — do NOT skip to Phase 3.** Phase 2.5 is always entered after Phase 2, whether or not any stage returned `STATUS: plan_ready`.

---

### Phase 2.5: Stage Action Gate

The task-runner owns all approval decisions for its pipeline. Stage agents
(devops, reviewer, etc.) MUST NOT issue their own AskUserQuestion for deploy,
merge, push, or destructive operations. Instead they write a PLAN block and wait.

**This phase runs unconditionally after Phase 2 completes.** Do not treat it as conditional on receiving a PLAN: block — it always runs. Within this phase:
- **Step 2** (collect PLAN blocks) runs only when at least one stage returned `STATUS: plan_ready`.
- **Step 3** (devops approval gate) always runs when `EXECUTION_MODE == single`, regardless of whether any stage returned a PLAN: block.

#### Step 1 — Always display the implementation summary

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Implementation Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Branch: {BRANCH}

Commits ready for review:
  {git -C PROJECT_ROOT log --oneline HEAD ^main, up to 10 lines}

Note: No remote push has occurred yet.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Collect the commit log:

```bash
git -C "${PROJECT_ROOT}" log --oneline HEAD ^main 2>/dev/null | head -10
```

#### Step 2 — Collect PLAN blocks from stage agents

When a stage agent returns a `PLAN:` block (instead of executing), the task-runner:

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
   `{TASK_DIR}/context/approval.md` and polls until the orchestrator writes
   `APPROVED` or `CANCELLED` (up to 60s, 5s interval):

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

4. If `EXECUTION_MODE == single`: the task-runner issues the AskUserQuestion
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

**If a devops stage is present:** use **AskUserQuestion** to request approval
before executing the devops stage. Do not run the devops stage without approval.
This is the single consolidated approval gate for this pipeline — do not delegate
it to the devops agent.

Question:
- header: "Deploy"
- question: "Implementation is complete. Review the action plan above. Approve to run the devops stage (CI/CD + git push), or cancel to skip deployment and keep commits local."
- options:
  - Approve — run devops stage now
  - Cancel — skip devops, keep commits local

If **Approve**:
  - Write `APPROVED` to `{TASK_DIR}/context/approval.md`
  - Spawn the devops stage agent now using the standard agent prompt format.
  - After the devops agent returns, check its `STATUS` field:
    - `STATUS: completed` → devops stage succeeded. Proceed to Phase 3.
    - `STATUS: plan_ready` → the devops agent submitted a secondary plan
      (e.g. it needs further confirmation for a specific destructive sub-step).
      Collect its PLAN block, write it to `{TASK_DIR}/context/action-plan.md`
      (appending under a new `## Sub-plan` section), and repeat the
      AskUserQuestion loop (Step 3) for the sub-plan before continuing.
    - `STATUS: BLOCKED` → write the blocker to `{TASK_DIR}/result.md` and
      return `STATUS: blocked` to the orchestrator.
    - No STATUS line → treat as a crash; apply the Stage Retry Rule (up to 5
      crash attempts). After 5 failures, write BLOCKED to result.md and stop.

If **Cancel**:
  - Write `CANCELLED` to `{TASK_DIR}/context/approval.md`
  - Mark the devops stage as skipped (do not update `completed_stages` for it).
  - Print the branch name so the user can push manually later.
  - Proceed directly to Phase 3 without running the devops stage.

---

### Phase 3: Completion Handling

#### 1. Collect git log

```bash
git -C "${PROJECT_ROOT}" log --oneline -5
```

#### 2. Save concise result to `{TASK_DIR}/result.md`

(Do not re-quote contents)

All fields below are required. The orchestrator reads these fields to build
the Step 7 Run Summary — missing fields will cause the summary to be incomplete
or skipped.

Collect the list of changed files and write a one-line description of what changed
for each:

```bash
git -C "${PROJECT_ROOT}" diff --name-only main...HEAD
```

For each changed file, describe the change semantically (not just a filename):
- Newly created file → `(did not exist) → {brief description of purpose}`
- Deleted file → `{brief description} → (removed)`
- Modified file → describe the key behavioral or structural change

```markdown
# {TASK}

DESCRIPTION: {TASK}
BRANCH: {BRANCH}
STATUS: completed
COMMITS: {commit count}
LOG:
{git log --oneline -5 output}

CHANGES:
  - {file path}: {one-line description of what changed}
  - {file path}: {one-line description of what changed}
```

After writing result.md, collect the commit count and emit:

```
[crew] {TASK_ID} | COMPLETED | branch={BRANCH} commits={n}
```

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%S) | COMPLETED | branch={BRANCH} commits={n}" >> "${TASK_DIR}/progress.log"
```

The completion event must also be mirrored to stderr per the stderr-mirror rule
in Phase 0 (use `log_progress "COMPLETED" "branch=${BRANCH} commits=${n}"`).

#### 2b. Close out the host task (capability-gated)

If `HAS_TASK_TOOLS == 1` from Phase 0 and `${TASK_DIR}/host-task-id.txt` exists,
mark the host-side task complete:

```text
HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt")
TaskUpdate(taskId=HOST_TASK_ID, status="completed")
```

For a `STATUS: blocked` exit, call `TaskUpdate(taskId=HOST_TASK_ID,
status="in_progress")` instead and let the operator decide whether to close it.
For a `STATUS: CANCELLED` exit (plan-approval gate cancel), call
`TaskUpdate(taskId=HOST_TASK_ID, status="completed")` so the host task list does
not accumulate stale tasks.

If `HAS_TASK_TOOLS == 0` or the file is absent: skip this step entirely.

#### 3. Clear active task marker

Only clear the active marker when running in `single` mode. In `parallel` mode,
the crew orchestrator is responsible for clearing it after all task-runners finish.

Use the `AGENT_CREW_HOME` variable resolved in Phase 0 — do not re-derive it:

```bash
if [ "${EXECUTION_MODE}" != "parallel" ]; then
  PROJECT_NAME=$(basename "${PROJECT_ROOT}")
  rm -f "${AGENT_CREW_HOME}/state/${PROJECT_NAME}/tasks/active"
fi
```

#### 4. Remove isolated worktree when applicable

```bash
if [ "${EXECUTION_MODE}" = "parallel" ] && [ "${PROJECT_ROOT}" != "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" ]; then
  git worktree remove "${PROJECT_ROOT}" --force 2>/dev/null || true
fi
```

#### 5. Final return value (to parent crew orchestrator)

```text
TASK_ID: {TASK_ID}
BRANCH: {BRANCH}
STATUS: completed
COMMITS: {N} commits
```

Return only this.
Do not include file contents, code, or long explanations.

---

## Absolute Rules

- All file operations must be performed relative to `{PROJECT_ROOT}`
- Never inline file contents in sub-agent prompts — pass only paths
- Never complete without writing `{TASK_DIR}/result.md`
- Final return value must remain within 5 lines and concise
- **Never push to remote** — `git push` is strictly forbidden. Local commits only.
  The task-runner commits exclusively to its own feature branch (`{BRANCH}`).
  The crew orchestrator handles all remote operations: for parallel runs (N > 1),
  it merges all task feature branches into `main` in Step 9 of `run.md` before
  pushing; for single-task runs (N == 1), it pushes the feature branch directly.
  Both paths require explicit user approval (Step 11 of `run.md`) before any push.
- **Never stop mid-pipeline** — if a sub-agent returns without a `STATUS:` line,
  treat it as a crash and apply the Stage Retry Rule (up to 5 crash attempts). Only
  after 5 consecutive crash failures may the task-runner halt with `STATUS: blocked`.
  A task-runner that silently stops without writing `result.md` violates this rule.
