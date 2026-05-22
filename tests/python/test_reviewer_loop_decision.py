"""Tests for reviewer response loop-back classification."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "reviewer-loop-decision.py"


def run_decision(text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--format", "json"],
        input=text,
        text=True,
        capture_output=True,
    )


def test_status_rejected_triggers_retry_with_reason():
    result = run_decision(
        "STATUS: REJECTED\n"
        "REASON: tests_failed\n"
        "DETAIL: pytest failed\n"
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry"
    assert payload["reason"] == "tests_failed"
    assert "failing tests" in payload["directive"]


def test_review_needs_changes_triggers_retry():
    result = run_decision(
        "REVIEW: NEEDS_CHANGES\n"
        "REPORT: context/review.md\n"
        "ISSUES: 2\n"
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry"
    assert payload["trigger"] == "REVIEW: NEEDS_CHANGES"
    assert payload["reason"] == "review_needs_changes"
    assert payload["issues"] == 2
    assert "re-run reviewer" in payload["directive"]


def test_review_approved_does_not_retry():
    result = run_decision(
        "REVIEW: APPROVED\n"
        "REPORT: context/review.md\n"
        "ISSUES: 0\n"
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "approve"


def test_supervisor_docs_treat_needs_changes_as_loop_trigger():
    retry_doc = (REPO_ROOT / "core" / "agents" / "supervisor-retry.md").read_text(encoding="utf-8")
    quality_doc = (REPO_ROOT / "core" / "rules" / "quality-loop.md").read_text(encoding="utf-8")
    reviewer_doc = (REPO_ROOT / "core" / "agents" / "reviewer.md").read_text(encoding="utf-8")

    assert "REVIEW: NEEDS_CHANGES` return (a soft advisory" not in retry_doc
    assert "does\n-NOT trigger" not in retry_doc
    assert "`REVIEW: NEEDS_CHANGES`" in retry_doc
    assert "action=retry" in retry_doc
    assert "REVIEW: NEEDS_CHANGES` | Static or streaming review" in quality_doc
    assert "`REVIEW: NEEDS_CHANGES` is a loop-triggering rejection" in reviewer_doc
