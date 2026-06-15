"""Tests for implementer response clarification classification.

Spec: prd.md § AC5 (classifier helper) and § AC6 (tests).
SUT: core/scripts/implementer-clarification-check.py

The helper recognizes a new STATUS: needs_clarification return path from
implementer agents (backend / frontend / generic implementers) and emits
the routing verdict the supervisor acts on, in JSON shape:

  {"action": "clarify" | "completed" | "blocked" | "none",
   "request": "...", "detail_path": "..."}

It MUST NOT misclassify STATUS: completed or STATUS: BLOCKED as
needs_clarification, and the STATUS line MUST be at start of line
(mirrors reviewer-loop-decision.py's STATUS_REJECTED_RE shape).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "implementer-clarification-check.py"


def run_check(text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", str(SCRIPT), "--format", "json"],
        input=text,
        text=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# AC6 case 1: needs_clarification with CLARIFICATION_REQUEST -> action=clarify
# ---------------------------------------------------------------------------


def test_needs_clarification_with_request_and_detail_classifies_as_clarify():
    """Spec: prd.md § AC4 — needs_clarification return-block shape."""
    response = (
        "STATUS: needs_clarification\n"
        "CLARIFICATION_REQUEST: PRD ambiguous on acceptance criterion AC2 wording.\n"
        "CLARIFICATION_DETAIL: context/clarification-request.md\n"
    )

    result = run_check(response)

    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "clarify"
    assert "AC2" in payload["request"]
    assert payload["detail_path"] == "context/clarification-request.md"


def test_needs_clarification_with_request_only_has_empty_detail_path():
    """When no CLARIFICATION_DETAIL line is present, detail_path is empty."""
    response = (
        "STATUS: needs_clarification\n"
        "CLARIFICATION_REQUEST: Which auth provider should the endpoint use?\n"
    )

    result = run_check(response)

    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "clarify"
    assert "auth provider" in payload["request"]
    assert payload["detail_path"] == ""


# ---------------------------------------------------------------------------
# AC6 case 2: needs_clarification WITHOUT CLARIFICATION_REQUEST -> blocked
# ---------------------------------------------------------------------------


def test_needs_clarification_without_request_is_malformed_blocked():
    """Spec: prd.md § AC4 — CLARIFICATION_REQUEST is required."""
    response = (
        "STATUS: needs_clarification\n"
        "CLARIFICATION_DETAIL: context/clarification-request.md\n"
    )

    result = run_check(response)

    payload = json.loads(result.stdout)
    assert payload["action"] == "blocked"
    assert payload["reason"] == "needs_clarification_malformed"


def test_needs_clarification_with_blank_request_is_malformed_blocked():
    """A CLARIFICATION_REQUEST: line with empty value is still malformed."""
    response = (
        "STATUS: needs_clarification\n"
        "CLARIFICATION_REQUEST:   \n"
    )

    result = run_check(response)

    payload = json.loads(result.stdout)
    assert payload["action"] == "blocked"
    assert payload["reason"] == "needs_clarification_malformed"


# ---------------------------------------------------------------------------
# AC6 case 3: STATUS: completed must NOT be classified as clarify
# ---------------------------------------------------------------------------


def test_status_completed_is_not_clarify():
    """Spec: prd.md § AC5 collision guard — completed never maps to clarify."""
    response = (
        "STATUS: completed\n"
        "ITERATIONS: 1\n"
        "ARTIFACTS: src/foo.py\n"
        "VERIFIED: tests=3/3 cmd=pytest exit=0\n"
    )

    result = run_check(response)

    payload = json.loads(result.stdout)
    assert payload["action"] != "clarify"
    assert payload["action"] in {"completed", "none"}


# ---------------------------------------------------------------------------
# AC6 case 4: STATUS: BLOCKED must NOT be classified as clarify
# ---------------------------------------------------------------------------


def test_status_blocked_is_not_clarify():
    """Spec: prd.md § AC5 collision guard — BLOCKED never maps to clarify."""
    response = (
        "STATUS: BLOCKED\n"
        "BLOCKER: cannot reach upstream service\n"
    )

    result = run_check(response)

    payload = json.loads(result.stdout)
    assert payload["action"] != "clarify"
    assert payload["action"] == "blocked"


# ---------------------------------------------------------------------------
# AC6 case 5: empty / no-STATUS input is a non-clarify outcome
# ---------------------------------------------------------------------------


def test_empty_input_is_not_clarify():
    """No STATUS line at all is the supervisor's crash path, not this helper."""
    result = run_check("")

    payload = json.loads(result.stdout)
    assert payload["action"] != "clarify"
    assert payload["action"] in {"none", "blocked"}


def test_no_status_line_input_is_not_clarify():
    """Plain prose without any STATUS line is not a clarify case."""
    response = "Some narrative text without any STATUS line.\nMore prose here.\n"

    result = run_check(response)

    payload = json.loads(result.stdout)
    assert payload["action"] != "clarify"
    assert payload["action"] in {"none", "blocked"}


# ---------------------------------------------------------------------------
# AC6 case 6: substring 'needs_clarification' off a STATUS line is NOT clarify
# ---------------------------------------------------------------------------


def test_needs_clarification_substring_not_in_status_line_is_not_clarify():
    """Mirrors reviewer-loop-decision.py: STATUS verdicts must be at line-start."""
    response = (
        "Notes: we briefly considered needs_clarification but resolved it.\n"
        "STATUS: completed\n"
        "VERIFIED: tests=1/1 cmd=pytest exit=0\n"
    )

    result = run_check(response)

    payload = json.loads(result.stdout)
    assert payload["action"] != "clarify"


def test_needs_clarification_in_indented_text_is_not_clarify():
    """An indented line is not at line-start, so it is not a STATUS verdict."""
    response = (
        "    STATUS: needs_clarification\n"
        "    CLARIFICATION_REQUEST: was this a real verdict?\n"
    )

    result = run_check(response)

    payload = json.loads(result.stdout)
    assert payload["action"] != "clarify"
