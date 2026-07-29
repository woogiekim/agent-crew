"""Documentation regression checks for memory contract and repo evaluation docs."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_memory_provider_contract_covers_required_surface() -> None:
    text = (REPO_ROOT / "docs" / "memory-provider-contract.md").read_text(encoding="utf-8")
    lowered = text.lower()

    for command in ("memory capture", "memory search", "memory read", "memory gc"):
        assert command in text

    for behavior in ("timeout", "no-backend", "partial capture failure", "score"):
        assert behavior in lowered

    for flag in (
        "AGENT_CREW_MEMORY_RECALL_MODE",
        "AGENT_CREW_MEMORY_FEEDBACK",
        "AGENT_CREW_MEMORY_STRICT",
    ):
        assert flag in text

    for status in ("disabled", "ok", "no_results", "degraded", "unavailable", "timeout", "invalid_json", "incompatible_provider"):
        assert status in text


def test_compatibility_matrix_documents_mnemos_degradation() -> None:
    text = (REPO_ROOT / "docs" / "compatibility-matrix.md").read_text(encoding="utf-8")

    assert "agent-crew" in text
    assert "mnemos" in text
    assert "search --fast --json" in text
    assert "Graceful Degradation" in text
    assert "crew doctor" in text


def test_workspace_evaluation_preserves_memory_boundary() -> None:
    text = (REPO_ROOT / "docs" / "repository-workspace-evaluation.md").read_text(encoding="utf-8")

    assert "Separate repositories" in text
    assert "shared contract package" in text
    assert "Workspace / monorepo" in text
    assert "must not import mnemos code" in text
