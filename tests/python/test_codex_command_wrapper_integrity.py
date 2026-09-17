"""Ensure shipped Codex wrappers have provider-neutral command definitions."""

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "adapters" / "codex" / "skill"
COMMAND_ROOT = REPO_ROOT / "core" / "commands"
USER_COMMAND_ROOT = REPO_ROOT / "core" / "user" / "commands"
COMMAND_REFERENCE_RE = re.compile(r"~/.agent-crew/commands/([A-Za-z0-9._-]+\.md)")


def test_every_codex_command_wrapper_references_a_shipped_command():
    missing: list[str] = []

    for skill_file in sorted(SKILL_ROOT.glob("*/SKILL.md")):
        references = COMMAND_REFERENCE_RE.findall(skill_file.read_text(encoding="utf-8"))
        for command_name in references:
            if not (COMMAND_ROOT / command_name).is_file() and not (
                USER_COMMAND_ROOT / command_name
            ).is_file():
                missing.append(f"{skill_file.relative_to(REPO_ROOT)} -> {command_name}")

    assert not missing, "Missing provider-neutral command assets:\n" + "\n".join(missing)


def test_parity_wrappers_and_commands_ship_together():
    assert (SKILL_ROOT / "parity-check" / "SKILL.md").is_file()
    assert not (SKILL_ROOT / "crew:parity-check" / "SKILL.md").is_file()
    assert (SKILL_ROOT / "parity-implement" / "SKILL.md").is_file()
    assert not (SKILL_ROOT / "crew:parity-implement" / "SKILL.md").is_file()
    assert (USER_COMMAND_ROOT / "parity-check.md").is_file()
    assert (USER_COMMAND_ROOT / "parity-implement.md").is_file()
    assert not (COMMAND_ROOT / "parity-check.md").exists()
    assert not (COMMAND_ROOT / "parity-implement.md").exists()


def test_smoke_test_wrapper_and_user_command_ship_together():
    wrapper = (SKILL_ROOT / "smoke-test" / "SKILL.md").read_text(encoding="utf-8")
    command = (USER_COMMAND_ROOT / "smoke-test.md").read_text(encoding="utf-8")

    assert "~/.agent-crew/commands/smoke-test.md" in wrapper
    assert "$smoke-test" in wrapper
    assert "IntelliJ `.http`" in wrapper
    assert "local project server" in wrapper
    assert "Docker" in wrapper
    assert "devstack" not in wrapper.lower()
    assert "dev stack" not in wrapper.lower()
    assert "devstack" not in command.lower()
    assert "dev stack" not in command.lower()
    assert (USER_COMMAND_ROOT / "smoke-test.md").is_file()
    assert not (COMMAND_ROOT / "smoke-test.md").exists()


def test_smoke_test_artifacts_are_named_by_feature_not_issue_identifier():
    command = (USER_COMMAND_ROOT / "smoke-test.md").read_text(encoding="utf-8")

    assert "FEATURE_NAME" in command
    assert "smoke-<feature-name>-<timestamp>.md" in command
    assert "Do not include issue, ticket, MR, PR, branch, or commit identifiers" in command


def test_review_synthesis_wrapper_uses_effective_command_path():
    wrapper = (SKILL_ROOT / "review-synthesis" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "~/.agent-crew/commands/review-synthesis.md" in wrapper
    assert "~/.agent-crew/user/commands/review-synthesis.md" not in wrapper
    assert (USER_COMMAND_ROOT / "review-synthesis.md").is_file()


def test_review_synthesis_wrapper_loads_codex_system_review_agent_as_lens():
    wrapper = (SKILL_ROOT / "review-synthesis" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "~/.codex/skills/.system/review-agent/SKILL.md" in wrapper
    assert "codex-system-review" in wrapper
    assert "source_lens=codex-system-review" in wrapper
    assert "load it in full" in wrapper
    assert "read-only" in wrapper
    assert "Do not directly invoke the system `reviewer` agent" in wrapper


def test_parity_check_preserves_explicit_repository_and_mode_resolution():
    command = (USER_COMMAND_ROOT / "parity-check.md").read_text(encoding="utf-8")

    assert "If not provided as arguments, ask the user for the repo paths" in command
    assert "If not specified, present a structured choice" in command
    assert "Do not guess paths from training data or prior sessions" in command
