#!/bin/bash
# Block dangerous shell commands before execution.

COMMAND="$1"

DANGEROUS_PATTERNS=(
  "rm -rf /"
  "rm -rf ~"
  "rm -rf \\$HOME"
  ":(){ :|:& };:"
  "mkfs"
  "dd if="
  "> /dev/sd"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -Eq "$pattern"; then
    echo "Blocked dangerous command pattern: '$pattern'"
    echo "Command: $COMMAND"
    echo "Explicit user approval is required before running this command."
    exit 2
  fi
done

exit 0
