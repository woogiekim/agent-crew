#!/usr/bin/env bash
# outline-posttooluse.sh — fires after mcp__outline__document_update/create
# If NOT inside an agent-crew workflow, reminds Claude to sync to connect-docs.
# If inside a scribe workflow, the rule in the agent handles sync (no-op here).

set -euo pipefail

TOOL_OUTPUT=$(cat)

# Suppress if inside an agent-crew active task (scribe rule handles it)
STATE_DIR="${AGENT_CREW_HOME:-${HOME}/.agent-crew}/state"
if ls "${STATE_DIR}"/*/tasks/active 2>/dev/null | grep -q .; then
  exit 0
fi

# Extract title, id, url from tool output JSON
DOC_INFO=$(echo "$TOOL_OUTPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    doc = data.get('data', {})
    title = doc.get('title', '')
    doc_id = doc.get('id', '')
    url = doc.get('url', '')
    if doc_id:
        base = 'https://enuri.wiki.cowave.kr'
        print(f'{title}|||{doc_id}|||{base}{url}')
except Exception:
    pass
" 2>/dev/null || true)

if [ -z "$DOC_INFO" ]; then
  exit 0
fi

IFS='|||' read -r TITLE DOC_ID FULL_URL <<< "$DOC_INFO"

echo "[outline-sync] Outline 문서 \"${TITLE}\"가 수정되었습니다."
echo "connect-docs 동기화를 자동으로 실행해주세요 (scribe 워크플로 Step 4)."
echo "문서 URL: ${FULL_URL}"
echo "문서 ID: ${DOC_ID}"
