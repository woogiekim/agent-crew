#!/usr/bin/env bash
# PostToolUse[Agent]: emit a diff summary of repo changes after an Agent call
# completes. Header text is English so the diff display is consistent across
# adapters; agent narrative localization is governed by core/rules/output-language.md.

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
. "${HOOK_DIR}/read-hook-input.sh"
INPUT="$(read_agent_crew_hook_input || true)"
TOOL=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null <<< "$INPUT" || echo "")
[ "$TOOL" != "Agent" ] && exit 0

BEFORE=$(cat /tmp/.agent-crew/head-before 2>/dev/null)
[ -z "$BEFORE" ] && exit 0

NEW_COMMITS=$(git log --oneline "${BEFORE}..HEAD" 2>/dev/null)
UNCOMMITTED_STAT=$(git diff --stat HEAD 2>/dev/null)

[ -z "$NEW_COMMITS" ] && [ -z "$UNCOMMITTED_STAT" ] && exit 0

echo ""
echo "┌─ Agent Changes ─────────────────────────────────────────"
if [ -n "$NEW_COMMITS" ]; then
    echo "│ Commits:"
    while IFS= read -r line; do echo "│   $line"; done <<< "$NEW_COMMITS"
fi
if [ -n "$UNCOMMITTED_STAT" ]; then
    echo "│ Uncommitted:"
    while IFS= read -r line; do echo "│   $line"; done <<< "$UNCOMMITTED_STAT"
fi
echo "└──────────────────────────────────────────────────────────"
if [ -n "$NEW_COMMITS" ]; then
    git diff "${BEFORE}..HEAD" 2>/dev/null | head -400
elif [ -n "$UNCOMMITTED_STAT" ]; then
    git diff HEAD 2>/dev/null | head -400
fi
