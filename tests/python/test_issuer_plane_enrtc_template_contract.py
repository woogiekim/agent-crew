"""Regression coverage for ENRTC Plane issue template defaults."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUER_PLANE_TEMPLATE = (
    REPO_ROOT / "core" / "agents" / "skills" / "templates" / "issuer-plane.md"
)


def _template_text() -> str:
    return ISSUER_PLANE_TEMPLATE.read_text(encoding="utf-8")


def test_enrtc_uses_local_default_template_without_runtime_template_fetch() -> None:
    text = _template_text()
    step_06 = text.split("## Step 0.6", 1)[1].split("## Supplementary", 1)[0]

    assert "ENRTC default issue template" in step_06
    assert "local canonical ENRTC template" in step_06
    assert "MUST fetch" not in step_06
    assert "mcp__plane__retrieve_work_item_by_identifier" not in step_06
    assert "fallback skeleton" not in step_06.lower()
    assert "ENRTC-1 remains the source of truth" not in step_06


def test_enrtc_template_preserves_implementation_ready_fields() -> None:
    text = _template_text()

    required_fields = [
        "Background",
        "Current Behavior",
        "Target Behavior",
        "Scope",
        "Out of Scope",
        "Implementation Notes",
        "Contract / Parity",
        "Test Plan",
        "Rollout / Rollback",
        "Open Questions",
    ]

    for field in required_fields:
        assert field in text

    implementation_ready_markers = [
        "implementation readiness",
        "purpose",
        "implementation scope",
        "expected behavior",
        "test plan",
        "Unknown",
        "MISSING",
    ]

    lowered = text.lower()
    for marker in implementation_ready_markers:
        assert marker.lower() in lowered


def test_enrtc_template_guides_branch_naming_by_commit_convention() -> None:
    text = _template_text()
    lowered = text.lower()

    assert "Branch / Commit Convention" in text
    assert "{type}/{issue-key}-{short-slug}" in text
    assert "branch type" in lowered
    assert "branch name" in lowered
    assert "MISSING" in text

    for commit_type in ("feat", "fix", "chore", "docs", "test", "refactor"):
        assert f"`{commit_type}`" in text

    for parsed_field in ("branch_type", "branch_name"):
        assert parsed_field in text
