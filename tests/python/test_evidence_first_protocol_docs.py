"""Issue #193: bug reports and analysis must separate evidence from hypotheses."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_evidence_grounded_rule_defines_bug_report_protocol() -> None:
    text = read("core/rules/evidence-grounded-reasoning.md")

    assert "Evidence-First Verification Protocol" in text
    assert "Bug reports, incident analysis, and root-cause reports" in text
    assert "Proven Facts" in text
    assert "Unverified Hypotheses" in text
    assert "Needed Evidence" in text
    assert "Conclusion" in text


def test_evidence_grounded_rule_keeps_hypotheses_out_of_conclusions() -> None:
    text = read("core/rules/evidence-grounded-reasoning.md")
    normalized = " ".join(text.split())

    assert "Do not put an unverified hypothesis in Conclusion" in normalized
    assert "If the report cannot collect required evidence" in normalized


def test_code_review_skill_checks_evidence_first_reporting() -> None:
    text = read("core/agents/skills/code-review.md")

    assert "Evidence-first reporting" in text
    assert "Proven Facts" in text
    assert "Unverified Hypotheses" in text
    assert "Needed Evidence" in text
