"""Wave B exemplar (#131) — backend-kotlin-spring Channel B seed template.

Asserts that `core/agents/skills/templates/backend-kotlin-spring.md` exists,
captures the Kotlin/Spring Boot + TDD/DDD knowledge that `backend.md`
previously embedded, and reads as a faithful re-packaging — not invention.
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
    / "backend-kotlin-spring.md"
)
BACKEND_MD = REPO_ROOT / "core" / "agents" / "backend.md"


@pytest.fixture(scope="module")
def template_text() -> str:
    assert TEMPLATE.is_file(), (
        f"Channel B seed template missing at {TEMPLATE}. "
        "Wave B requires this file to ship."
    )
    return TEMPLATE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Tech stack — Kotlin / Spring Boot / JUnit 5 / MockK / Gradle                #
# --------------------------------------------------------------------------- #


def test_template_contains_kotlin_language(template_text: str) -> None:
    assert "Kotlin" in template_text


def test_template_contains_spring_boot_framework(template_text: str) -> None:
    assert "Spring Boot" in template_text


def test_template_contains_junit_test_runner(template_text: str) -> None:
    assert "JUnit" in template_text


def test_template_contains_mockk(template_text: str) -> None:
    assert "MockK" in template_text


def test_template_contains_gradle_build_tool(template_text: str) -> None:
    assert "Gradle" in template_text or "gradle" in template_text


# --------------------------------------------------------------------------- #
# TDD cycle — RED -> GREEN -> REFACTOR with ./gradlew test                    #
# --------------------------------------------------------------------------- #


def test_template_contains_red_green_refactor_cycle(template_text: str) -> None:
    upper = template_text.upper()
    for marker in ("RED", "GREEN", "REFACTOR"):
        assert marker in upper, (
            f"Template must document the {marker} step of the TDD cycle "
            "(verbatim from backend.md Phase 2)."
        )


def test_template_contains_gradle_test_invocation(template_text: str) -> None:
    assert "./gradlew test" in template_text, (
        "Template must document the ./gradlew test invocation that backs "
        "each RED -> GREEN -> REFACTOR step (verbatim from backend.md)."
    )


# --------------------------------------------------------------------------- #
# Test file naming convention                                                 #
# --------------------------------------------------------------------------- #


def test_template_contains_unit_test_naming(template_text: str) -> None:
    assert "Test.kt" in template_text


def test_template_contains_integration_test_naming(template_text: str) -> None:
    assert "IntegrationTest.kt" in template_text


def test_template_contains_sut_default(template_text: str) -> None:
    lowered = template_text.lower()
    assert "sut" in lowered, (
        "Template must document the `sut` default test-target naming convention."
    )


# --------------------------------------------------------------------------- #
# DDD tactical patterns                                                       #
# --------------------------------------------------------------------------- #


def test_template_contains_aggregate_root(template_text: str) -> None:
    assert "Aggregate Root" in template_text or "aggregate root" in template_text.lower()


def test_template_contains_value_object(template_text: str) -> None:
    assert "Value Object" in template_text or "value object" in template_text.lower()


def test_template_contains_domain_event(template_text: str) -> None:
    assert "Domain Event" in template_text or "domain event" in template_text.lower()


# --------------------------------------------------------------------------- #
# Coverage gate — 100% changed executable coverage                            #
# --------------------------------------------------------------------------- #


def test_template_contains_coverage_gate(template_text: str) -> None:
    lower = template_text.lower()
    assert "100%" in template_text and "coverage" in lower, (
        "Template must document the 100% changed executable coverage gate."
    )


# --------------------------------------------------------------------------- #
# Object Calisthenics + Tell, Don't Ask reference                             #
# --------------------------------------------------------------------------- #


def test_template_references_object_calisthenics(template_text: str) -> None:
    assert (
        "Object Calisthenics" in template_text
        or "object calisthenics" in template_text.lower()
    )


def test_template_references_no_else_rule(template_text: str) -> None:
    # backend.md uses "No `else` keyword" — the template uses the same phrase
    # but bolded as "**No `else`**". Accept both.
    lower = template_text.lower()
    assert (
        "no `else`" in lower  # case-insensitive: matches "No `else`"
        or "no else" in lower
    ), "Template must document the 'No `else`' Object Calisthenics rule."


# --------------------------------------------------------------------------- #
# "Faithful — not invented" check                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "phrase",
    [
        "Kotlin",
        "Spring Boot",
        "JUnit",
        "MockK",
        "Gradle",
        "./gradlew test",
    ],
)
def test_template_phrases_trace_to_backend_md(phrase: str, template_text: str) -> None:
    """A faithful re-package must trace its load-bearing phrases back to backend.md."""
    backend_text = BACKEND_MD.read_text(encoding="utf-8")
    assert phrase in template_text, f"Template missing {phrase!r}"
    assert phrase in backend_text, (
        f"Template uses {phrase!r} but backend.md does not — Channel B template "
        "content must be a faithful re-package of backend.md, not invention."
    )


# --------------------------------------------------------------------------- #
# Naming convention check                                                     #
# --------------------------------------------------------------------------- #


def test_template_file_lives_at_templates_dir() -> None:
    """Channel B templates live at core/agents/skills/templates/ (flat layout)."""
    assert TEMPLATE.parent.name == "templates"
    assert TEMPLATE.parent.parent.name == "skills"
    assert TEMPLATE.name == "backend-kotlin-spring.md"
