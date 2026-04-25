#!/usr/bin/env bash
# ship-check.sh — /ship 동시 실행 제한 확인 (읽기 전용)
# Usage: bash ship-check.sh <state_dir>
# Output: active=N max=N
set -euo pipefail

STATE_DIR="${1:?Usage: ship-check.sh <state_dir>}"
CONFIG="${STATE_DIR}/config.json"

MAX=$(python3 -c "import json; print(json.load(open('${CONFIG}')).get('maxConcurrentTasks', 2))" 2>/dev/null || echo 2)
ACTIVE=$(python3 -c "
import json, glob
count = 0
for f in glob.glob('${STATE_DIR}/tasks/*/pipeline.json'):
    try:
        p = json.load(open(f))
        if p.get('status') == 'IN_PROGRESS': count += 1
    except: pass
print(count)
" 2>/dev/null || echo 0)

echo "active=${ACTIVE} max=${MAX}"
