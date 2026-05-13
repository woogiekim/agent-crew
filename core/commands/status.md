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

### 1b. Probe host capabilities (Layers 1–2 progressive adoption)

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

HAS_MONITOR_TOOL=$(python3 -c "
import json
try:
    print('1' if json.load(open('${CAPABILITIES_PATH}')).get('monitor_tool') else '0')
except Exception:
    print('0')
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
   buffering caveat — task-runners mirror every progress event to stderr in
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

`progress.log` is always written by the task-runner regardless of which source
is preferred — it remains the single source of truth per
`core/rules/host-capabilities.md`.

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

### 5. Read recent progress events

Resolve `RECENT_PROGRESS` using the preference matrix from Step 1b:

```text
if HAS_MONITOR_TOOL == 1 AND TaskOutput is callable:
    # P5 — preferred source. The task-runner mirrors every progress event to
    # stderr (host-agnostic), which Claude Code captures as TaskOutput. This
    # avoids the buffering caveat described in core/commands/run.md.
    HOST_TASK_ID=$(cat "${TASK_DIR}/host-task-id.txt" 2>/dev/null)
    if [ -n "$HOST_TASK_ID" ]:
        RECENT_PROGRESS=$(TaskOutput(taskId=$HOST_TASK_ID)
            | grep '^\[crew\]'
            | tail -20)
    else:
        # Parent host task id not recorded — fall back to file tail
        RECENT_PROGRESS=$(tail -20 "${TASK_DIR}/progress.log" 2>/dev/null || echo "")
else:
    # Legacy fallback: tail the canonical progress.log artifact.
    PROGRESS_LOG="${TASK_DIR}/progress.log"
    if [ -f "${PROGRESS_LOG}" ]:
        RECENT_PROGRESS=$(tail -20 "${PROGRESS_LOG}" 2>/dev/null)
    else:
        RECENT_PROGRESS=""
```

When the `TaskOutput` call fails at runtime (tool not loaded, host returns an
error), silently fall back to tailing `progress.log`. The capability flag opts
in; the actual call must still be guarded by a runtime availability check.

The file is written by the task-runner at every phase and stage boundary, so it
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
  host's `TaskList` output for the parent-task stage state because hosts like
  Claude Code stream that surface live.
- When the host adapter has advertised `monitor_tool: true`, `crew:status`
  prefers `TaskOutput(taskId)` for the "Recent events" stream (P5). The
  stderr-mirror rule in `core/agents/task-runner.md` ensures every progress
  event is written to stderr (which Claude Code captures as `TaskOutput`),
  eliminating the file-buffering caveat. `progress.log` is still written, so
  the fallback is always safe.
- See `core/rules/host-capabilities.md` for the schema and the absence
  contract.
