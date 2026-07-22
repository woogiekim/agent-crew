"""Regression coverage for the step-gated feature workflow command."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND = REPO_ROOT / "core" / "commands" / "feature-step.md"
CODEX_WRAPPER = REPO_ROOT / "adapters" / "codex" / "skill" / "feature-step" / "SKILL.md"


def command_text() -> str:
    return COMMAND.read_text(encoding="utf-8")


def test_feature_step_command_ships_from_core_commands() -> None:
    assert COMMAND.is_file()


def test_feature_step_codex_wrapper_delegates_to_provider_neutral_command() -> None:
    assert CODEX_WRAPPER.is_file()
    text = CODEX_WRAPPER.read_text(encoding="utf-8")

    assert "~/.agent-crew/commands/feature-step.md" in text
    assert "Do not implement all phases in one pass" in text
    assert "explicit user approval" in text


def test_feature_step_collects_requirements_from_multiple_sources() -> None:
    text = command_text()

    assert "Plane issue" in text
    assert "GitLab issue" in text
    assert "prompt input" in text
    assert "local files" in text
    assert "requirements-register.md" in text


def test_feature_step_requires_direction_approval_before_implementation() -> None:
    text = command_text()

    assert "Implementation Direction Approval" in text
    assert "Do not start implementation before this approval is recorded" in text
    assert "context/approval.md" in text


def test_feature_step_enforces_separate_phase_gates() -> None:
    text = command_text()

    for phrase in (
        "Phase 2: Domain Design and Domain Logic",
        "Phase 3: Domain Services and Use Cases",
        "Phase 4: Adapters",
        "Phase 5: External System Integration",
    ):
        assert phrase in text

    assert "Do not implement all phases in one pass" in text
    assert "phase-report.md" in text
    assert "retrospective.md" in text
    assert "approval_required" in text


def test_feature_step_outputs_reviewable_status_contract() -> None:
    text = command_text()

    assert "STATUS: completed | blocked | cancelled | approval_required" in text
    assert "CURRENT_PHASE:" in text
    assert "NEXT_APPROVAL:" in text
    assert "ARTIFACTS:" in text
