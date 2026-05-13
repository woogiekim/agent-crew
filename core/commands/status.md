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
CAPABILITIES_PATH="${AGENT_CREW_HOME}/state/${PROJECT_NAME}/capabilities.json"
```

### 1b. Probe host capabilities (Layer 1 progressive adoption)

Read the host capabilities file written by the active adapter's `setup.sh`. Per
`core/rules/host-capabilities.md`, a missing file or parse error means every
flag is treated as `false` (legacy behavior).

```bash
HAS_TASK_TOOLS=$(python3 -c "
import json
try:
    print('1' if json.load(open('${CAPABILITIES_PATH}')).get('task_tools') else '0')
except Exception:
    print('0')
" 2>/dev/null)
```

If `HAS_TASK_TOOLS == 1` AND the host exposes a callable `TaskList` tool, the
preferred source for "Recent events" is `TaskList` output filtered to the
crew-managed entry. Use this preference path:

```text
if HAS_TASK_TOOLS == 1:
    call TaskList()
    filter to tasks whose metadata.task_id matches the current ACTIVE_TASK
      (or whose subject starts with "crew:run —")
    render the matching task as "Recent events (from host task list)"
else:
    fall back to tailing progress.log (Step 5 below)
```

If the TaskList call is not available at runtime (tool not loaded in this
session, host unable to respond), silently fall back to the progress.log tail.
The capability flag opts in; the actual TaskList call must still be guarded by a
runtime availability check.

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

# Branch: read from result.md BRANCH field or derive from pipeline.json and ACTIVE_TASK
BRANCH=$(grep "^BRANCH:" "${RESULT}" 2>/dev/null | head -1 | sed 's/^BRANCH: //' || true)
if [ -z "${BRANCH}" ]; then
  BRANCH=$(python3 - "${PIPELINE}" "${ACTIVE_TASK}" <<'PYEOF'
import json
import re
import sys

pipeline, task_id = sys.argv[1], sys.argv[2]

try:
    task = json.load(open(pipeline)).get("task", "")
except Exception:
    task = ""

task_lc = task.lower()
words = set(re.findall(r"[a-z0-9]+", task_lc))
prefix_rules = [
    ("fix", {"fix", "fixes", "fixed", "bug", "bugs", "repair", "repairs", "broken", "error", "errors", "failing", "failure", "failures", "regression", "regressions"}, ()),
    ("docs", {"doc", "docs", "documentation", "readme", "guide", "guides", "instruction", "instructions", "manual"}, ()),
    ("refactor", {"refactor", "refactors", "refactoring", "restructure", "cleanup", "simplify", "reorganize"}, ("clean up",)),
    ("test", {"test", "tests", "testing", "spec", "specs", "coverage", "qa"}, ()),
    ("chore", {"chore", "chores", "build", "dependency", "dependencies", "deps", "config", "configuration", "setup", "tooling", "maintenance"}, ("continuous integration",)),
]
prefix = "feature"
for candidate, tokens, phrases in prefix_rules:
    if words & tokens or any(phrase in task_lc for phrase in phrases):
        prefix = candidate
        break

words = re.findall(r"[a-z0-9]+", task_lc)
stopwords = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "so", "that", "the",
    "to", "with", "instead", "only", "than", "rather"
}
slug = "-".join(word for word in words if word not in stopwords)[:48].strip("-") or "task"
print(f"{prefix}/{slug}-{task_id}")
PYEOF
)
fi
```

### 5. Read recent progress events (fallback)

This step is the legacy fallback used when `HAS_TASK_TOOLS == 0`, when the host
TaskList call is not available, or when the capability gate was not opted into.
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

Source-selection summary:

| `task_tools` flag | TaskList callable | Source used |
|---|---|---|
| `true` | yes | host TaskList output (Step 1b) |
| `true` | no | progress.log tail (this step) |
| `false` or missing | — | progress.log tail (this step) |

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
- When the host adapter has advertised `task_tools: true` in
  `~/.agent-crew/state/{project}/capabilities.json`, `crew:status` prefers the
  host's `TaskList` output for "Recent events" because hosts like Claude Code
  stream that surface live. `progress.log` is still written, so the fallback is
  always safe. See `core/rules/host-capabilities.md` for the schema and the
  absence contract.
