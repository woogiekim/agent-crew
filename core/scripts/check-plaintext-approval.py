#!/usr/bin/env python3
"""
check-plaintext-approval.py — Forbid free-text approval prompts.

Purpose:
  Validate that an agent response does NOT contain free-text yes/no
  approval prompts like "Shall I merge and push?" — those violate
  `core/rules/disambiguation.md` (all questions MUST be structured
  options via the host's interactive_question capability) and the
  approval-gate rule in `core/global-agents.md`. The validator runs
  as a PostToolUse hook so the model receives feedback when it
  produces a forbidden phrase.

Inputs:
  - stdin (default): a hook payload JSON. The script attempts to
    extract text from `tool_response.content`, `tool_response.text`,
    `tool_response.message`, or `tool_response` itself when it is a
    string. Unknown shapes are treated as empty (exit 0).
  - --text "..."  : pre-extracted text for diagnostic invocation.
  - --tool NAME   : restrict to a specific `tool_name` (default: Agent).
                    When the hook payload's `tool_name` does not match,
                    exit 0 silently.

Exit codes:
  0 — no violation found (or payload not applicable).
  2 — forbidden phrase detected. The first match is printed to stderr
      with the surrounding excerpt; the host (claude PostToolUse) feeds
      stderr back to the assistant.
  3 — invalid arguments.

Example invocations:
  $ echo '{"tool_name":"Agent","tool_response":{"content":"Shall I merge?"}}' \
      | check-plaintext-approval.py
  $ check-plaintext-approval.py --text "Should I deploy now?"

Forbidden patterns (case-insensitive, anchored to question mark):
  English: Shall I / Should I / Do you want me to / Would you like me to /
           May I / Can I [verb] ... ?
  Korean:  ...할까요? / ...해드릴까요? / ...진행할까요? /
           ...해도 될까요? / ...해도 되나요?

The patterns deliberately require question marks AND modal verbs so
they don't trigger on prose that merely mentions the rule (e.g.,
"the rule forbids 'Shall I merge?'-style prompts" contains a quoted
example but is not itself an approval request — the regex still
matches, accepted false positive).
"""

import argparse
import json
import re
import sys


# --------------------------------------------------------------------------- #
# Forbidden patterns                                                          #
# --------------------------------------------------------------------------- #

# Patterns are case-insensitive (re.IGNORECASE).
# Each pattern captures the offending question and a few words after it
# so the stderr message can quote the exact phrasing.

PATTERNS_EN = [
    # "Shall I <verb> ...?" — most common
    r"\bshall\s+I\s+\w+[^?\n]{0,80}\?",
    # "Should I <verb> ...?"
    r"\bshould\s+I\s+\w+[^?\n]{0,80}\?",
    # "Do you want me to <verb> ...?"
    r"\bdo\s+you\s+want\s+me\s+to\s+\w+[^?\n]{0,80}\?",
    # "Would you like me to <verb> ...?"
    r"\bwould\s+you\s+like\s+me\s+to\s+\w+[^?\n]{0,80}\?",
    # "May I <verb> ...?"
    r"\bmay\s+I\s+\w+[^?\n]{0,80}\?",
    # "Can I <verb> ...?"  (excludes "Can I help" which is greeting-style)
    r"\bcan\s+I\s+(?!help\b)\w+[^?\n]{0,80}\?",
]

PATTERNS_KO = [
    # ...할까요?
    r"[가-힣\w]{1,40}\s*할까요\s*\?",
    # ...해드릴까요?
    r"[가-힣\w]{1,40}\s*해\s*드릴까요\s*\?",
    # ...진행할까요?
    r"[가-힣\w]{1,40}\s*진행할까요\s*\?",
    # ...해도 될까요?
    r"[가-힣\w]{1,40}\s*해도\s*될까요\s*\?",
    # ...해도 되나요?
    r"[가-힣\w]{1,40}\s*해도\s*되나요\s*\?",
]

PATTERNS = [re.compile(p, re.IGNORECASE) for p in PATTERNS_EN + PATTERNS_KO]


# --------------------------------------------------------------------------- #
# Text extraction                                                             #
# --------------------------------------------------------------------------- #

def extract_text(payload):
    """Pull the response text out of a hook payload. Unknown shapes
    return empty string so the caller exits 0 silently."""
    if not isinstance(payload, dict):
        return ""
    resp = payload.get("tool_response")
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        for key in ("content", "text", "message", "output"):
            v = resp.get(key)
            if isinstance(v, str):
                return v
            # Claude tool_response.content can be a list of content blocks.
            if isinstance(v, list):
                parts = []
                for block in v:
                    if isinstance(block, dict):
                        t = block.get("text") or block.get("content")
                        if isinstance(t, str):
                            parts.append(t)
                if parts:
                    return "\n".join(parts)
    return ""


# --------------------------------------------------------------------------- #
# Driver                                                                      #
# --------------------------------------------------------------------------- #

def find_violation(text):
    """Return (pattern_source, match_str) on first hit, else None."""
    for rx in PATTERNS:
        m = rx.search(text)
        if m:
            return rx.pattern, m.group(0)
    return None


def main():
    p = argparse.ArgumentParser(
        description="Forbid free-text approval prompts (Phase G6).")
    p.add_argument("--text",
                   help="diagnostic: pre-extracted text to scan "
                        "(otherwise read from stdin as JSON)")
    p.add_argument("--tool", default="Agent",
                   help="tool_name to filter on when reading from stdin "
                        "(default: Agent; use '*' to scan every payload)")
    args = p.parse_args()

    if args.text is not None:
        text = args.text
    else:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # Not JSON — could be a raw text payload (codex/generic).
            payload = None
            text = raw
        if payload is not None:
            if not isinstance(payload, dict):
                return 0
            if args.tool != "*":
                tool_name = payload.get("tool_name", "")
                if tool_name != args.tool:
                    return 0
            text = extract_text(payload)

    if not text:
        return 0

    hit = find_violation(text)
    if hit is None:
        return 0

    pattern, match_str = hit
    msg = (
        "agent-crew: forbidden plain-text approval prompt detected.\n"
        f"  Match: {match_str.strip()!r}\n"
        f"  Pattern: {pattern}\n"
        "  Rule: core/rules/disambiguation.md — all yes/no questions\n"
        "        MUST use the host's structured-choice surface\n"
        "        (interactive_question capability) or a structured\n"
        "        markdown fallback. Free-text approval prompts like\n"
        "        \"Shall I merge?\" / \"진행할까요?\" violate the rule.\n"
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
