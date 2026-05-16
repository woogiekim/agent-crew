# crew:status — Pipeline Snapshot

Print a real-time snapshot of the active pipeline state.

```text
crew:status           # snapshot — show current state and exit
crew:status --collect # wait for background session to finish, then finalize
```

When a background session is running (`session.json` exists with `status:
running`), `crew:status` displays a live session table. Without `--collect`,
it exits immediately after the snapshot. With `--collect`, it waits for all
tasks to finish and then runs the equivalent of Steps 7–11 from `crew:run`
(Run Summary, merge, Implementation Summary, Deploy approval).

When no background session exists (or `session.json` is absent / completed),
`crew:status` falls back to the existing single-task snapshot behavior.

---

## Execution Steps

### 1. Resolve state paths

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}"
TASKS_DIR="${STATE_DIR}/tasks"
SESSION_FILE="${STATE_DIR}/session.json"
CAPABILITIES_PATH="${STATE_DIR}/capabilities.json"
```

### 1b. Probe host capabilities (Layers 1–2 progressive adoption)

Read the host capabilities file written by the active adapter's `setup.sh`. Per
`core/rules/host-capabilities.md`, a missing file or parse error means every
flag is treated as `false` (legacy behavior).

```bash
# Single Python process reads capabilities.json once and emits all three flags,
# eliminating extra python3 process startups.
read -r HAS_TASK_TOOLS HAS_MONITOR_TOOL HAS_AGENT_BACKGROUND < <(python3 -c "
import json
try:
    c = json.load(open('${CAPABILITIES_PATH}'))
    print(
        '1' if c.get('task_tools') else '0',
        '1' if c.get('monitor_tool') else '0',
        '1' if c.get('agent_background') else '0',
    )
except Exception:
    print('0 0 0')
" 2>/dev/null)
```

Two preferences are derived from the flags:

1. **`HAS_TASK_TOOLS == 1` AND `TaskList` callable** — preferred source for the
   pipeline stage list and the current parent-task state. Filter `TaskList()`
   output to entries with `metadata.task_id == ACTIVE_TASK` (or
   `subject` starting with `"crew:run —"`) and render the matching task.
2. **`HAS_MONITOR_TOOL == 1` AND `TaskOutput` callable** — preferred source for
   the "Recent events" stream (P5). Instead of tailing
   `{TASK_DIR}/progress.log`, read `TaskOutput(taskId=<parent host task>)` and
   render the last 20 lines that start with `[crew]`. This eliminates the
   buffering caveat — supervisors mirror every progress event to stderr in
   real time, and the host surfaces stderr through `TaskOutput` without the
   sub-agent having to flush.

Both preferences are independent: a host may advertise `task_tools=true` but
`monitor_tool=false`, in which case `crew:status` uses `TaskList` for stage
state but `tail -20 progress.log` for the event stream. Source-selection
matrix:

| `task_tools` | `monitor_tool` | Stage state source | Event stream source |
|---|---|---|---|
| true | true | `TaskList` (Step 6 fallback otherwise) | `TaskOutput` (Step 5 below) |
| true | false | `TaskList` (Step 6 fallback otherwise) | `tail -20 progress.log` |
| false | * | `pipeline.json` (Step 6) | `tail -20 progress.log` |

If either tool call is not available at runtime (tool not loaded in this
session, host unable to respond), silently fall back to the file-based path.
The capability flag opts in; the actual `TaskList` / `TaskOutput` call must
still be guarded by a runtime availability check.

`progress.log` is always written by the supervisor regardless of which source
is preferred — it remains the single source of truth per
`core/rules/host-capabilities.md`.

### 1c. Detect session mode

Check whether a live background session exists:

```bash
SESSION_MODE=$(python3 -c "
import json, os, time
try:
    path = '${SESSION_FILE}'
    s = json.load(open(path))
    age = time.time() - os.path.getmtime(path)
    if s.get('status') == 'running' and age <= 86400:
        print('live')
    elif s.get('status') in ('running', 'completed'):
        print('session')
    else:
        print('none')
except Exception:
    print('none')
" 2>/dev/null)
```

- `live` — `session.json` exists, `status == running`, and the file is less
  than 24 hours old. Use **Session-Aware Mode** (Steps 2S–7S below).
- `session` — `session.json` exists but the session has already completed or
  the file is older than 24h. Display as completed session (Steps 2S–3S only,
  no --collect action).
- `none` — no session file. Use **Single-Task Mode** (Steps 2–7 below).

---

## Session-Aware Mode (Steps 2S–7S)

> These steps run when `SESSION_MODE == "live"` or `SESSION_MODE == "session"`.
> Skip these steps and proceed to Step 2 (single-task mode) when
> `SESSION_MODE == "none"`.

### 2S. Read session state

```bash
python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
print('SESSION_ID:', s.get('session_id', '?'))
print('STATUS:', s.get('status', '?'))
for t in s.get('tasks', []):
    print('TASK', t['task_id'], t['branch'], t['status'],
          '(injected)' if t.get('injected') else '', sep='|')
" 2>/dev/null
```

Extract all task entries: `task_id`, `task_dir`, `branch`, `status`, `injected`.

### 3S. Show live session table

For each task, determine live status:

```bash
# For each task entry:
TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
PROGRESS_LOG="${TASK_DIR}/progress.log"

# Overall task status:
# 1. Check result.md
if grep -q "STATUS: completed" "${TASK_DIR}/result.md" 2>/dev/null; then
  TASK_STATUS="completed"
elif grep -q "STATUS: blocked\|STATUS: BLOCKED" "${TASK_DIR}/result.md" 2>/dev/null; then
  TASK_STATUS="blocked"
else
  TASK_STATUS="running"
fi

# 2. Last progress event
LAST_EVENT=$(tail -1 "${PROGRESS_LOG}" 2>/dev/null | sed 's/^[0-9T:-]* | //' || echo "(no events yet)")

# 3. Current stage (from pipeline.json completed_stages)
CURRENT_STAGE=$(python3 -c "
import json
try:
    p = json.load(open('${TASK_DIR}/pipeline.json'))
    stages = p.get('stages', [])
    done = p.get('completed_stages', 0)
    if done < len(stages):
        s = stages[done]
        agent = s if isinstance(s, str) else '/'.join(s)
        print(f'{done+1}/{len(stages)} — {agent}')
    else:
        print('done')
except Exception:
    print('(planning...)')
" 2>/dev/null)
```

When `HAS_TASK_TOOLS == 1` and `${TASK_DIR}/host-task-id.txt` exists, also
read the host task status for the most precise live state:

```text
HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt" 2>/dev/null)
if [ -n "$HOST_TASK_ID" ]:
    HOST_STATUS=$(TaskGet(taskId=$HOST_TASK_ID).status)
    # Map to display: in_progress → running, completed → completed, etc.
```

Display the session table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Background Session: {SESSION_ID}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Session status: {running | completed}

  #  Task ID              Branch                         Status     Stage
  ─  ────────────────────  ─────────────────────────────  ─────────  ──────────────────
  1  {TASK_ID_1}           {BRANCH_1}                     running    2/3 — backend
  2  {TASK_ID_2} (inj)     {BRANCH_2}                     completed  done
  3  {TASK_ID_3}           {BRANCH_3}                     running    (planning...)

Last event per task:
  {TASK_ID_1}: {LAST_EVENT_1}
  {TASK_ID_2}: COMPLETED | branch={BRANCH_2} commits=3
  {TASK_ID_3}: {LAST_EVENT_3}

  "(inj)" marks tasks injected after session start.

To wait for all tasks and finalize: crew:status --collect
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**If `SESSION_MODE == "session"` (completed session):** append a note:

```
Session completed. To see full results, read result.md for each task above.
```

**If `--collect` was NOT passed** (snapshot mode): **STOP here**. Print the
table above and exit. Do not wait or enter any loop.

### 4S. Collect mode (--collect only)

> Only entered when `--collect` was passed AND `SESSION_MODE == "live"`.

Wait for all running tasks to reach a terminal state. Poll every 5 seconds
(use TaskGet wake-on-change when `HAS_TASK_TOOLS == 1` to reduce latency):

```bash
PRE_RUN_HEAD=$(python3 -c "
import json
try:
    s = json.load(open('${SESSION_FILE}'))
    print(s.get('pre_run_head', ''))
except Exception:
    print('')
" 2>/dev/null)

while true:
    # Re-read session.json to detect newly injected tasks
    REMAINING=$(python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
print(sum(1 for t in s['tasks'] if t['status'] not in ('completed', 'blocked')))
" 2>/dev/null)

    # For each still-running task, check result.md and update session.json
    python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
changed = False
for t in s['tasks']:
    if t['status'] not in ('completed', 'blocked'):
        result_path = t['task_dir'] + '/result.md'
        try:
            content = open(result_path).read()
            if 'STATUS: completed' in content:
                t['status'] = 'completed'; changed = True
            elif 'STATUS: blocked' in content or 'STATUS: BLOCKED' in content:
                t['status'] = 'blocked'; changed = True
        except Exception:
            pass
if changed:
    json.dump(s, open('${SESSION_FILE}', 'w'), ensure_ascii=False, indent=2)
" 2>/dev/null

    if [ "${REMAINING}" = "0" ]; then
        break  # All tasks have reached terminal state
    fi

    # When HAS_TASK_TOOLS == 1: prefer TaskGet wake-on-change over sleep
    # (poll each task's host task id; sleep is the fallback guard)
    sleep 5
done
```

After all tasks complete, mark `session.json` as done:

```bash
python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
s['status'] = 'completed'
json.dump(s, open('${SESSION_FILE}', 'w'), ensure_ascii=False, indent=2)
" 2>/dev/null
```

Apply the same crash-retry rule as `crew:run` Step 7: if a task's `result.md`
is missing or lacks a STATUS field after the poll loop exits, treat it as a
crash and re-invoke the supervisor for that task (up to 3 retries, passing
the same `TASK_DIR` so the supervisor resumes from `pipeline.json`).

### 5S. Run Summary (--collect only)

> This is the equivalent of `crew:run` Step 7's Run Summary. Read
> `result.md` for each task and display the full diff / commit output.

Read all task results from `session.json`:

```bash
python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
for t in s['tasks']:
    print(t['task_id'], t['task_dir'], t['branch'], t['status'],
          '1' if t.get('injected') else '0', sep='|')
" 2>/dev/null
```

For each task, collect the diff relative to `pre_run_head`:

```bash
TASK_PROJECT_ROOT="${TASK_DIR}/../../.."  # worktrees are under PROJECT_ROOT/.crew-worktrees/
# Or read PROJECT_ROOT from result.md if recorded

git -C "${PROJECT_ROOT_FOR_TASK}" diff --stat ${PRE_RUN_HEAD}..HEAD
DIFF_OUTPUT=$(git -C "${PROJECT_ROOT_FOR_TASK}" diff ${PRE_RUN_HEAD}..HEAD 2>/dev/null)
DIFF_LINES=$(echo "$DIFF_OUTPUT" | wc -l | tr -d ' ')
if [ "$DIFF_LINES" -le 200 ]; then
  echo "$DIFF_OUTPUT"
else
  echo "$DIFF_OUTPUT" | head -200
  echo "… $((DIFF_LINES - 200)) more lines. Run: git diff ${PRE_RUN_HEAD}..HEAD"
fi
```

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Run Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task 1: {description}  [injected]    ← "(injected)" tag when task.injected == true
  Status : completed | blocked
  Branch : {branch}

  Changes:
    {git diff --stat {PRE_RUN_HEAD}..HEAD output}

  Diff:
    {git diff {PRE_RUN_HEAD}..HEAD | head -200 output}
    (If over 200 lines: "… {N} more lines. Run: git diff {PRE_RUN_HEAD}..HEAD")

  Commits ({N}):
    {git log --oneline, up to 5 lines}

Task 2: {description}
  ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If any task has `STATUS: blocked`, report the blocker. Do not proceed to merge.

### 6S. Merge Branches (--collect only, N > 1)

> This is the equivalent of `crew:run` Step 8.

Merge all completed task branches into `main` locally:

```bash
SESSION_FILE="${STATE_DIR}/session.json"
ALL_BRANCHES=$(python3 -c "
import json
s = json.load(open('${SESSION_FILE}'))
for t in s['tasks']:
    if t['status'] == 'completed':
        print(t['branch'])
" 2>/dev/null)

git checkout main
for BRANCH in ${ALL_BRANCHES}; do
  git merge --no-ff "${BRANCH}" -m "merge: ${BRANCH} into main"
done
```

If a merge conflict occurs, invoke the conflict resolver before continuing:

```text
crew:run "resolve merge conflicts"
```

After all merges succeed:

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Implementation Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Merged branches into main (local):
  - {BRANCH_1}  ({N} commits)
  - {BRANCH_2}  ({N} commits)

Commits ready for push (origin/main..HEAD):
  {git log --oneline origin/main..HEAD, up to 10 lines}

Note: No remote push has occurred yet.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

> **Stop here by default.** Do not volunteer deployment. If the user wants to
> deploy or push, they will request it explicitly.

### 7S. Deploy Approval (--collect only, devops stage present)

> This is the equivalent of `crew:run` Steps 10–11. Only runs when at least
> one pipeline in the session included a `devops` stage.

Check if any pipeline had a devops stage:

```bash
HAS_DEVOPS=$(python3 -c "
import json, os
import json as j
s = j.load(open('${SESSION_FILE}'))
for t in s['tasks']:
    pp = os.path.join(t['task_dir'], 'pipeline.json')
    try:
        p = j.load(open(pp))
        if any('devops' in stage for stage in p.get('stages', [])):
            print('yes'); exit()
    except Exception:
        pass
print('no')
" 2>/dev/null)
```

If `HAS_DEVOPS == "no"`: skip this step entirely.

If `HAS_DEVOPS == "yes"`: display the Deployment Plan and emit a **structured
user-choice intent** (per `core/rules/capabilities/interactive-question.md`):

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Deployment Plan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Action: push main to origin (all task branches merged)

Commits to be published (origin/main..HEAD):
  {git log --oneline origin/main..HEAD}

Target remote: origin
Risk notes:
  - {any merge conflicts detected?}
  - {any blocked tasks?}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

```text
# Structured user-choice intent (host-bound — see
# core/rules/capabilities/interactive-question.md):
ask_question:
  header: "Deploy"
  question: "Review the deployment plan above. Approve to push main to remote, or cancel to hold."
  options:
    - label: "Approve"
      description: "Push main to origin now"
    - label: "Cancel"
      description: "Hold, do not push (branches remain local)"
```

If **Approve**:

```bash
git push origin main
```

Report: `Deployment complete. Pushed: main`

If **Cancel**: Print the branch name(s) so the user can push manually later.

---

## Single-Task Mode (Steps 2–7)

> These steps run when `SESSION_MODE == "none"` (no live or recent session).
> They are the original `crew:status` behavior, unchanged.

### 2. Find the most recent task

```bash
ACTIVE_TASK=$(ls -t "${TASKS_DIR}" | head -1)
TASK_DIR="${TASKS_DIR}/${ACTIVE_TASK}"
PIPELINE="${TASK_DIR}/pipeline.json"
RESULT="${TASK_DIR}/result.md"
REGISTER="${TASK_DIR}/register.json"
```

If `TASKS_DIR` does not exist or is empty, print:

```
No tasks found. Run crew:setup or crew:run first.
```

### 2.5. Prefer register.json for state (Phase F4)

When `register.json` is present, read `current_phase`,
`approval_status`, and `verification_status` directly — no need to
parse `pipeline.json` and `progress.log` to infer state. Pre-F4 task
directories without `register.json` fall through to the existing
`result.md`-grep logic in Step 3.

```bash
HAS_REGISTER=0
REG_CURRENT_PHASE=""
REG_APPROVAL_STATUS=""
REG_VERIFY_STATUS=""
if [ -f "${REGISTER}" ]; then
  HAS_REGISTER=1
  read -r REG_CURRENT_PHASE REG_APPROVAL_STATUS REG_VERIFY_STATUS \
    < <(python3 -c "
import json
try:
    r = json.load(open('${REGISTER}'))
    print(r.get('current_phase', '?'),
          r.get('approval_status', '?'),
          r.get('verification_status', '?'))
except Exception:
    print('? ? ?')
" 2>/dev/null)
fi
```

### 3. Determine overall status

```bash
if [ "${HAS_REGISTER}" = "1" ]; then
  case "${REG_CURRENT_PHASE}" in
    completed)  OVERALL_STATUS="completed" ;;
    blocked)    OVERALL_STATUS="blocked" ;;
    *)          OVERALL_STATUS="in-progress" ;;
  esac
else
  # Pre-F4 fallback: grep result.md for STATUS.
  if grep -q "STATUS: completed" "${RESULT}" 2>/dev/null; then
    OVERALL_STATUS="completed"
  elif grep -q "STATUS: blocked" "${RESULT}" 2>/dev/null || grep -q "STATUS: BLOCKED" "${RESULT}" 2>/dev/null; then
    OVERALL_STATUS="blocked"
  else
    OVERALL_STATUS="in-progress"
  fi
fi
```

### 4. Extract task metadata

```bash
# BRANCH fast path: prefer result.md BRANCH field (simple grep — no Python needed).
BRANCH=$(grep "^BRANCH:" "${RESULT}" 2>/dev/null | head -1 | sed 's/^BRANCH: //' || true)

# Single Python process reads pipeline.json once and emits TASK_DESC and
# (when BRANCH is still empty) the derived branch slug.
# Output format: two lines — line 1 is task description, line 2 is branch slug.
_PY_OUT=$(python3 - "${PIPELINE}" "${ACTIVE_TASK}" <<'PYEOF'
import json, re, sys

pipeline, task_id = sys.argv[1], sys.argv[2]
try:
    task = json.load(open(pipeline)).get("task", "")
except Exception:
    task = ""

# Line 1: task description
print(task or "(unknown)")

# Line 2: derived branch slug (used only when result.md BRANCH field is absent)
task_lc = task.lower()
words_set = set(re.findall(r"[a-z0-9]+", task_lc))
prefix_rules = [
    ("fix",      {"fix","fixes","fixed","bug","bugs","repair","repairs","broken","error","errors","failing","failure","failures","regression","regressions"}, ()),
    ("docs",     {"doc","docs","documentation","readme","guide","guides","instruction","instructions","manual"}, ()),
    ("refactor", {"refactor","refactors","refactoring","restructure","cleanup","simplify","reorganize"}, ("clean up",)),
    ("test",     {"test","tests","testing","spec","specs","coverage","qa"}, ()),
    ("chore",    {"chore","chores","build","dependency","dependencies","deps","config","configuration","setup","tooling","maintenance"}, ("continuous integration",)),
]
prefix = "feature"
for candidate, tokens, phrases in prefix_rules:
    if words_set & tokens or any(p in task_lc for p in phrases):
        prefix = candidate
        break

stopwords = {"a","an","and","are","as","at","be","by","for","from","in","into","is","it","of","on","or","so","that","the","to","with","instead","only","than","rather"}
slug = "-".join(w for w in re.findall(r"[a-z0-9]+", task_lc) if w not in stopwords)[:48].strip("-") or "task"
print(f"{prefix}/{slug}-{task_id}")
PYEOF
)
TASK_DESC=$(printf '%s' "${_PY_OUT}" | head -1)
if [ -z "${BRANCH}" ]; then
  BRANCH=$(printf '%s' "${_PY_OUT}" | tail -1)
fi
unset _PY_OUT
```

### 5. Read recent progress events

Resolve `RECENT_PROGRESS` using the preference matrix from Step 1b. The
file-based fallback path prefers the structured JSONL buffer
(`progress.buffer.jsonl`, Phase F5) when present and falls back to
`tail -20 progress.log` otherwise:

```text
if HAS_MONITOR_TOOL == 1 AND TaskOutput is callable:
    # P5 — preferred source. The supervisor mirrors every progress event to
    # stderr (host-agnostic), which Claude Code captures as TaskOutput. This
    # avoids the buffering caveat described in core/commands/run.md.
    HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt" 2>/dev/null)
    if [ -n "$HOST_TASK_ID" ]:
        RECENT_PROGRESS=$(TaskOutput(taskId=$HOST_TASK_ID)
            | grep '^\[crew\]'
            | tail -20)
    else:
        # Parent host task id not recorded — fall back to file tail
        RECENT_PROGRESS=$(_render_local_recent_events "${TASK_DIR}")
else:
    # File-based fallback path.
    RECENT_PROGRESS=$(_render_local_recent_events "${TASK_DIR}")
```

The `_render_local_recent_events` helper prefers the structured buffer
when present (Phase F5), falling through to the legacy `progress.log`
tail when only the older artifact exists (pre-F5 task directories):

```bash
_render_local_recent_events() {
  local task_dir="$1"
  local buffer="${task_dir}/progress.buffer.jsonl"
  local legacy="${task_dir}/progress.log"

  if [ -f "${buffer}" ] && [ -s "${buffer}" ]; then
    # Phase F5 — render last 20 JSONL events as a compact table.
    python3 - "${buffer}" <<'PYEOF' 2>/dev/null || tail -20 "${legacy}" 2>/dev/null
import json, sys
from collections import deque
path = sys.argv[1]
tail = deque(maxlen=20)
skipped = 0
with open(path, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            skipped += 1
            continue
        if not all(k in row for k in ("ts", "trace_id", "task_id", "event")):
            skipped += 1
            continue
        tail.append(row)
for row in tail:
    ts      = row.get("ts", "")
    event   = row.get("event", "")
    stage   = row.get("stage", 0)
    agent   = row.get("agent", "") or "-"
    status  = row.get("status", "unknown")
    detail  = row.get("detail", "")
    print(f"  {ts} | {event:<24} | stage={stage} agent={agent:<12} "
          f"status={status:<10} | {detail}")
if skipped:
    print(f"  (skipped {skipped} malformed line(s) in progress.buffer.jsonl)",
          file=sys.stderr)
PYEOF
  elif [ -f "${legacy}" ]; then
    # Pre-F5 task directory — legacy tail
    tail -20 "${legacy}" 2>/dev/null
  fi
  # If neither exists, return empty (caller renders "(no progress log yet)")
}
```

When the `TaskOutput` call fails at runtime (tool not loaded, host returns an
error), silently fall back to tailing `progress.log`. The capability flag opts
in; the actual call must still be guarded by a runtime availability check.

The file is written by the supervisor at every phase and stage boundary, so it
always reflects the current live state even while a sub-agent is still
running. The host-task event stream is the same data path with lower latency.

Source-selection summary (full matrix from Step 1b):

| `task_tools` flag | `monitor_tool` flag | TaskList callable | TaskOutput callable | Stage state | Event stream |
|---|---|---|---|---|---|
| `true` | `true` | yes | yes | host TaskList | host TaskOutput (P5) |
| `true` | `true` | yes | no | host TaskList | progress.log tail |
| `true` | `false` | yes | — | host TaskList | progress.log tail |
| `true` | * | no | — | pipeline.json (Step 6) | progress.log tail |
| `false` or missing | — | — | — | pipeline.json (Step 6) | progress.log tail |

`progress.log` is always written regardless of which source is preferred — it
remains the single source of truth per `core/rules/host-capabilities.md`.

### 6. Build the stage list

Read `pipeline.json` to determine stages, `completed_stages`, and `stage_agent_status`:

```bash
python3 -c "
import json, sys

pipeline_path = '${PIPELINE}'
result_path = '${RESULT}'

try:
    p = json.load(open(pipeline_path))
except Exception as e:
    print('(pipeline.json not found — task may still be in Phase 1)')
    sys.exit(0)

stages = p.get('stages', [])
completed = p.get('completed_stages', 0)
agent_status = p.get('stage_agent_status', {})

# Check if overall result shows completed
import os
overall_done = False
try:
    content = open(result_path).read()
    overall_done = 'STATUS: completed' in content
except:
    pass

lines = []
total = len(stages)
for i, stage in enumerate(stages):
    stage_num = i + 1
    agents = stage if isinstance(stage, list) else [stage]
    agent_label = ', '.join(agents)

    if overall_done or stage_num <= completed:
        marker = '[✓]'
    elif stage_num == completed + 1:
        marker = '[▶]'
    else:
        marker = '[ ]'

    # Append current marker for the active stage
    suffix = '  ← current' if marker == '[▶]' else ''
    lines.append(f'  {marker} {agent_label}{suffix}')

for line in lines:
    print(line)
print()
print(f'Completed: {completed} / {total} stages')
" 2>/dev/null
```

### 7. Print the snapshot

Assemble and print the snapshot in this format. When `RECENT_PROGRESS` is
non-empty, include the "Recent events" section above the pipeline stages list:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Task Status: {ACTIVE_TASK}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task    : {TASK_DESC}
Branch  : {BRANCH}
Status  : {in-progress | completed | blocked}
Phase   : {REG_CURRENT_PHASE}    ← printed only when register.json present
Approval: {REG_APPROVAL_STATUS}  ← printed only when register.json present and approval_status != not_required
Reviewer: {REG_VERIFY_STATUS}    ← printed only when register.json present and verification_status not in (not_started, skipped)

Recent events (from progress.log):
  2026-05-10T14:22:01 | STARTED    | Implement order management API
  2026-05-10T14:22:03 | PHASE      | 1a — Requirement collection
  2026-05-10T14:22:45 | PHASE      | 1b — Analysis
  2026-05-10T14:23:10 | PHASE      | 1c — Planning
  2026-05-10T14:23:11 | PHASE      | 1d — Plan approval
  2026-05-10T14:24:00 | STAGE      | 1/3 — backend

Pipeline stages:
  [✓] requirements
  [✓] analyst
  [✓] planner
  [▶] backend        ← current
  [ ] reviewer

Completed: 3 / 5 stages
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

When `RECENT_PROGRESS` is empty (no log file yet), omit the "Recent events" section:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Task Status: {ACTIVE_TASK}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task   : {TASK_DESC}
Branch : {BRANCH}
Status : {in-progress | completed | blocked}

Pipeline stages:
  [✓] requirements
  [✓] analyst
  [✓] planner
  [▶] backend        ← current
  [ ] reviewer

Completed: 3 / 5 stages
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

When `pipeline.json` does not yet exist (task is in Phase 1 before planning):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Task Status: {ACTIVE_TASK}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Task   : {TASK_DESC or "(pending)"}
Branch : {BRANCH}
Status : in-progress

Recent events (from progress.log):
  {RECENT_PROGRESS lines, or "(no progress log yet)" if empty}

Pipeline stages:
  (pipeline not yet created — still in planning phase)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Notes

- `crew:status` is read-only in snapshot mode. It never modifies any state file.
  The `--collect` flag is the only mode that modifies state (merging branches,
  marking session as completed, writing `approval.md`).
- **Session-aware mode** is the primary mode when a background session (`session.json`
  with `status: running`) is detected. It shows all tasks in the session, not just
  the most recently modified task directory.
- **Single-task mode** (Steps 2–7, original behavior) is the fallback when no active
  session is present. It targets the most recently modified task directory
  (using `ls -t … | head -1`). To inspect an older task, pass the TASK_ID
  directly as an argument (future extension — not required for v1).
- **`crew:status --collect`** is the finalization command for background sessions.
  It waits for all tasks to complete, then runs the equivalent of `crew:run` Steps
  7–11 (Run Summary, branch merge, Implementation Summary, Deploy approval). Use
  this after `crew:run` spawns a background parallel session and returns early.
- Stage markers in single-task mode reflect `completed_stages` from `pipeline.json`,
  not live agent output. For live event streaming, the "Recent events" section reads
  `{TASK_DIR}/progress.log` (tail -20), which is written by the supervisor at every
  phase and stage boundary. This log is the most up-to-date source of pipeline state
  even while a sub-agent is still running. The host-task event stream is the same
  data path with lower latency.
- When the host adapter has advertised `task_tools: true` in
  `~/.agent-crew/state/{project}/capabilities.json`, `crew:status` prefers the
  host's `TaskList` output for the parent-task stage state because hosts like
  Claude Code stream that surface live.
- When the host adapter has advertised `monitor_tool: true`, `crew:status`
  prefers `TaskOutput(taskId)` for the "Recent events" stream (P5). The
  stderr-mirror rule in `core/agents/supervisor.md` ensures every progress
  event is written to stderr (which Claude Code captures as `TaskOutput`),
  eliminating the file-buffering caveat. `progress.log` is still written, so
  the fallback is always safe.
- See `core/rules/host-capabilities.md` for the schema and the absence
  contract; `core/rules/capabilities/monitor-tool.md` for the per-flag
  detail.
