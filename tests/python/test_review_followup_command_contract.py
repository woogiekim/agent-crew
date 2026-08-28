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


def test_review_followup_triages_review_feedback_before_implementation() -> None:
    command = " ".join(read_command().split())

    for marker in (
        "review feedback is a candidate input, not an implementation command",
        "Disposition must be decided before any item enters an implementation prompt",
        "Only `ACCEPT` and `ACCEPT_WITH_ADAPTATION` items may become direct implementation work",
        "`REJECT_METHOD_ONLY`, `DEFER`, and `REJECT` items remain explicit ledger entries",
        "Use `candidate_disposition` for the triage value",
        "preserve that value as `contract_disposition`",
        "`disposition` only for the lifecycle result",
        "IMPLEMENTED",
        "LOCAL_DONE",
        "Do not convert every `review-synthesis` finding into a `crew:run` todo",
    ):
        assert marker in command


def test_review_followup_codex_wrapper_ships_with_command() -> None:
    wrapper = (CODEX_SKILL_ROOT / "review-followup" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "~/.agent-crew/commands/review-followup.md" in wrapper
    assert "$review-followup" in wrapper
    assert "ordinary numbered choices" in wrapper
    assert "review feedback as candidate input" in wrapper
    assert "candidate_disposition" in wrapper
    assert "contract_disposition" in wrapper
    assert "IMPLEMENTED" in wrapper
