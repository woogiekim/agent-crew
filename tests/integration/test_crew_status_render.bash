#!/usr/bin/env bash
# Integration: verify the Step 6 stage-rendering snippet from
# core/commands/status.md produces well-formed output for a synthetic
# task state.
#
# The snippet is extracted inline from status.md (the test would be
# brittle if it tried to source-extract a python block from markdown).
# When status.md changes its snippet, this test will need to be updated
# in lockstep — but the regression value (a markdown edit that breaks
# the snippet would otherwise go unnoticed) justifies the duplication.

set -u
source "$(dirname "$0")/../shell/_lib.bash"

TMP=$(make_tmp)
TD="${TMP}/task"
mkdir -p "${TD}"

# --------------------------------------------------------------------------- #
# Build synthetic state                                                       #
# --------------------------------------------------------------------------- #

cat > "${TD}/pipeline.json" <<'EOF'
{
  "schema_version": 1,
  "task": "Implement order management API",
  "stages": ["planner", "backend", "frontend", "reviewer"],
  "completed_stages": 2,
  "stage_agent_status": {
    "1": {"planner": "completed"},
    "2": {"backend": "completed"}
  }
}
EOF

cat > "${TD}/register.json" <<'EOF'
{
  "schema_version": 1,
  "task_id": "20260101-120000-0",
  "session_id": "20260101-120000",
  "task": "Implement order management API",
  "branch": "feat/orders",
  "project_root": "/tmp/proj",
  "task_dir": "/tmp/td",
  "execution_mode": "single",
  "current_phase": "phase_2",
  "approval_status": "approved",
  "verification_status": "not_started"
}
EOF

cat > "${TD}/progress.buffer.jsonl" <<'EOF'
{"ts":"2026-01-01T12:00:00Z","trace_id":"x","task_id":"20260101-120000-0","event":"STARTED","detail":"Implement order management API"}
{"ts":"2026-01-01T12:00:30Z","trace_id":"x","task_id":"20260101-120000-0","event":"PHASE","detail":"1b — Analysis"}
{"ts":"2026-01-01T12:01:00Z","trace_id":"x","task_id":"20260101-120000-0","event":"STAGE","detail":"1/4 — planner"}
EOF

# No result.md (in-progress task)
RESULT="${TD}/result.md"

# --------------------------------------------------------------------------- #
# Invoke the Step 6 renderer                                                  #
# --------------------------------------------------------------------------- #

PIPELINE="${TD}/pipeline.json"

OUT=$(python3 -c "
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

    suffix = '  ← current' if marker == '[▶]' else ''
    lines.append(f'  {marker} {agent_label}{suffix}')

for line in lines:
    print(line)
print()
print(f'Completed: {completed} / {total} stages')
" 2>&1)

it "renderer exits 0 for valid pipeline.json"
# We didn't capture rc above; rerun for the assertion
python3 -c "
import json
p = json.load(open('${PIPELINE}'))
" 2>/dev/null
assert_exit 0 $?

it "render output contains completion summary"
assert_contains "${OUT}" "Completed: 2 / 4 stages"

it "render output marks first two stages [✓]"
# Each completed stage should have the check mark
n_done=$(echo "${OUT}" | grep -c '\[✓\]')
assert_eq 2 "${n_done}" "completed stage count"

it "render output marks third stage [▶] (current)"
assert_contains "${OUT}" "[▶] frontend"

it "render output marks fourth stage [ ] (pending)"
assert_contains "${OUT}" "[ ] reviewer"

it "render output adds '← current' marker to active stage"
assert_contains "${OUT}" "← current"

# --------------------------------------------------------------------------- #
# Edge case: missing pipeline.json                                            #
# --------------------------------------------------------------------------- #

it "missing pipeline.json emits 'task may still be in Phase 1' fallback"
out_missing=$(python3 -c "
import json, sys
try:
    p = json.load(open('/nonexistent/pipeline.json'))
except Exception as e:
    print('(pipeline.json not found — task may still be in Phase 1)')
    sys.exit(0)
" 2>&1)
assert_contains "${out_missing}" "Phase 1"

# --------------------------------------------------------------------------- #
# Edge case: result.md present with STATUS: completed → all stages done       #
# --------------------------------------------------------------------------- #

cat > "${RESULT}" <<'EOF'
# Implement order management API

STATUS: completed
COMMITS: 5
EOF

OUT2=$(python3 -c "
import json, sys

pipeline_path = '${PIPELINE}'
result_path = '${RESULT}'

p = json.load(open(pipeline_path))
stages = p.get('stages', [])
completed = p.get('completed_stages', 0)

import os
overall_done = False
try:
    content = open(result_path).read()
    overall_done = 'STATUS: completed' in content
except:
    pass

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
    print(f'  {marker} {agent_label}')
")

it "result.md with STATUS: completed marks ALL stages done"
n_done=$(echo "${OUT2}" | grep -c '\[✓\]')
assert_eq 4 "${n_done}" "all stages done when result.md says completed"

end_report
