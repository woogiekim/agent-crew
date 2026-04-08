#!/bin/bash
# guard-dangerous-commands.sh
# PreToolUse(Bash) 시 자동 실행 — 위험한 명령어 차단

COMMAND="${CLAUDE_TOOL_INPUT_COMMAND:-}"

# 위험 명령어 패턴
DANGEROUS_PATTERNS=(
  "rm -rf"
  "DROP TABLE"
  "DELETE FROM.*WHERE.*1=1"
  "git push --force"
  "git reset --hard HEAD"
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qi "$pattern"; then
    echo "🚫 차단: 위험한 명령어 감지 — '$pattern'"
    echo "명령어: $COMMAND"
    echo "이 명령어를 실행하려면 사용자의 명시적 승인이 필요합니다."
    exit 1
  fi
done

exit 0
