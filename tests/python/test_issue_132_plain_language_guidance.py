"""Regression coverage for issue #132 plain-language documentation guidance."""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CORE_GUIDANCE_FILES = [
    REPO_ROOT / "core" / "agents" / "issuer.md",
    REPO_ROOT / "core" / "agents" / "documenter.md",
]

SHIPPED_DOC_TEMPLATE_FILES = [
    REPO_ROOT / "core" / "agents" / "skills" / "templates" / "issuer-plane.md",
    REPO_ROOT
    / "core"
    / "agents"
    / "skills"
    / "templates"
    / "documenter-outline.md",
]

ABSENT_SHIPPED_TEMPLATE = (
    REPO_ROOT / "core" / "agents" / "skills" / "templates" / "issuer-github.md"
)

FORBIDDEN_AUDIENCE_LABELS = (
    "기획자용",
    "기획자 요약",
    "for planners",
    "for designers",
)


@pytest.mark.parametrize("path", CORE_GUIDANCE_FILES + SHIPPED_DOC_TEMPLATE_FILES)
def test_plain_language_guidance_separates_summary_from_developer_details(
    path: Path,
) -> None:
    text = path.read_text(encoding="utf-8")

    assert "Supplementary Writing Guideline" in text
    assert "Plain-language summary first" in text
    assert "Developer details are separate" in text
    assert "No audience-role labels for the plain summary" in text
    assert "구현 메모(개발자용)" in text


@pytest.mark.parametrize("path", CORE_GUIDANCE_FILES + SHIPPED_DOC_TEMPLATE_FILES)
def test_plain_language_guidance_preserves_base_format_authority(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    lowered = " ".join(text.lower().split())

    assert "supplementary" in lowered
    assert "remain authoritative" in lowered or "remains authoritative" in lowered


@pytest.mark.parametrize("path", CORE_GUIDANCE_FILES + SHIPPED_DOC_TEMPLATE_FILES)
def test_recommended_examples_do_not_emit_role_specific_summary_labels(
    path: Path,
) -> None:
    text = path.read_text(encoding="utf-8")
    examples = re.findall(r"```markdown\n(.*?)```", text, flags=re.DOTALL)
    assert examples, f"{path} should include at least one markdown example"

    for example in examples:
        for label in FORBIDDEN_AUDIENCE_LABELS:
            assert label not in example, (
                f"{path} markdown example should not emit role-specific "
                f"plain-summary label {label!r}."
            )


def test_shipped_documentation_seed_templates_scope_is_explicit() -> None:
    """Issue #132 mentions issuer-github, but this repo does not ship it."""
    for path in SHIPPED_DOC_TEMPLATE_FILES:
        assert path.is_file(), f"Expected shipped seed template at {path}"

    assert not ABSENT_SHIPPED_TEMPLATE.exists(), (
        "issuer-github.md is not a shipped seed template in this checkout; "
        "issue #132 should be handled without fabricating this absent path."
    )
