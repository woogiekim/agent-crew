#!/usr/bin/env bash
# crew-wait-signal.sh — agent_signal/{agent}.ready 신호 대기 후 제거
# Usage: bash crew-wait-signal.sh <task_dir> <agent|*> [timeout_secs]
#   agent="*" or ""  — 어떤 신호든 첫 번째로 도착한 것을 반환
# Exit 0: signal found (prints "signal:<agent>"). Exit 1: timeout.
set -euo pipefail

TASK_DIR="${1:?Usage: crew-wait-signal.sh <task_dir> <agent|*> [timeout_secs]}"
AGENT="${2:-*}"
TIMEOUT="${3:-30}"

SIGNAL_DIR="${TASK_DIR}/agent_signal"
ITERS=$(( (TIMEOUT + 1) / 2 ))

for i in $(seq 1 "$ITERS"); do
  if [ "$AGENT" = "*" ] || [ -z "$AGENT" ]; then
    for sig in "${SIGNAL_DIR}/"*.ready; do
      [ -f "$sig" ] || continue
      name=$(basename "$sig" .ready)
      rm -f "$sig"
      echo "signal:${name}"
      exit 0
    done
  else
    if [ -f "${SIGNAL_DIR}/${AGENT}.ready" ]; then
      rm -f "${SIGNAL_DIR}/${AGENT}.ready"
      echo "signal:${AGENT}"
      exit 0
    fi
  fi
  sleep 2
done

echo "ERROR: ${AGENT}.ready 신호 없음 (timeout ${TIMEOUT}s)" >&2
exit 1
