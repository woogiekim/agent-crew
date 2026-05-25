"""Coverage ownership contract documentation tests."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_quality_loop_names_coverage_owners_and_rejection_reasons():
    text = read("core/rules/quality-loop.md")

    assert "100% Test Coverage Ownership" in text
    assert "**Test-writer** owns coverage planning and test creation" in text
    assert "**Implementation agents**" in text
    assert "**Reviewer** owns enforcement" in text
    assert "coverage_below_100" in text
    assert "missing_coverage_evidence" in text
    assert "coverage_exception_unjustified" in text


def test_agent_contracts_define_coverage_evidence_and_enforcement():
    test_writer = read("core/agents/test-writer.md")
    reviewer = read("core/agents/reviewer.md")
    backend = read("core/agents/backend.md")
    frontend = read("core/agents/frontend.md")
    planner = read("core/agents/planner.md")

    assert "context/test-coverage.md" in test_writer
    assert "Coverage target: 100% changed-surface coverage" in test_writer
    assert "COVERAGE: 100% changed-surface coverage" in test_writer
    assert "Phase 1.6" in reviewer
    assert "COVERAGE_RESULT" in reviewer
    assert "100% changed-surface test coverage" in planner
    assert "100% changed executable coverage" in backend
    assert "100% changed executable coverage" in frontend
