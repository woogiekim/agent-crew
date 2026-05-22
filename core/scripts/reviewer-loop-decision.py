#!/usr/bin/env python3
"""Classify reviewer output for supervisor quality-loop routing.

Inputs:
  --response FILE     Reviewer output file. When omitted, read stdin.
  --format text|json  Output format.

Outputs:
  json: {"action": "approve|retry|none", "reason": "...", "directive": "..."}
  text: ACTION/REASON/DIRECTIVE lines.

Exit codes:
  0 - reviewer approved or no loop action needed
  1 - reviewer requested implementer retry
  2 - invalid arguments or unreadable response file
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


STATUS_REJECTED_RE = re.compile(r"^STATUS\s*:\s*REJECTED\b", re.I | re.M)
REVIEW_NEEDS_CHANGES_RE = re.compile(r"^REVIEW\s*:\s*NEEDS_CHANGES\b", re.I | re.M)
REVIEW_APPROVED_RE = re.compile(r"^REVIEW\s*:\s*APPROVED\b", re.I | re.M)
REASON_RE = re.compile(r"^REASON\s*:\s*([a-zA-Z0-9_.:-]+)", re.I | re.M)
ISSUES_RE = re.compile(r"^ISSUES\s*:\s*(\d+)", re.I | re.M)
REPORT_RE = re.compile(r"^REPORT\s*:\s*(.+)$", re.I | re.M)


DIRECTIVES = {
    "tests_failed": (
        "Tests failed in the previous review. Fix the failing tests reported "
        "in ${TASK_DIR}/context/review-tests.md. Do not skip or comment out "
        "the failing assertions."
    ),
    "tests_absent_for_code_change": (
        "Reviewer detected a code change with no discoverable test runner. "
        "Add a test runner config and tests covering the changed behavior, "
        "or have the planner justify requires_test_execution=false for a "
        "non-code stage."
    ),
    "cross_process_path_mismatch": (
        "Reviewer detected a path-literal mismatch across the shell/Python "
        "boundary. Make both sides resolve to the same path."
    ),
    "review_needs_changes": (
        "Reviewer requested changes in ${TASK_DIR}/context/review.md. Return "
        "to the most recent implementer/TDD stage, remediate every listed "
        "issue, run the relevant tests, and then re-run reviewer."
    ),
}


def read_response(path: str | None) -> tuple[str, str | None]:
    if not path:
        return sys.stdin.read(), None
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace"), None
    except Exception as exc:
        return "", f"reviewer-loop-decision: cannot read response: {exc}"


def report_path(text: str) -> str:
    match = REPORT_RE.search(text)
    return match.group(1).strip() if match else "${TASK_DIR}/context/review.md"


def classify(text: str) -> dict:
    if STATUS_REJECTED_RE.search(text):
        reason_match = REASON_RE.search(text)
        reason = reason_match.group(1) if reason_match else "reviewer_rejected"
        return {
            "action": "retry",
            "trigger": "STATUS: REJECTED",
            "reason": reason,
            "directive": DIRECTIVES.get(reason, DIRECTIVES["review_needs_changes"]),
        }

    if REVIEW_NEEDS_CHANGES_RE.search(text):
        issues_match = ISSUES_RE.search(text)
        issues = int(issues_match.group(1)) if issues_match else None
        report = report_path(text)
        directive = DIRECTIVES["review_needs_changes"].replace(
            "${TASK_DIR}/context/review.md",
            report,
        )
        return {
            "action": "retry",
            "trigger": "REVIEW: NEEDS_CHANGES",
            "reason": "review_needs_changes",
            "directive": directive,
            "issues": issues,
            "report": report,
        }

    if REVIEW_APPROVED_RE.search(text):
        return {
            "action": "approve",
            "trigger": "REVIEW: APPROVED",
            "reason": "review_approved",
            "directive": "",
        }

    return {
        "action": "none",
        "trigger": "",
        "reason": "no_review_verdict",
        "directive": "",
    }


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
        if result.get("directive"):
            print(f"DIRECTIVE: {result['directive']}")
    return 1 if result["action"] == "retry" else 0


if __name__ == "__main__":
    raise SystemExit(main())
