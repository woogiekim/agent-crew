#!/bin/bash
# Detect common rule violations after file edits.
# PostToolUse hook: receives the flattened envelope JSON via stdin, as
# produced by core/scripts/post-tool-use-dispatcher.py — top-level
# file_path / new_path / path fields, no tool_input wrapper. The legacy
# nested tool_input.file_path / tool_input.new_path shape is kept as a
# defensive fallback only, in case a caller ever sends the old shape.

INPUT=$(cat)
CHANGED_FILE=$(python3 -c "
import json, sys

def pick(d, *keys):
    if not isinstance(d, dict):
        return ''
    for key in keys:
        value = d.get(key)
        if isinstance(value, str) and value:
            return value
    return ''

try:
    data = json.loads(sys.argv[1])
except Exception:
    data = {}

result = pick(data, 'file_path', 'new_path', 'path')
if not result:
    result = pick(data.get('tool_input', {}), 'file_path', 'new_path')

print(result)
" "$INPUT" 2>/dev/null)

if [[ -z "$CHANGED_FILE" || ! -f "$CHANGED_FILE" ]]; then
  exit 0
fi

AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"
case "$CHANGED_FILE" in
  "${AGENT_CREW_HOME}/state"/*)
    exit 0
    ;;
esac

VIOLATIONS=()

file_extension() {
  local path="$1"
  local base="${path##*/}"
  if [[ "${base}" == *.* ]]; then
    printf '%s' "${base##*.}" | tr '[:upper:]' '[:lower:]'
  else
    printf ''
  fi
}

is_test_file() {
  local path="$1"
  case "$path" in
    *Test.*|*Tests.*|*_test.*|*.test.*|*.spec.*|*/test/*|*/tests/*|*/__tests__/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_code_file() {
  local path="$1"
  local ext
  ext="$(file_extension "$path")"
  case "$ext" in
    kt|kts|java|jsp|jspf|ts|tsx|js|jsx|mjs|cjs|py|pyi|go|rs|rb|swift|scala|sc|groovy|gradle|sh|bash|zsh|sql|lua|php|c|cc|cpp|h|hpp|cs|dart|vue|svelte|xml|yml|yaml)
      return 0
      ;;
  esac

  if command -v file >/dev/null 2>&1; then
    local mime
    mime="$(file --mime-type -b "$path" 2>/dev/null || true)"
    case "$mime" in
      text/x-*|text/*script*|application/x-shellscript)
        return 0
        ;;
    esac
  fi

  return 1
}

code_lines() {
  grep -nE '.' "$1" \
    | grep -vE '^[0-9]+:[[:space:]]*(//|#|/\*|\*|\*/|<!--|<%--)' \
    || true
}

count_else_usage() {
  local path="$1"
  local ext
  ext="$(file_extension "$path")"

  case "$ext" in
    py|pyi)
      code_lines "$path" | grep -E '^[0-9]+:[[:space:]]*else[[:space:]]*:' | wc -l | tr -d ' '
      ;;
    sh|bash|zsh)
      code_lines "$path" | grep -E '^[0-9]+:[[:space:]]*else([[:space:]]|$)' | wc -l | tr -d ' '
      ;;
    yml|yaml|xml)
      printf '0'
      ;;
    *)
      code_lines "$path" | grep -E '(^|[[:space:]\};])else([[:space:]\{\}:]|$)' | wc -l | tr -d ' '
      ;;
  esac
}

if is_code_file "$CHANGED_FILE"; then
  if ! is_test_file "$CHANGED_FILE"; then
    ELSE_COUNT=$(count_else_usage "$CHANGED_FILE")
    if [[ "$ELSE_COUNT" -gt 0 ]]; then
      VIOLATIONS+=("[Object Calisthenics #2] Detected else usage (${ELSE_COUNT} occurrence(s)) in a code file. Prefer early return, guard clauses, polymorphism, or table-driven dispatch.")
    fi
  fi

  GETTER_COUNT=$(code_lines "$CHANGED_FILE" | grep -E '\.get[A-Z]|\.is[A-Z]' | wc -l | tr -d ' ')
  if [[ "$GETTER_COUNT" -gt 5 ]]; then
    VIOLATIONS+=("[Tell, Do Not Ask] Detected heavy getter usage (${GETTER_COUNT} occurrence(s)). Delegate behavior to objects.")
  fi
fi

case "$CHANGED_FILE" in
  *.kt)
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
