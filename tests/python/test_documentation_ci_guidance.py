"""Regression coverage for documentation as part of continuous integration."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_ddd_skill_treats_docs_as_shared_model_integration():
    text = read("core/agents/skills/domain-driven-design.md")

    assert "Continuous Model Integration" in text
    assert "documentation is part of the shared model" in text
    assert "Ubiquitous Language ledger" in text


def test_agile_xp_ci_rule_requires_documentation_sync():
    text = read("core/agents/skills/agile-xp.md")

    assert "CI integrates code, tests, and documentation" in text
    assert "Documentation synchronization is part of the integration slice" in text
    assert "Done means code, tests, and docs are coherent" in text


def test_planner_requires_documentation_integration_plan():
    text = read("core/agents/skills/pipeline-planning.md")

    assert "Documentation Integration Plan" in text
    assert "doc_impact" in text
    assert "documentation_ci_required" in text


def test_reviewer_rejects_missing_documentation_sync():
    text = read("core/agents/skills/code-review.md")

    assert "Documentation Integration Review" in text
    assert "documentation_ci_missing" in text
    assert "missing documentation synchronization is an IMPORTANT finding" in text


def test_readme_documents_documentation_ci_contract():
    text = read("README.md")

    assert "Documentation CI Contract" in text
    assert "continuous integration of the shared model" in text
    assert "docs are part of the integration evidence" in text
