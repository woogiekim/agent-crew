#!/bin/bash
# Detect common rule violations after file edits.
# PostToolUse hook: receives JSON via stdin with tool_input.file_path.

INPUT=$(cat)
CHANGED_FILE=$(python3 -c "
import json, sys
try:
    data = json.loads(sys.argv[1])
    ti = data.get('tool_input', {})
    print(ti.get('file_path', ti.get('new_path', '')) if isinstance(ti, dict) else '')
except Exception:
    print('')
" "$INPUT" 2>/dev/null)

if [[ -z "$CHANGED_FILE" || ! -f "$CHANGED_FILE" ]]; then
  exit 0
fi

VIOLATIONS=()

case "$CHANGED_FILE" in
  *.kt)
    if [[ "$CHANGED_FILE" != *Test.kt ]]; then
      ELSE_COUNT=$(grep -nE '\belse\b' "$CHANGED_FILE" | grep -vE '^\s*//' | wc -l | tr -d ' ')
      if [[ "$ELSE_COUNT" -gt 0 ]]; then
        VIOLATIONS+=("[Object Calisthenics #2] Detected else usage (${ELSE_COUNT} occurrence(s)). Prefer early return or polymorphism.")
      fi
    fi

    GETTER_COUNT=$(grep -nE '\.get[A-Z]|\.is[A-Z]' "$CHANGED_FILE" | wc -l | tr -d ' ')
    if [[ "$GETTER_COUNT" -gt 5 ]]; then
      VIOLATIONS+=("[Tell, Do Not Ask] Detected heavy getter usage (${GETTER_COUNT} occurrence(s)). Delegate behavior to objects.")
    fi

    if [[ "$CHANGED_FILE" == */src/main/* ]]; then
      TEST_FILE="${CHANGED_FILE/src\/main/src\/test}"
      TEST_FILE="${TEST_FILE%.kt}Test.kt"
      if [[ ! -f "$TEST_FILE" ]]; then
        VIOLATIONS+=("[TDD] Missing test file. Create ${TEST_FILE} first.")
      fi
    fi
    ;;

  *.ts|*.tsx)
    # Exclude comment-only lines (// ...) to avoid false positives
    ANY_COUNT=$(grep -nE '\bany\b' "$CHANGED_FILE" | grep -vE '^\s*//' | wc -l | tr -d ' ')
    if [[ "$ANY_COUNT" -gt 0 ]]; then
      VIOLATIONS+=("[TypeScript] Detected any usage (${ANY_COUNT} occurrence(s)). Use explicit types.")
    fi

    if [[ "$CHANGED_FILE" != *test* && "$CHANGED_FILE" != *spec* ]]; then
      LOG_COUNT=$(grep -nE 'console\.(log|debug|info)' "$CHANGED_FILE" | wc -l | tr -d ' ')
      if [[ "$LOG_COUNT" -gt 0 ]]; then
        VIOLATIONS+=("[Code Quality] Detected console usage (${LOG_COUNT} occurrence(s)). Remove it or use a logger.")
      fi
    fi

    if [[ "$CHANGED_FILE" == */src/* && "$CHANGED_FILE" != *test* && "$CHANGED_FILE" != *spec* ]]; then
      TEST_FILE="${CHANGED_FILE%.*}.test.${CHANGED_FILE##*.}"
      if [[ ! -f "$TEST_FILE" ]]; then
        VIOLATIONS+=("[TDD] Missing test file. Create ${TEST_FILE} first.")
      fi
    fi
    ;;

  *.js|*.jsx)
    if [[ "$CHANGED_FILE" != *test* && "$CHANGED_FILE" != *spec* ]]; then
      LOG_COUNT=$(grep -nE 'console\.(log|debug|info)' "$CHANGED_FILE" | wc -l | tr -d ' ')
      if [[ "$LOG_COUNT" -gt 0 ]]; then
        VIOLATIONS+=("[Code Quality] Detected console usage (${LOG_COUNT} occurrence(s)). Remove it or use a logger.")
      fi
    fi
    ;;
esac

if [[ ${#VIOLATIONS[@]} -gt 0 ]]; then
  echo "Rule violations detected: $CHANGED_FILE"
  printf '%s\n' "${VIOLATIONS[@]}"
  echo ""
  echo "Fix the items above before continuing."
  exit 2
fi

exit 0
