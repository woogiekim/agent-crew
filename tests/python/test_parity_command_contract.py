from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_COMMAND_ROOT = REPO_ROOT / "core" / "commands"
USER_COMMAND_ROOT = REPO_ROOT / "core" / "user" / "commands"


def read_command(name: str) -> str:
    return (USER_COMMAND_ROOT / f"{name}.md").read_text(encoding="utf-8")


def test_parity_commands_are_user_commands_not_system_commands() -> None:
    for command_name in ("parity-check.md", "parity-implement.md"):
        assert (USER_COMMAND_ROOT / command_name).is_file()
        assert not (SYSTEM_COMMAND_ROOT / command_name).exists()


def test_parity_check_requires_reachable_target_discovery() -> None:
    command = read_command("parity-check")

    for marker in (
        "TARGET_DISCOVERY",
        "ENTRYPOINTS_READ",
        "IN_SCOPE_OPERATIONS",
        "OUT_OF_SCOPE_OPERATIONS",
        "CONTRACT_GAPS",
        "DEPENDENCY_GRAPH",
        "UI_COVERAGE",
        "COVERAGE_GAPS",
    ):
        assert marker in command

    assert "starting points, not an upper bound" in command
    assert "endpoint string or grep hit" in command
    assert "file:line" in command
    assert "symbol or method" in command
    assert "call direction" in command


def test_parity_check_covers_ui_and_non_ui_entrypoints() -> None:
    command = read_command("parity-check")

    for technology in ("JavaScript", "TypeScript", "JSP", "PHP", "Vue"):
        assert technology in command

    for entrypoint in (
        "controller",
        "resolver",
        "consumer",
        "scheduler",
        "CLI handler",
    ):
        assert entrypoint in command

    assert "UI_COVERAGE: not_applicable" in command
    assert "read the complete entrypoint file" in command


def test_parity_check_blocks_match_when_discovery_is_incomplete() -> None:
    command = read_command("parity-check")

    assert "MUST NOT report an overall `MATCH`" in command
    assert "unreviewed" in command
    assert "`UNVERIFIABLE`" in command


def test_parity_check_keeps_mutating_calls_outside_its_execution_boundary() -> None:
    command = read_command("parity-check")

    assert "approval gate `crew:run`" not in command
    assert "explicit `crew:run` request" in command


def test_parity_implement_requires_complete_deep_parity_evidence() -> None:
    command_path = USER_COMMAND_ROOT / "parity-implement.md"

    assert command_path.is_file()
    command = read_command("parity-implement")
    for marker in (
        "TARGET_DISCOVERY: completed",
        "IN_SCOPE_OPERATIONS",
        "DEPENDENCY_GRAPH",
        "UI_COVERAGE",
        "COVERAGE_GAPS",
        "EVIDENCE_GATE",
        "STATUS: blocked",
    ):
        assert marker in command

    assert "Endpoint-name-only" in command
    assert "existing partial implementation" in command
    assert "owner, reason, and follow-up" in command


def test_parity_implement_preserves_execution_boundaries() -> None:
    command_path = USER_COMMAND_ROOT / "parity-implement.md"

    assert command_path.is_file()
    command = read_command("parity-implement")
    assert "MUST NOT silently execute" in command
    assert "Continue with crew:run" in command
    assert "Send to another AI session" in command
    assert "crew:run" in command
    assert "How would you like to proceed" in command
    assert "APPROVAL_GATE" not in command
