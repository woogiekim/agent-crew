from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_ROOT = REPO_ROOT / "core" / "commands"


def read_command(name: str) -> str:
    return (COMMAND_ROOT / f"{name}.md").read_text(encoding="utf-8")


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
    assert "explicit `crew:task` or `crew:workflow`" in command
