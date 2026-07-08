"""Contract tests for temporary repair evidence guidance."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = r"\s+".join(re.escape(part) for part in phrase.split())

    return bool(re.search(pattern, text))


def test_tdd_guidance_classifies_temporary_repair_evidence():
    """success-case(contract) - TDD guidance separates durable tests from repair evidence."""
    # given
    text = _read("core/agents/skills/tdd.md")

    # when / then
    assert "durable product-contract test" in text
    assert "temporary internal-repair evidence" in text
    assert _contains_phrase(
        text,
        "only proves that a bad intermediate implementation was reverted",
    )
    assert _contains_phrase(
        text,
        "temporary local checks, focused command output, diff evidence, or task-context notes",
    )
    assert _contains_phrase(
        text,
        "public API behavior, product requirement, security policy, data rule, legacy parity, or compatibility requirement",
    )


def test_code_review_guidance_flags_repair_only_tests_without_contract_source():
    """success-case(contract) - review guidance blocks repair-only tests without a contract source."""
    # given
    text = _read("core/agents/skills/code-review.md")

    # when / then
    assert "repair-only or revert-only tests" in text
    assert "durable contract source" in text
    assert "REVIEW: NEEDS_CHANGES" in text
    assert _contains_phrase(
        text,
        "temporary local checks, focused command output, diff evidence, or task-context notes",
    )


def test_repair_guidance_avoids_private_context():
    """success-case(contract) - repair-test guidance remains generic."""
    # given
    combined = "\n".join(
        [
            _read("core/agents/skills/tdd.md"),
            _read("core/agents/skills/code-review.md"),
        ]
    )
    private_workspace_patterns = [
        r"/Users/[A-Za-z0-9._-]+",
        r"/home/[A-Za-z0-9._-]+",
        r"[A-Za-z]:\\Users\\[^\\\s]+",
    ]

    # when / then
    assert not any(
        re.search(pattern, combined)
        for pattern in private_workspace_patterns
    )
