from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_COMMAND_ROOT = REPO_ROOT / "core" / "commands"
USER_COMMAND_ROOT = REPO_ROOT / "core" / "user" / "commands"
CODEX_SKILL_ROOT = REPO_ROOT / "adapters" / "codex" / "skill"


def read_command() -> str:
    return (USER_COMMAND_ROOT / "review-followup.md").read_text(encoding="utf-8")


def test_review_followup_is_user_command_not_system_command() -> None:
    assert (USER_COMMAND_ROOT / "review-followup.md").is_file()
    assert not (SYSTEM_COMMAND_ROOT / "review-followup.md").exists()


def test_review_followup_orchestrates_existing_review_commands_without_hooks() -> None:
    command = read_command()

    for existing_step in (
        "`mr-review-rate`",
        "`prompt`",
        "`crew:run`",
        "`review-synthesis`",
    ):
        assert existing_step in command

    assert "No lifecycle hook" in command
    assert "No `PreToolUse` hook" in command
    assert "No `UserPromptSubmit` hook" in command


def test_review_followup_requires_user_decisions_between_mutating_cycles() -> None:
    command = read_command()

    for marker in (
        "approval checkpoint",
        "must not auto-execute",
        "must not auto-post",
        "must not push",
        "max_cycles",
        "ordinary numbered choices",
    ):
        assert marker in command


def test_review_followup_preserves_review_intent_and_contract_safety() -> None:
    command = read_command()

    for marker in (
        "review-ledger",
        "Review Intent Fidelity",
        "Contract-First Feedback Fidelity",
        "LOCAL_REFLECTION_RATE",
        "MR_REFLECTION_RATE",
        "contract-safe",
        "parity-safe",
        "scope-safe",
        "side-effect-safe",
    ):
        assert marker in command


def test_review_followup_codex_wrapper_ships_with_command() -> None:
    wrapper = (CODEX_SKILL_ROOT / "review-followup" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "~/.agent-crew/commands/review-followup.md" in wrapper
    assert "$review-followup" in wrapper
    assert "ordinary numbered choices" in wrapper
