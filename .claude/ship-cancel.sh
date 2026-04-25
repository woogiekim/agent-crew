#!/usr/bin/env bash
# ship-cancel.sh — /ship 취소 시 워크트리·브랜치·태스크 디렉토리 정리
# Usage: bash ship-cancel.sh <project_root> <worktree_path> <branch> <task_dir>
set -euo pipefail

PROJECT_ROOT="${1:?Usage: ship-cancel.sh <project_root> <worktree_path> <branch> <task_dir>}"
WORKTREE_PATH="${2:?}"
BRANCH="${3:?}"
TASK_DIR="${4:?}"

git -C "$PROJECT_ROOT" worktree remove --force "$WORKTREE_PATH" 2>/dev/null || true
git -C "$PROJECT_ROOT" branch -D "$BRANCH" 2>/dev/null || true
rm -rf "$TASK_DIR"
echo "cancelled: branch=${BRANCH}"
