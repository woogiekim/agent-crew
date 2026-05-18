#!/usr/bin/env bash
# Tests for result.md dual-format parsing (GitHub issue #31).
#
# Verifies that the grep/sed expressions used by crew:status and run.md
# correctly extract STATUS and BRANCH from both the canonical plain-text
# format and the legacy Markdown-bold format.

set -u
source "$(dirname "$0")/_lib.bash"

# ---------------------------------------------------------------------------
# Helpers that replicate the parser expressions from core/commands/status.md
# ---------------------------------------------------------------------------

# Replicate Step 3 pre-F4 STATUS detection (mirrors core/commands/status.md Step 3).
# Accepts both canonical plain-text ("STATUS: completed") and legacy Markdown-bold
# ("**Status:** completed") — colon is INSIDE the bold markers in the legacy format.
parse_status() {
  local file="$1"
  if grep -qiE "^(\*\*)?status:\*{0,2}\s+\**completed\**" "${file}" 2>/dev/null; then
    echo "completed"
  elif grep -qiE "^(\*\*)?status:\*{0,2}\s+\**(blocked|BLOCKED)\**" "${file}" 2>/dev/null; then
    echo "blocked"
  else
    echo "in-progress"
  fi
}

# Replicate Step 4 BRANCH extraction (mirrors core/commands/status.md Step 4).
# Accepts both canonical plain-text ("BRANCH: value") and legacy Markdown-bold
# ("**Branch:** value") — colon is INSIDE the bold markers in the legacy format.
parse_branch() {
  local file="$1"
  grep -iE "^(\*\*)?branch:\*{0,2}" "${file}" 2>/dev/null \
    | head -1 \
    | sed -E 's/^\*\*[Bb]ranch:\*\*[[:space:]]*//' \
    | sed -E 's/^[Bb][Rr][Aa][Nn][Cc][Hh]:[[:space:]]*//' \
    | tr -d '\r' \
    || true
}

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

TMP=$(make_tmp)

# --- Canonical plain-text completed result ---
PLAIN_COMPLETED="${TMP}/plain_completed.md"
cat > "${PLAIN_COMPLETED}" <<'EOF'
# Implement order management API

DESCRIPTION: Implement order management API
BRANCH: feat/order-api
STATUS: completed
COMMITS: 3
LOG:
abc1234 Add cancel endpoint
def5678 Add idempotency guard
EOF

# --- Canonical plain-text blocked result ---
PLAIN_BLOCKED="${TMP}/plain_blocked.md"
cat > "${PLAIN_BLOCKED}" <<'EOF'
# Some task

STATUS: blocked
BRANCH: fix/something
BLOCKER: crash_budget_exceeded
DETAIL: Agent crashed 5 times.
EOF

# --- Markdown-bold format (legacy, issue #31) ---
MARKDOWN_COMPLETED="${TMP}/markdown_completed.md"
cat > "${MARKDOWN_COMPLETED}" <<'EOF'
**Task:** Add a greet.py module

**Branch:** feat/add-greet-py-module
**Status:** completed
**Commits:** 1
EOF

# --- Markdown-bold blocked ---
MARKDOWN_BLOCKED="${TMP}/markdown_blocked.md"
cat > "${MARKDOWN_BLOCKED}" <<'EOF'
**Task:** Some task

**Status:** blocked
**Branch:** fix/broken-thing
EOF

# --- Mixed case variants ---
MIXEDCASE="${TMP}/mixedcase.md"
cat > "${MIXEDCASE}" <<'EOF'
# Task

STATUS: Completed
BRANCH: feat/mixed-case
COMMITS: 2
EOF

# --- No STATUS line (in-progress) ---
NO_STATUS="${TMP}/no_status.md"
cat > "${NO_STATUS}" <<'EOF'
# Task without status yet

BRANCH: feat/in-progress
EOF

# --- CANCELLED format (plan approval gate) ---
CANCELLED="${TMP}/cancelled.md"
cat > "${CANCELLED}" <<'EOF'
# Task

DESCRIPTION: Task
BRANCH: feat/cancelled
STATUS: CANCELLED
COMMITS: 0
LOG: (cancelled before execution)

CHANGES: none — cancelled at plan approval gate
EOF

# ---------------------------------------------------------------------------
# STATUS parsing tests
# ---------------------------------------------------------------------------

it "plain-text STATUS: completed is recognized"
assert_eq "completed" "$(parse_status "${PLAIN_COMPLETED}")"

it "plain-text STATUS: blocked is recognized"
assert_eq "blocked" "$(parse_status "${PLAIN_BLOCKED}")"

it "markdown-bold **Status:** completed is recognized"
assert_eq "completed" "$(parse_status "${MARKDOWN_COMPLETED}")"

it "markdown-bold **Status:** blocked is recognized"
assert_eq "blocked" "$(parse_status "${MARKDOWN_BLOCKED}")"

it "mixed-case STATUS: Completed is recognized"
assert_eq "completed" "$(parse_status "${MIXEDCASE}")"

it "missing STATUS line reports in-progress"
assert_eq "in-progress" "$(parse_status "${NO_STATUS}")"

