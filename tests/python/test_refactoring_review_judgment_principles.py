"""Regression coverage for agnostic refactoring and review judgment rules."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CODE_QUALITY = REPO_ROOT / "core" / "rules" / "code-quality.md"
REFACTORING_CATALOG = REPO_ROOT / "core" / "agents" / "skills" / "refactoring-catalog.md"
CODE_REVIEW = REPO_ROOT / "core" / "agents" / "skills" / "code-review.md"

PROJECT_SPECIFIC_TOKENS = (
    "ENRTC",
    "CMS",
    "CNAS",
    "Danawa",
    "NewsBot",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def compact(path: Path) -> str:
    return " ".join(read(path).split())


def test_code_quality_prefers_domain_concepts_over_raw_values() -> None:
    text = compact(CODE_QUALITY)

    for required in (
        "Prefer domain concepts over raw-value comparisons",
        "Convert external input, persisted values, and API response values",
        "policy decision",
        "meaningful type, value object, enum, or named concept",
        "Do not compare raw strings, numbers, booleans, or nulls",
    ):
        assert required in text


def test_code_quality_separates_failure_absence_and_presence() -> None:
    text = compact(CODE_QUALITY)

    for required in (
        "Model failure, absence, and valid presence as distinct states",
        "Failure is not an empty result",
        "empty result",
        "valid result",
        "policy outcome",
    ):
        assert required in text


def test_refactoring_catalog_defines_intent_preserving_refactor_hygiene() -> None:
    text = read(REFACTORING_CATALOG)

    for required in (
        "Refactoring should reveal intent, not merely shorten code",
        "Use functional pipelines only when they separate transformation from decision",
        "Remove comments that no longer match the current contract",
        "Keep diffs reviewable by limiting them to the smallest meaningful change",
        "format churn",
    ):
        assert required in text


def test_code_review_reaches_refactoring_principles_through_existing_wiring() -> None:
    text = read(CODE_REVIEW)

    assert "core/rules/code-quality.md" in text
    assert "refactoring-catalog.md" in text


def test_refactoring_principles_are_not_project_specific() -> None:
    combined = "\n".join([read(CODE_QUALITY), read(REFACTORING_CATALOG)])

    for token in PROJECT_SPECIFIC_TOKENS:
        assert token not in combined
