#!/usr/bin/env bash
# ship-init.sh — /ship TASK 초기화 (브랜치·워크트리·상태 디렉토리·daemon 시작)
# Usage: bash ship-init.sh <project_root> <state_dir>
# Output: task_id=... branch=... worktree=...
set -euo pipefail

PROJECT_ROOT="${1:?Usage: ship-init.sh <project_root> <state_dir>}"
STATE_DIR="${2:?Usage: ship-init.sh <project_root> <state_dir>}"
AGENT_CREW_DIR="${HOME}/.claude/agent-crew"

# ── TASK_ID / 브랜치 / 워크트리 생성 ────────────────────────
TASK_ID=$(date +%Y%m%d-%H%M%S)
BRANCH="feature/task-${TASK_ID}"
WORKTREE_PATH="${PROJECT_ROOT}/../$(basename "${PROJECT_ROOT}")-task-${TASK_ID}"

git -C "$PROJECT_ROOT" show-ref --verify --quiet refs/heads/feature/main \
  || git -C "$PROJECT_ROOT" checkout -b feature/main

git -C "$PROJECT_ROOT" checkout -b "$BRANCH" feature/main
git -C "$PROJECT_ROOT" checkout -
git -C "$PROJECT_ROOT" worktree add "$WORKTREE_PATH" "$BRANCH"

# ── task 상태 디렉토리 초기화 ────────────────────────────────
TASK_DIR="${STATE_DIR}/tasks/${TASK_ID}"
mkdir -p "${TASK_DIR}/context" "${TASK_DIR}/agent_signal"
printf '%s\n' "$WORKTREE_PATH" > "${TASK_DIR}/worktree_path.txt"
printf '%s\n' "$BRANCH"        > "${TASK_DIR}/branch.txt"
printf '%s\n' "REQUIREMENTS"   > "${TASK_DIR}/phase.txt"
printf '%s\n' "planner"        > "${TASK_DIR}/active_agent.txt"
printf '%s\n' "0"              > "${TASK_DIR}/iterations.txt"
printf '%s\n' "0"              > "${TASK_DIR}/retry_count.txt"
printf '%s\n' "$TASK_ID"       > "${WORKTREE_PATH}/.crew_task_id"
printf '%s\n' '{"task":"","agents":[],"currentIndex":0,"status":"PENDING"}' > "${TASK_DIR}/pipeline.json"

# ── crew-daemon 상태 확인 및 시작 ────────────────────────────
bash "${AGENT_CREW_DIR}/crew-daemon.sh" status 2>/dev/null | grep -q RUNNING \
  || nohup bash "${AGENT_CREW_DIR}/crew-daemon.sh" start \
       >> "${STATE_DIR}/daemon.log" 2>&1 &

echo "task_id=${TASK_ID}"
echo "branch=${BRANCH}"
echo "worktree=${WORKTREE_PATH}"
