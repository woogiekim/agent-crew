"""Regression coverage for provider-agnostic code intelligence evidence."""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULE = REPO_ROOT / "core" / "rules" / "code-intelligence-evidence.md"
BACKEND = REPO_ROOT / "core" / "agents" / "backend.md"
FRONTEND = REPO_ROOT / "core" / "agents" / "frontend.md"
REVIEWER = REPO_ROOT / "core" / "agents" / "reviewer.md"
DISPATCH_RULE = REPO_ROOT / "core" / "rules" / "agent-tool-dispatch.md"


@pytest.fixture(scope="module")
def rule_text() -> str:
    assert RULE.is_file(), f"code intelligence evidence rule missing at {RULE}"
    return RULE.read_text(encoding="utf-8")


def test_rule_defines_language_and_provider_agnostic_contract(rule_text: str) -> None:
    required_terms = (
        "language-agnostic",
        "provider-agnostic",
        "semantic evidence provider",
        "queried_symbols",
        "diagnostics_before",
        "diagnostics_after",
        "unsupported_capabilities",
        "fallback-static",
    )

    for term in required_terms:
        assert term in rule_text


def test_rule_treats_typescript_lsp_as_example_not_canonical_gate(rule_text: str) -> None:
    assert "TypeScript LSP" in rule_text
    assert "one provider example" in rule_text
    assert "MUST NOT name the generic gate after TypeScript" in rule_text


def test_dispatch_rule_documents_semantic_provider_adapter_boundary() -> None:
    text = DISPATCH_RULE.read_text(encoding="utf-8")

    assert "Semantic evidence provider dispatch" in text
    assert "code-intelligence-evidence.md" in text
    assert "semantic evidence provider" in text


@pytest.mark.parametrize("agent_path", [BACKEND, FRONTEND])
def test_implementation_agents_require_semantic_evidence_before_code_edits(
    agent_path: Path,
) -> None:
    text = agent_path.read_text(encoding="utf-8")

    assert "core/rules/code-intelligence-evidence.md" in text
    assert "context/code-intelligence-evidence.json" in text
    assert "before modifying production code" in text


def test_reviewer_enforces_semantic_evidence_for_code_changes() -> None:
    text = REVIEWER.read_text(encoding="utf-8")

    assert "core/rules/code-intelligence-evidence.md" in text
    assert "context/code-intelligence-evidence.json" in text
    assert "NEEDS_CHANGES" in text