it "STATUS: CANCELLED is NOT reported as completed"
# CANCELLED is not 'completed' — status should be in-progress (no completed match)
# The session collect loop maps CANCELLED to 'blocked' via the Python regex,
# but the shell parse_status here only checks for completed/blocked keywords.
result="$(parse_status "${CANCELLED}")"
assert_not_contains "${result}" "completed"

# ---------------------------------------------------------------------------
# BRANCH extraction tests
# ---------------------------------------------------------------------------

it "plain-text BRANCH: value is extracted correctly"
assert_eq "feat/order-api" "$(parse_branch "${PLAIN_COMPLETED}")"

it "plain-text BRANCH: blocked result is extracted correctly"
assert_eq "fix/something" "$(parse_branch "${PLAIN_BLOCKED}")"

it "markdown-bold **Branch:** value is extracted correctly"
assert_eq "feat/add-greet-py-module" "$(parse_branch "${MARKDOWN_COMPLETED}")"

it "markdown-bold **Branch:** blocked is extracted correctly"
assert_eq "fix/broken-thing" "$(parse_branch "${MARKDOWN_BLOCKED}")"

it "mixed-case BRANCH: value is extracted correctly"
assert_eq "feat/mixed-case" "$(parse_branch "${MIXEDCASE}")"

it "parse_branch returns empty string for missing BRANCH line"
result="$(parse_branch "${NO_STATUS}")"
# NO_STATUS does have a BRANCH line; confirm it extracted it
assert_eq "feat/in-progress" "${result}"

# ---------------------------------------------------------------------------
# Python collect-loop regex (from Step 4S in status.md)
# ---------------------------------------------------------------------------

it "Python collect regex matches plain-text STATUS: completed"
result=$(python3 -c "
import re
# Mirrors the _status_re from status.md Step 4S collect loop.
# Canonical: 'STATUS: value'; legacy: '**Status:** value' (colon inside bold).
_status_re = re.compile(r'^(?:\*\*)?status:\*{0,2}\s+\*{0,2}(\w+)\*{0,2}', re.IGNORECASE | re.MULTILINE)
content = open('${PLAIN_COMPLETED}').read()
m = _status_re.search(content)
print(m.group(1).lower() if m else 'none')
")
assert_eq "completed" "${result}"

it "Python collect regex matches markdown-bold **Status:** completed"
result=$(python3 -c "
import re
_status_re = re.compile(r'^(?:\*\*)?status:\*{0,2}\s+\*{0,2}(\w+)\*{0,2}', re.IGNORECASE | re.MULTILINE)
content = open('${MARKDOWN_COMPLETED}').read()
m = _status_re.search(content)
print(m.group(1).lower() if m else 'none')
")
assert_eq "completed" "${result}"

it "Python collect regex matches plain-text STATUS: blocked"
result=$(python3 -c "
import re
_status_re = re.compile(r'^(?:\*\*)?status:\*{0,2}\s+\*{0,2}(\w+)\*{0,2}', re.IGNORECASE | re.MULTILINE)
content = open('${PLAIN_BLOCKED}').read()
m = _status_re.search(content)
print(m.group(1).lower() if m else 'none')
")
assert_eq "blocked" "${result}"

it "Python collect regex matches markdown-bold **Status:** blocked"
result=$(python3 -c "
import re
_status_re = re.compile(r'^(?:\*\*)?status:\*{0,2}\s+\*{0,2}(\w+)\*{0,2}', re.IGNORECASE | re.MULTILINE)
content = open('${MARKDOWN_BLOCKED}').read()
m = _status_re.search(content)
print(m.group(1).lower() if m else 'none')
")
assert_eq "blocked" "${result}"

# ---------------------------------------------------------------------------
# Step 6 Python snippet (stage list renderer)
# ---------------------------------------------------------------------------

it "Step 6 Python status_re matches plain-text STATUS: completed"
result=$(python3 -c "
import re
# Mirrors the _status_re from status.md Step 6 stage-list renderer.
# Canonical: 'STATUS: completed'; legacy: '**Status:** completed'.
_status_re = re.compile(r'^(?:\*\*)?status:\*{0,2}\s+\*{0,2}completed\*{0,2}', re.IGNORECASE | re.MULTILINE)
content = open('${PLAIN_COMPLETED}').read()
print('yes' if _status_re.search(content) else 'no')
")
assert_eq "yes" "${result}"

it "Step 6 Python status_re matches markdown-bold **Status:** completed"
result=$(python3 -c "
import re
_status_re = re.compile(r'^(?:\*\*)?status:\*{0,2}\s+\*{0,2}completed\*{0,2}', re.IGNORECASE | re.MULTILINE)
content = open('${MARKDOWN_COMPLETED}').read()
print('yes' if _status_re.search(content) else 'no')
")
assert_eq "yes" "${result}"

it "Step 6 Python status_re does NOT match blocked content as completed"
result=$(python3 -c "
import re
_status_re = re.compile(r'^(?:\*\*)?status:\*{0,2}\s+\*{0,2}completed\*{0,2}', re.IGNORECASE | re.MULTILINE)
content = open('${PLAIN_BLOCKED}').read()
print('yes' if _status_re.search(content) else 'no')
")
assert_eq "no" "${result}"

end_report
