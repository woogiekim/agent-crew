# crew:status — Pipeline Snapshot

Print a real-time snapshot of the most recently active task's pipeline state.

```text
crew:status
```

No arguments required. The command automatically targets the most recent task
under the active project's state directory.

---

## Execution Steps

### 1. Resolve state paths

```bash
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
PROJECT_NAME=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")
STATE_DIR="${AGENT_CREW_HOME}/state/${PROJECT_NAME}/tasks"
```

### 2. Find the most recent task

```bash
ACTIVE_TASK=$(ls -t "${STATE_DIR}" | head -1)
TASK_DIR="${STATE_DIR}/${ACTIVE_TASK}"
PIPELINE="${TASK_DIR}/pipeline.json"
RESULT="${TASK_DIR}/result.md"
```

If `STATE_DIR` does not exist or is empty, print:

```
No tasks found. Run crew:setup or crew:run first.
```

### 3. Determine overall status

```bash
# Check result.md for a completed status
if grep -q "STATUS: completed" "${RESULT}" 2>/dev/null; then
  OVERALL_STATUS="completed"
elif grep -q "STATUS: blocked" "${RESULT}" 2>/dev/null || grep -q "STATUS: BLOCKED" "${RESULT}" 2>/dev/null; then
  OVERALL_STATUS="blocked"
else
  OVERALL_STATUS="in-progress"
fi
```

### 4. Extract task metadata

```bash
# Task description: prefer pipeline.json "task" field, fall back to result.md DESCRIPTION
TASK_DESC=$(python3 -c "
import json, sys
try:
    p = json.load(open('${PIPELINE}'))
    print(p.get('task', '(unknown)'))
except:
    print('(unknown)')
" 2>/dev/null)

# Branch: read from result.md BRANCH field or derive from ACTIVE_TASK
BRANCH=$(grep "^BRANCH:" "${RESULT}" 2>/dev/null | head -1 | sed 's/^BRANCH: //' || echo "feature/task-${ACTIVE_TASK}")
```

### 5. Read recent progress events

Read the last 20 lines from `{TASK_DIR}/progress.log` (if it exists) to show
real-time progress events that may not yet be reflected in `pipeline.json`:

```bash
PROGRESS_LOG="${TASK_DIR}/progress.log"
if [ -f "${PROGRESS_LOG}" ]; then
  RECENT_PROGRESS=$(tail -20 "${PROGRESS_LOG}" 2>/dev/null)
else
  RECENT_PROGRESS=""
fi
```

This log is written by the task-runner at every phase and stage boundary, so it
reflects the current live state even while a sub-agent is still running.

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
Task   : {TASK_DESC}
Branch : {BRANCH}
Status : {in-progress | completed | blocked}

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

- `crew:status` is read-only. It never modifies any state file.
- The command always targets the **most recently modified** task directory
  (using `ls -t … | head -1`). To inspect an older task, pass the TASK_ID
  directly as an argument (future extension — not required for v1).
- Stage markers reflect `completed_stages` from `pipeline.json`, not live
  agent output. For live event streaming, the "Recent events" section reads
  `{TASK_DIR}/progress.log` (tail -20), which is written by the task-runner
  at every phase and stage boundary. This log is the most up-to-date source
  of pipeline state even while a sub-agent is still running.
