"""Wave C exemplar (#131) — documenter-outline Channel B seed template.

Asserts that `core/agents/skills/templates/documenter-outline.md` exists,
captures the documentation-output knowledge that `documenter.md` already
contains (canonical result.md format, side-car README/CHANGELOG layout,
keepachangelog discipline), and reads as a faithful re-package — not
fabricated Outline-vendor knowledge.

The template is honest about being a seed point: it does NOT invent Outline
API specifics that aren't already in documenter.md. The dispatcher-loadable
contract is the side-car output contract; the Outline-specific surface is
explicitly marked as a seed marker for adopters to extend.
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE = (
    REPO_ROOT
    / "core"
    / "agents"
    / "skills"
    / "templates"
    / "documenter-outline.md"
)
DOCUMENTER_MD = REPO_ROOT / "core" / "agents" / "documenter.md"


@pytest.fixture(scope="module")
def template_text() -> str:
    assert TEMPLATE.is_file(), (
        f"Channel B seed template missing at {TEMPLATE}. "
        "Wave C requires this file to ship."
    )
    return TEMPLATE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC6 — Required frontmatter                                                  #
# --------------------------------------------------------------------------- #


def test_template_has_frontmatter_name(template_text: str) -> None:
    assert "name: documenter-outline" in template_text, (
        "Template frontmatter must declare name: documenter-outline."
    )


def test_template_has_frontmatter_loaded_by(template_text: str) -> None:
    assert "loaded_by: documenter" in template_text, (
        "Template frontmatter must declare loaded_by: documenter."
    )


def test_template_has_frontmatter_axis(template_text: str) -> None:
    assert "axis: outline" in template_text, (
        "Template frontmatter must declare axis: outline (the dispatcher's "
        "resolved <tool> value for this skill)."
    )


def test_template_has_frontmatter_description(template_text: str) -> None:
    # YAML 'description:' must appear in the frontmatter block.
    assert "description:" in template_text.split("---", 2)[1], (
        "Template frontmatter must include a description field."
    )


# --------------------------------------------------------------------------- #
# AC7 — Honest faithfulness disclaimer / seed-point marker                    #
# --------------------------------------------------------------------------- #


def test_template_contains_faithfulness_disclaimer(template_text: str) -> None:
    """Template must explicitly mark itself as a faithful re-package, not invention."""
    lowered = template_text.lower()
    # Accept any of the canonical phrasings ("faithful", "seed point", "not invented",
    # "extension point", "seed template") that make the honesty explicit.
    honesty_markers = [
        "faithful",
        "seed point",
        "seed marker",
        "seed template",
        "not invented",
        "extension point",
    ]
    matched = [m for m in honesty_markers if m in lowered]
    assert matched, (
        "Template must include an explicit faithfulness / seed-point marker — "
        f"none of {honesty_markers!r} were found. The Channel B template MUST "
        "be honest about what it captures verbatim from documenter.md vs what "
        "is a seed surface for the adopter to extend."
    )


def test_template_does_not_fabricate_outline_api_calls(template_text: str) -> None:
    """No invented Outline API specifics (URLs, endpoint paths, auth headers).

    The dispatcher leg loads this skill at runtime; the skill MUST NOT invent
    vendor-specific request shapes that documenter.md never specified. If the
    user wants concrete Outline coverage they extend the seed; the framework
    refuses to ship fabricated specifics.
    """
    forbidden_fabrications = [
        "api.outline.com",  # invented base URL
        "/api/documents.create",  # invented endpoint path
        "Bearer ol_",  # invented auth token prefix
    ]
    for marker in forbidden_fabrications:
        assert marker not in template_text, (
            f"Template contains fabricated Outline-vendor specific {marker!r} — "
            "Channel B content must be FAITHFUL to documenter.md. Add the "
            "specifics yourself in your user-layer skill copy."
        )


# --------------------------------------------------------------------------- #
# Faithfulness — load-bearing content must trace back to documenter.md        #
# --------------------------------------------------------------------------- #


def test_template_references_result_md_default_output(template_text: str) -> None:
    """The default-output contract (result.md) is the load-bearing faithful content."""
    assert "result.md" in template_text, (
        "Template must document {TASK_DIR}/result.md as the canonical "
        "documenter output (verbatim from documenter.md's Output Contract)."
    )


def test_template_references_side_car_artifacts(template_text: str) -> None:
    """Side-car README/CHANGELOG artifacts must be documented (faithful to documenter.md)."""
    lowered = template_text.lower()
    assert ("readme" in lowered) and ("changelog" in lowered), (
        "Template must document the side-car README/CHANGELOG artifacts that "
        "documenter.md produces (verbatim from the Output Contract table)."
    )


@pytest.mark.parametrize(
    "phrase",
    [
        "result.md",
        "side-car",
        "README",
        "CHANGELOG",
    ],
)
def test_template_phrases_trace_to_documenter_md(
    phrase: str,
    template_text: str,
) -> None:
    """Faithful re-package: load-bearing phrases must also appear in documenter.md."""
    documenter_text = DOCUMENTER_MD.read_text(encoding="utf-8")
    assert phrase in template_text, f"Template missing {phrase!r}"
    assert phrase in documenter_text, (
        f"Template uses {phrase!r} but documenter.md does not — Channel B "
        "template content must be a faithful re-package of documenter.md, "
        "not invention."
    )


# --------------------------------------------------------------------------- #
# Honesty about the seed point — Outline-specific surface is marked          #
# --------------------------------------------------------------------------- #


def test_template_marks_outline_surface_as_seed_point(template_text: str) -> None:
    """The Outline-specific surface MUST be flagged as a seed point for adopters."""
    lowered = template_text.lower()
    # The template should explicitly mention Outline somewhere (the skill IS
    # for the outline axis) AND mark the Outline-specific surface as a seed
    # marker so adopters don't mistake placeholder text for vendor specifics.
    assert "outline" in lowered, (
        "Template must mention Outline (the resolved <tool> value)."
    )
    has_seed_marker = (
        "seed point" in lowered
        or "seed marker" in lowered
        or "extension point" in lowered
        or "fill this in" in lowered
        or "extend this skill" in lowered
        or "adopter" in lowered
    )
    assert has_seed_marker, (
        "Template must explicitly mark the Outline-specific surface as a "
        "seed point so adopters know what to extend (and what was already "
        "faithful coverage of documenter.md)."
    )


# --------------------------------------------------------------------------- #
# Naming convention check                                                     #
# --------------------------------------------------------------------------- #


def test_template_file_lives_at_templates_dir() -> None:
    """Channel B templates live at core/agents/skills/templates/ (flat layout)."""
    assert TEMPLATE.parent.name == "templates"
    assert TEMPLATE.parent.parent.name == "skills"
    assert TEMPLATE.name == "documenter-outline.md"
