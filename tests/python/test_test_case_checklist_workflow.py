"""Domain-behavior test checklist workflow contract tests."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


REQUIRED_FIELDS = (
    "TC-ID",
    "Category",
    "Given",
    "When",
    "Then",
    "Priority",
    "MUST / SHOULD / SUGGESTION",
    "Reason",
)

REQUIRED_CATEGORIES = (
    "Normal",
    "Exception",
    "Boundary",
    "Validation",
    "State Transition",
    "Authorization",
    "Ownership",
    "Idempotency",
    "Duplicate Request",
    "Concurrency",
    "Persistence Side Effect",
    "Domain Event",
    "External Dependency Failure",
    "Regression",
)


def read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_test_writer_requires_checklist_review_before_test_code() -> None:
    text = read("core/agents/test-writer.md")

    assert "requirements analysis -> test checklist derivation -> checklist-only review -> test code generation -> TC-ID mapping verification" in text
    assert "context/test-checklist.md" in text
    assert "context/test-checklist-review.md" in text
    assert "context/test-case-mapping.md" in text
    assert "Do not write test code before checklist review is APPROVED" in text
    assert "TC-ID" in text

    for field in REQUIRED_FIELDS:
        assert field in text

    for category in REQUIRED_CATEGORIES:
        assert category in text

    assert "N/A" in text


def test_checklist_preflight_is_non_blocking_supervisor_transition() -> None:
    test_writer = read("core/agents/test-writer.md")
    supervisor = read("core/agents/supervisor-stages.md")

    assert "CHECKLIST_REVIEW_REQUIRED: true" in test_writer
    assert "STATUS: completed" in test_writer
    assert "STATUS: BLOCKED\nBLOCKER: checklist_review_required" not in test_writer
    assert "CHECKLIST_REVIEW_REQUIRED: true" in supervisor
    assert "non-terminal checklist handoff" in supervisor
    assert "Do not apply the generic `STATUS: BLOCKED` terminal rule" in supervisor


def test_tdd_skill_defines_domain_behavior_checklist_gate() -> None:
    text = read("core/agents/skills/tdd.md")

    assert "Domain Behavior Checklist Gate" in text
    assert "TC-ID" in text
    assert "domain behavior coverage" in text
    assert "Line coverage is not sufficient" in text

    for field in REQUIRED_FIELDS:
        assert field in text

    for category in REQUIRED_CATEGORIES:
        assert category in text


def test_reviewer_prioritizes_missing_domain_behavior_in_test_checklist_review() -> None:
    text = read("core/agents/reviewer.md")

    assert "checklist-only review" in text
    assert "Missing MUST" in text
    assert "Missing SHOULD" in text
    assert "Duplicate" in text
    assert "Low-value Test" in text
    assert "Wrong Priority" in text
    assert "domain behavior coverage" in text
    assert "Line coverage is not sufficient" in text
    assert "style findings come after missing domain behavior" in text


def test_quality_loop_documents_test_case_mapping_completion_conditions() -> None:
    text = read("core/rules/quality-loop.md")

    assert "Test Case Checklist Workflow" in text
    assert "context/test-checklist.md" in text
    assert "context/test-checklist-review.md" in text
    assert "context/test-case-mapping.md" in text
    assert "Reviewer APPROVED" in text
    assert "all MUST checklist items are implemented or explicitly explained" in text
    assert "Missing MUST" in text
