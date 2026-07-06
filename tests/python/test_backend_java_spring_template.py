"""backend-java-spring Channel B seed template contract.

Asserts that `core/agents/skills/templates/backend-java-spring.md` exists and
captures the Java/Spring Boot + Maven/JUnit/Mockito stack contract needed by the
backend dispatcher when it resolves the `java-spring` axis.
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
    / "backend-java-spring.md"
)
BACKEND_MD = REPO_ROOT / "core" / "agents" / "backend.md"


@pytest.fixture(scope="module")
def template_text() -> str:
    assert TEMPLATE.is_file(), (
        f"Channel B seed template missing at {TEMPLATE}. "
        "Java Spring backend work requires this adapter skill to ship."
    )
    return TEMPLATE.read_text(encoding="utf-8")


def test_template_contains_java_spring_maven_stack(template_text: str) -> None:
    for phrase in ("Java", "Spring Boot", "JUnit", "Mockito", "Maven", "mvn test"):
        assert phrase in template_text


def test_template_contains_java_spring_gradle_stack(template_text: str) -> None:
    for phrase in ("Gradle", "./gradlew test", "build.gradle"):
        assert phrase in template_text


def test_template_completion_gates_use_project_test_command(template_text: str) -> None:
    normalized = " ".join(template_text.split())

    assert "All tests must be GREEN (`mvn test`) before commit." not in template_text
    assert "All tests ran and are GREEN (`mvn test`)" not in template_text
    assert (
        "All tests must be GREEN with the project test command "
        "(`mvn test` or `./gradlew test`) before commit."
    ) in normalized
    assert (
        "All tests ran and are GREEN with the project test command "
        "(`mvn test` or `./gradlew test`)"
    ) in normalized


def test_template_allows_mixed_java_kotlin_spring_scope(template_text: str) -> None:
    for phrase in ("Mixed Java/Kotlin Spring Projects", "backend-kotlin-spring", ".java", ".kt"):
        assert phrase in template_text


def test_template_contains_red_green_refactor_cycle(template_text: str) -> None:
    upper = template_text.upper()
    for marker in ("RED", "GREEN", "REFACTOR"):
        assert marker in upper


def test_template_contains_java_test_naming(template_text: str) -> None:
    assert "{ClassName}Test.java" in template_text
    assert "{ClassName}IntegrationTest.java" in template_text


def test_template_contains_java_layering_and_coverage_contract(template_text: str) -> None:
    lower = template_text.lower()
    assert "100%" in template_text and "coverage" in lower
    assert "Object Calisthenics" in template_text
    assert "Tell, Don't Ask" in template_text
    assert "controller" in lower
    assert "service" in lower
    assert "repository" in lower


def test_backend_md_lists_java_spring_as_shipped_template(template_text: str) -> None:
    backend_text = BACKEND_MD.read_text(encoding="utf-8")
    assert "backend-java-spring" in backend_text
    assert "java-spring" in backend_text
    assert "Maven (`mvn test`) or Gradle (`./gradlew test`)" in backend_text
    assert "backend-java-spring" in template_text


def test_template_file_lives_at_templates_dir() -> None:
    assert TEMPLATE.parent.name == "templates"
    assert TEMPLATE.parent.parent.name == "skills"
    assert TEMPLATE.name == "backend-java-spring.md"
