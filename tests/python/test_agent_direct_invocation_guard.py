"""Tests for the direct-invocation guard in crew:agent.

The goal is to keep crew:agent read-only. Any task that mutates files, docs,
issues, commits, or other state must use crew:run.
"""
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
        "documenter",
        "historian",
        "issuer",
        "learning-mentor",
        "input-normalizer",
        "korean-normalizer",
    }


def test_mutating_agents_remain_covered_by_the_read_only_guard() -> None:
    agent_command = _load(AGENT_COMMAND_PATH)
    assert "crew:run" in agent_command.lower()

    for agent_name in ("backend", "frontend", "planner", "designer", "documenter", "issuer"):
        row = _agent_row(agent_name)
        assert row.split("|")[4].strip().lower() == "yes", row


def test_agent_command_and_codex_invocation_are_read_only() -> None:
    agent_command = _load(AGENT_COMMAND_PATH)
    codex_invocation = _load(CODEX_INVOCATION_PATH)

    assert "read-only" in agent_command.lower()
    assert "mutating work must use crew:run" in agent_command.lower()
    assert "complete the read-only task" in agent_command.lower()

    assert "read-only investigation" in codex_invocation.lower()
    assert "any task that would edit files" in codex_invocation.lower()
    assert "mutate state" in codex_invocation.lower()
