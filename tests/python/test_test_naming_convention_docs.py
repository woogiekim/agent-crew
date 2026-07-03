"""Issue #185: test-name nature-prefix convention is documented."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_tdd_skill_defines_language_agnostic_nature_prefix_contract() -> None:
    text = read("core/agents/skills/tdd.md")

    assert "Test name = `<nature-prefix>[(<qualifier>)] - <behavior>`" in text
    assert "Korean canonical form: `{케이스타입}(qualifier) - {message}`" in text
    assert "structure is the contract" in text
    assert "success-case" in text
    assert "boundary-case" in text
    assert "failure-case" in text
    assert "성공케이스" in text
    assert "경계케이스" in text
    assert "실패케이스" in text


def test_tdd_skill_documents_simplified_qualifier_taxonomy() -> None:
    text = read("core/agents/skills/tdd.md")

    assert "Simplified qualifier taxonomy" in text
    for qualifier in (
        "`회귀` / `regression`",
        "`계약` / `contract`",
        "`부수효과` / `side-effect`",
        "`보안` / `security`",
        "`멱등성` / `idempotency`",
        "`동시성` / `concurrency`",
        "`제한` / `limit`",
        "`감사` / `audit`",
    ):
        assert qualifier in text


def test_tdd_skill_uses_boundary_case_for_boundary_inputs() -> None:
    text = read("core/agents/skills/tdd.md")

    assert "경계케이스(계약) - contentType/status 가 null 이면 enum 필드도 null 이다" in text
    assert "boundary-case(contract) - maps an out-of-range enum code to null without throwing" in text


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
        assert "boundary-case" in text
        assert "failure-case" in text
        assert "경계케이스" in text


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


def test_tc_ids_are_mapping_traceability_not_required_test_name_tokens() -> None:
    tdd = read("core/agents/skills/tdd.md")
    test_writer = read("core/agents/test-writer.md")
    reviewer = read("core/agents/reviewer.md")

    for text in (tdd, test_writer):
        normalized = " ".join(text.split())

        assert "TC-ID" in text
        assert "context/test-case-mapping.md" in text
        assert "TC-ID is an internal checklist/mapping identifier" in normalized
        assert "not required in test names" in normalized

    combined_test_guidance = "\n".join((tdd, test_writer))

    assert "include the related TC-ID in its display name" not in combined_test_guidance
    assert "Include the checklist `TC-ID` in the display name" not in combined_test_guidance
    assert "TC-ID in its display name" not in combined_test_guidance
    assert "absence of `TC-001`" in reviewer
