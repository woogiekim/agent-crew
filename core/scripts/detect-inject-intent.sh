#!/usr/bin/env bash
# detect-inject-intent.sh — Classify user input for task-injection intent.
#
# Purpose:
#   When a live crew:run session is in progress and the user submits a
#   new task, this script detects whether the input phrasing indicates
#   they want to *add* to the live session (rather than start a fresh
#   one). Lets crew:run Step 1.5 skip the "Inject or run independently?"
#   prompt when the user's phrasing is unambiguous.
#
# Inputs:
#   stdin   — user input text (the raw `crew:run "..."` argument or the
#             full request).
#   $1      — optional: user input as argument (used when stdin is empty,
#             e.g., for diagnostic shell invocation).
#
# Outputs:
#   stdout  — matched phrase on hit (for log_progress / diagnostic);
#             empty on miss.
#
# Exit codes:
#   0 — match found (inject-intent detected). stdout = the matched phrase.
#   1 — no match (default; caller should treat as "ambiguous, ask user").
#
# Patterns (case-insensitive, anchored to word boundaries where sensible):
#   Korean inject phrases:
#     "추가로 해줘" / "추가 해줘" / "추가로 작업해줘" / "추가로 부탁"
#     "이것도 부탁해" / "이것도 해줘" / "이것까지"
#     "더해줘" / "더 해줘"
#     "추가로 처리해줘" / "이어서 해줘"
#   English inject phrases:
#     "also do" / "and also" / "additionally"
#     "one more thing" / "while you're at it" / "while youre at it"
#     "plus do"
#
# Rationale: the patterns deliberately require complete connectors
# (not just "추가" or "also" alone) so that legitimate fresh-start
# requests don't trigger false-positives. The detection is advisory —
# the caller can still surface a structured prompt when the match is
# borderline.

INPUT=""
if [ -t 0 ]; then
  INPUT="${1:-}"
else
  INPUT="$(cat)"
fi

if [ -z "${INPUT}" ]; then
  exit 1
fi

# Korean patterns. Use POSIX BRE / ERE that BusyBox grep can handle.
# We use grep -E with case-insensitive matching for the Latin portions
# and literal byte matching for Hangul (Hangul is case-irrelevant).
KO_PATTERNS=(
  '추가로 *해줘'
  '추가 *해줘'
  '추가로 *작업해줘'
  '추가로 *부탁'
  '추가로 *처리해줘'
  '이것도 *부탁해'
  '이것도 *해줘'
  '이것까지'
  '더 *해줘'
  '더해줘'
  '이어서 *해줘'
)

EN_PATTERNS=(
  'also do'
  'and also'
  'additionally'
  'one more thing'
  "while you're at it"
  'while youre at it'
  'while you are at it'
  'plus do'
)

# Check Korean (literal grep — Hangul has no case folding).
for p in "${KO_PATTERNS[@]}"; do
  if printf '%s' "${INPUT}" | grep -E "${p}" >/dev/null 2>&1; then
    # Extract the matched substring for diagnostic output.
    MATCH=$(printf '%s' "${INPUT}" | grep -oE "${p}" | head -1)
    printf '%s\n' "${MATCH}"
    exit 0
  fi
done

# Check English (case-insensitive via -i).
for p in "${EN_PATTERNS[@]}"; do
  if printf '%s' "${INPUT}" | grep -iE "${p}" >/dev/null 2>&1; then
    MATCH=$(printf '%s' "${INPUT}" | grep -ioE "${p}" | head -1)
    printf '%s\n' "${MATCH}"
    exit 0
  fi
done

exit 1
