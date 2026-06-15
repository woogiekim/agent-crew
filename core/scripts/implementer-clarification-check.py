#!/usr/bin/env python3
"""Classify implementer output for supervisor clarification routing.

Inputs:
  --response FILE     Implementer output file. When omitted, read stdin.
  --format text|json  Output format.

Outputs:
  json: {"action": "clarify|completed|blocked|none",
         "reason": "...",
         "request": "...",
         "detail_path": "..."}
  text: ACTION/REASON/REQUEST lines (REQUEST omitted when empty).

Exit codes:
  0 - completed or none (no clarify action needed)
  1 - clarify (supervisor should route to analyst)
  2 - blocked (any blocked variant) or invalid args / unreadable file

Decision precedence (each excludes the rest):
  1. STATUS: needs_clarification with non-empty CLARIFICATION_REQUEST
     -> action=clarify
  2. STATUS: needs_clarification without (or with empty) CLARIFICATION_REQUEST
     -> action=blocked, reason=needs_clarification_malformed
  3. STATUS: BLOCKED -> action=blocked, reason=agent_blocked
  4. STATUS: completed -> action=completed
  5. neither -> action=none, reason=no_status

The STATUS line MUST be at the start of a physical line (mirrors
reviewer-loop-decision.py's STATUS_REJECTED_RE convention) -- an indented
or substring occurrence is NOT a STATUS verdict.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


STATUS_NEEDS_CLARIFICATION_RE = re.compile(
    r"^STATUS\s*:\s*needs_clarification\b", re.M
)
STATUS_COMPLETED_RE = re.compile(r"^STATUS\s*:\s*completed\b", re.M)
STATUS_BLOCKED_RE = re.compile(r"^STATUS\s*:\s*BLOCKED\b", re.I | re.M)
CLARIFICATION_REQUEST_RE = re.compile(
    r"^CLARIFICATION_REQUEST\s*:\s*(.+)$", re.M
)
CLARIFICATION_DETAIL_RE = re.compile(
    r"^CLARIFICATION_DETAIL\s*:\s*(.+)$", re.M
)


def read_response(path: str | None) -> tuple[str, str | None]:
    if not path:
        return sys.stdin.read(), None
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace"), None
    except Exception as exc:
        return "", f"implementer-clarification-check: cannot read response: {exc}"


def _extract(regex: "re.Pattern[str]", text: str) -> str:
    match = regex.search(text)
    if not match:
        return ""

    return match.group(1).strip()


def classify(text: str) -> dict:
    if STATUS_NEEDS_CLARIFICATION_RE.search(text):
        request = _extract(CLARIFICATION_REQUEST_RE, text)
        detail = _extract(CLARIFICATION_DETAIL_RE, text)
        if request:
            return {
                "action": "clarify",
                "reason": "",
                "request": request,
                "detail_path": detail,
            }

        return {
            "action": "blocked",
            "reason": "needs_clarification_malformed",
            "request": "",
            "detail_path": "",
        }

    if STATUS_BLOCKED_RE.search(text):
        return {
            "action": "blocked",
            "reason": "agent_blocked",
            "request": "",
            "detail_path": "",
        }

    if STATUS_COMPLETED_RE.search(text):
        return {
            "action": "completed",
            "reason": "",
            "request": "",
            "detail_path": "",
        }

    return {
        "action": "none",
        "reason": "no_status",
        "request": "",
        "detail_path": "",
    }


def _exit_code(action: str) -> int:
    if action == "clarify":
        return 1
    if action == "blocked":
        return 2

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    text, error = read_response(args.response)
    if error:
        print(error, file=sys.stderr)
        return 2

    result = classify(text)

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"ACTION: {result['action']}")
        print(f"REASON: {result['reason']}")
        if result.get("request"):
            print(f"REQUEST: {result['request']}")

    return _exit_code(result["action"])


if __name__ == "__main__":
    raise SystemExit(main())
