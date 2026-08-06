"""Regression checks for the user-owned rewind command contract."""

from __future__ import annotations

from pathlib import Path

import pytest


HOME = Path.home()
REWIND_COMMAND = HOME / ".agent-crew" / "user" / "commands" / "rewind.md"
CLAUDE_REWIND_COMMAND = HOME / ".claude" / "commands" / "rewind.md"
CODEX_REWIND_SKILL = HOME / ".codex" / "skills" / "rewind" / "SKILL.md"


def _read_existing(path: Path) -> str:
    if not path.is_file():
        pytest.skip(f"local user rewind asset not installed: {path}")
    return path.read_text(encoding="utf-8")


def test_rewind_approval_choices_use_plain_numbers() -> None:
    command = _read_existing(REWIND_COMMAND)

    assert "1. 승인" in command
    assert "2. Dry run" in command
    assert "3. 취소" in command
    assert "①" not in command
    assert "②" not in command
    assert "③" not in command


def test_rewind_preserves_safety_contract_and_dry_run_clarity() -> None:
    command = _read_existing(REWIND_COMMAND)

    for required in (
        "read-only network action",
        "git reset --hard",
        "git clean",
        "git push --force-with-lease",
        "git pull --rebase",
        "MODE: dry_run",
        "NOT_PERFORMED: fetch, rebase, stash, branch creation, conflict edit, stage, push",
        "approval 전 fetch/rebase/stash/branch 생성/push 없음",
    ):
        assert required in command


def test_rewind_explains_target_resolution_and_conflict_decisions() -> None:
    command = _read_existing(REWIND_COMMAND)

    assert "TARGET_RESOLUTION:" in command
    assert "$rewind main" in command
    assert "$rewind origin/main" in command
    assert "CONFLICT_DECISION_REQUIRED:" in command
    assert "1. target 구조를 유지하고 replay 의도만 이식" in command
    assert "명시 결정 전에는 해당 파일을 stage하지 않는다" in command


def test_claude_rewind_mirror_matches_user_command() -> None:
    command = _read_existing(REWIND_COMMAND)
    claude_command = _read_existing(CLAUDE_REWIND_COMMAND)

    assert claude_command == command


def test_codex_rewind_wrapper_delegates_to_user_command() -> None:
    skill = _read_existing(CODEX_REWIND_SKILL)

    assert "~/.agent-crew/user/commands/rewind.md" in skill
    assert "Run only the read-only preflight" in skill
    assert "Never push, force-push, reset, delete user files, discard commits/work" in skill
