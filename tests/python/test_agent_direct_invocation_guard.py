"""Tests for direct-agent invocation and per-agent read-only contracts."""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTING_PATH = REPO_ROOT / "core" / "rules" / "agent-routing.md"
AGENT_COMMAND_PATH = REPO_ROOT / "core" / "commands" / "agent.md"
CODEX_INVOCATION_PATH = REPO_ROOT / "adapters" / "codex" / "invocation.md"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _table_rows(text: str, header_fragment: str) -> list[str]:
    rows: list[str] = []
    in_section = False
    section_level = 0
    for line in text.splitlines():
        heading_match = re.match(r"^(#{2,})\s+", line)
        if heading_match and re.search(re.escape(header_fragment), line, re.IGNORECASE):
            in_section = True
            section_level = len(heading_match.group(1))
            continue
        if in_section and heading_match and len(heading_match.group(1)) <= section_level:
            break
        if in_section and line.startswith("|"):
            rows.append(line)
    return rows


def _registry_rows() -> list[str]:
    return _table_rows(_load(ROUTING_PATH), "Agent Registry")


def _agent_row(agent_name: str) -> str:
    rows = _registry_rows()
    matches = [row for row in rows if row.lstrip("| ").lower().startswith(agent_name)]
    assert matches, f"missing registry row for {agent_name}"
    return matches[0]


def test_direct_invocation_remains_available_for_analysis_agents() -> None:
    safe_agents = {
        row.split("|")[1].strip()
        for row in _registry_rows()
        if row.split("|")[1].strip()
        and row.split("|")[4].strip().lower() == "yes"
    }

    assert safe_agents == {
        "backend",
        "frontend",
        "planner",
        "designer",
        "analyst",
        "debugger",
        "documenter",
        "historian",
        "issuer",
        "mentor",
        "learning-mentor",
    }


def test_mutating_capable_agents_remain_directly_invokable() -> None:
    agent_command = _load(AGENT_COMMAND_PATH)
    assert "may execute mutating work" in agent_command.lower()
    assert "read-only guarantees are enforced by each agent definition" in agent_command.lower()

    for agent_name in ("backend", "frontend", "planner", "designer", "documenter", "issuer"):
        row = _agent_row(agent_name)
        assert row.split("|")[4].strip().lower() == "yes", row


def test_qa_owner_requires_supervisor_context() -> None:
    row = _agent_row("qa-owner")

    assert row.split("|")[4].strip().lower() == "no", row
    assert "supervisor context" in row.lower()
    assert "qa_mode" in row


def test_agent_command_is_not_globally_read_only() -> None:
    agent_command = _load(AGENT_COMMAND_PATH)
    codex_invocation = _load(CODEX_INVOCATION_PATH)

    assert "mutating work must use crew:run" not in agent_command.lower()
    assert "complete the read-only task" not in agent_command.lower()
    assert "complete the task" in agent_command.lower()

    assert "single-agent work" in codex_invocation.lower()
    assert "may mutate files or" in codex_invocation.lower()
    assert "agents that are read-only declare" in codex_invocation.lower()


def test_existing_read_only_agents_declare_read_only_in_their_own_rules() -> None:
    for relative in (
        "core/agents/analyst.md",
        "core/agents/debugger.md",
        "core/agents/historian.md",
        "core/agents/mentor.md",
        "core/agents/learning-mentor.md",
        "core/agents/reviewer.md",
    ):
        text = _load(REPO_ROOT / relative).lower()
        assert "read-only contract" in text, relative
