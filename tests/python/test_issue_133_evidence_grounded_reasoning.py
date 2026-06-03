"""Regression coverage for issue #133 evidence-grounded reasoning guidance."""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

RULE_PATH = REPO_ROOT / "core" / "rules" / "evidence-grounded-reasoning.md"

AGENT_PATHS = [
    REPO_ROOT / "core" / "agents" / "analyst.md",
    REPO_ROOT / "core" / "agents" / "planner.md",
    REPO_ROOT / "core" / "agents" / "reviewer.md",
    REPO_ROOT / "core" / "agents" / "supervisor.md",
]

GUIDANCE_PATHS = [
    REPO_ROOT / "core" / "rules" / "completion-report.md",
    REPO_ROOT / "core" / "rules" / "quality-loop.md",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_provider_neutral_core_rule_requires_first_party_evidence() -> None:
    text = read(RULE_PATH)

    assert "Provider-neutral" in text or "provider-neutral" in text
    assert "first-party evidence" in text
    assert "analysis, judgment, review, and planning outputs" in text
    assert "file:line" in text
    assert "tool-output" in text
    assert "evidence-to-inference-to-conclusion" in text
    assert "Evidence:" in text
    assert "Inference:" in text
    assert "Conclusion:" in text


@pytest.mark.parametrize("path", AGENT_PATHS)
def test_core_analysis_planning_review_agents_wire_reasoning_rule(path: Path) -> None:
    text = read(path)

    assert "core/rules/evidence-grounded-reasoning.md" in text
    assert "first-party evidence" in text
    assert "file:line" in text
    assert "tool-output" in text
    assert "evidence-to-inference-to-conclusion" in text


def test_agent_artifact_templates_require_evidence_inference_conclusion_flow() -> None:
    for path in AGENT_PATHS:
        text = read(path)
        assert "Evidence" in text, f"{path} should mention evidence"
        assert "Inference" in text, f"{path} should mention inference"
        assert "Conclusion" in text, f"{path} should mention conclusion"


@pytest.mark.parametrize("path", GUIDANCE_PATHS)
def test_completion_and_quality_guidance_enforce_reasoning_rule(path: Path) -> None:
    text = read(path)

    assert "core/rules/evidence-grounded-reasoning.md" in text
    assert "first-party evidence" in text
    assert "evidence-to-inference-to-conclusion" in text
