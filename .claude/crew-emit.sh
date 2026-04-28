#!/usr/bin/env bash
# crew-emit.sh — events.jsonl에 이벤트 append
# Usage: bash crew-emit.sh <task_dir> <event> [agent]
set -euo pipefail

TASK_DIR="${1:?Usage: crew-emit.sh <task_dir> <event> [agent]}"
EVENT="${2:?Usage: crew-emit.sh <task_dir> <event> [agent]}"
AGENT="${3:-}"

if [ -n "$AGENT" ]; then
  printf '{"event":"%s","agent":"%s"}\n' "$EVENT" "$AGENT" >> "${TASK_DIR}/events.jsonl"
else
  printf '{"event":"%s"}\n' "$EVENT" >> "${TASK_DIR}/events.jsonl"
fi
