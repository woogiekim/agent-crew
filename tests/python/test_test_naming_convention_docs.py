"""Issue #185: test-name nature-prefix convention is documented."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_tdd_skill_defines_language_agnostic_nature_prefix_contract() -> None:
    text = read("core/agents/skills/tdd.md")

    assert "Test name = `<nature-prefix>[(<qualifier>)] - <behavior>`" in text
    assert "structure is the contract" in text
    assert "success-case" in text
    assert "failure-case" in text
    assert "성공케이스" in text
    assert "실패케이스" in text


def test_tdd_skill_includes_examples_for_supported_test_families() -> None:
    text = read("core/agents/skills/tdd.md")

    for framework in (
        "Kotest",
        "JUnit5",
        "Jest / Vitest",
        "pytest",
        "Go testing",
        "Rust test",
        "ScalaTest / MUnit",
        "XCTest",
    ):
        assert framework in text


def test_test_writing_agents_require_nature_prefix_names() -> None:
    test_writer = read("core/agents/test-writer.md")
    backend = read("core/agents/backend.md")
    frontend = read("core/agents/frontend.md")

    for text in (test_writer, backend, frontend):
        assert "nature prefix" in text
        assert "`<nature-prefix>[(<qualifier>)] - <behavior>`" in text
        assert "success-case" in text
        assert "failure-case" in text


def test_shipped_adapter_templates_reference_test_name_contract() -> None:
    for rel_path in (
        "core/agents/skills/templates/backend-kotlin-spring.md",
        "core/agents/skills/templates/frontend-typescript-react.md",
    ):
        text = read(rel_path)

        assert "Test Case Name Convention" in text
        assert "`<nature-prefix>[(<qualifier>)] - <behavior>`" in text


def test_reviewer_flags_tests_missing_nature_prefix() -> None:
    reviewer = read("core/agents/reviewer.md")

    assert "missing_test_nature_prefix" in reviewer
    assert "`<nature-prefix>[(<qualifier>)] - <behavior>`" in reviewer
