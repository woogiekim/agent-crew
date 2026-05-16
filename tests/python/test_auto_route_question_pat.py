"""Tests for QUESTION_PAT in core/hooks/auto-route.sh.

Verifies that Korean question endings and state/usage verbs added in
issue #14 are correctly recognized, causing auto-route.sh to emit a
ROUTE directive instead of falling through to inline handling.

These tests exercise the regex pattern directly (pattern-level tests)
without spawning the full hook subprocess, keeping them fast and
hermetic.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = REPO_ROOT / "core" / "hooks" / "auto-route.sh"


# ---------------------------------------------------------------------------
# Extract QUESTION_PAT from auto-route.sh at import time so the tests are
# always in sync with the live file — no copy-paste drift.
# ---------------------------------------------------------------------------

def _extract_question_pat() -> str:
    """Parse QUESTION_PAT out of auto-route.sh and return the compiled regex."""
    src = HOOK_PATH.read_text(encoding="utf-8")
    # Match:  QUESTION_PAT = (
    #             r"...",
    #             ...
    #         )
    m = re.search(
        r'QUESTION_PAT\s*=\s*\((.*?)\)',
        src,
        re.DOTALL,
    )
    if not m:
        raise ValueError("Could not find QUESTION_PAT in auto-route.sh")
    # Evaluate the Python tuple literal in a restricted namespace
    # so we get the actual concatenated string.
    pat_tuple_src = "QUESTION_PAT = (" + m.group(1) + ")"
    ns: dict = {}
    exec(pat_tuple_src, ns)  # noqa: S102
    return ns["QUESTION_PAT"]


QUESTION_PAT = _extract_question_pat()
_compiled = re.compile(QUESTION_PAT, re.IGNORECASE)


def matches(text: str) -> bool:
    return bool(_compiled.search(text))


# ---------------------------------------------------------------------------
# Korean question endings — issue #14 additions (must match)
# ---------------------------------------------------------------------------

class TestKoreanQuestionEndings:
    def test_있나요_matches(self):
        assert matches("AI들이 니모스를 잘 활용하고 있나요?")

    def test_합니까_matches(self):
        assert matches("이 기능이 작동합니까?")

    def test_인가요_matches(self):
        assert matches("이것이 올바른 방법인가요?")

    def test_할까요_matches(self):
        assert matches("어떻게 할까요?")

    def test_됩니까_matches(self):
        assert matches("이렇게 하면 됩니까?")

    def test_인지요_matches(self):
        assert matches("이게 맞는 방향인지요?")

    def test_했나요_matches(self):
        assert matches("테스트를 했나요?")


# ---------------------------------------------------------------------------
# State/usage verbs — issue #14 additions (must match)
# ---------------------------------------------------------------------------

class TestKoreanUsageVerbs:
    def test_활용_matches(self):
        assert matches("AI들이 니모스를 잘 활용하고 있나요?")

    def test_활용_alone_matches(self):
        assert matches("에이전트가 메모리를 활용하고 있어?")

    def test_사용하고_matches(self):
        assert matches("이 기능을 사용하고 있나요?")

    def test_쓰고_matches(self):
        assert matches("훅을 쓰고 있나요?")

    def test_동작_matches(self):
        assert matches("파이프라인이 동작하는지 알고 싶어요")

    def test_작동_matches(self):
        assert matches("훅이 작동하나요?")


# ---------------------------------------------------------------------------
# The exact reproduction case from issue #14
# ---------------------------------------------------------------------------

class TestIssue14ReproductionCase:
    def test_exact_reproduction_phrase_matches(self):
        """Exact phrase from issue #14 reproduction path must match QUESTION_PAT."""
        phrase = "AI들이 니모스를 잘 활용하고 있나요?"
        assert matches(phrase), (
            f"Expected QUESTION_PAT to match {phrase!r} but it did not.\n"
            f"Current QUESTION_PAT:\n{QUESTION_PAT}"
        )


# ---------------------------------------------------------------------------
# Pre-existing Korean question markers — must still match (regression)
# ---------------------------------------------------------------------------

class TestPreexistingKoreanPatterns:
    def test_어떻게_matches(self):
        assert matches("어떻게 작동하나요?")

    def test_뭐야_matches(self):
        assert matches("이게 뭐야?")

    def test_무엇_matches(self):
        assert matches("무엇을 해야 하나요?")

    def test_왜_matches(self):
        assert matches("왜 실패했나요?")

    def test_설명_matches(self):
        assert matches("설명해 주세요")

    def test_알려_matches(self):
        assert matches("알려 주세요")


# ---------------------------------------------------------------------------
# English question markers — must still match (regression)
# ---------------------------------------------------------------------------

class TestEnglishQuestionPatterns:
    def test_why_matches(self):
        assert matches("why does this fail?")

    def test_what_matches(self):
        assert matches("what is the status?")

    def test_how_matches(self):
        assert matches("how does the pipeline work?")

    def test_explain_matches(self):
        assert matches("explain the retry logic")

    def test_show_me_matches(self):
        assert matches("show me the agent list")


# ---------------------------------------------------------------------------
# Negative cases — ACTION_PAT phrases alone must NOT match QUESTION_PAT
# (sanity check — QUESTION_PAT should not accidentally absorb action verbs)
# ---------------------------------------------------------------------------

class TestNegativeCases:
    def test_pure_action_implement_does_not_match(self):
        # "implement" is in ACTION_PAT, not QUESTION_PAT — should not match
        assert not matches("implement the new feature")

    def test_pure_action_추가해_does_not_match(self):
        assert not matches("기능을 추가해")

    def test_pure_action_수정해_does_not_match(self):
        assert not matches("버그를 수정해")
