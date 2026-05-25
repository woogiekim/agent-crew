"""Tests for mentor agent registration and learning-mentor compatibility."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTING_PATH = REPO_ROOT / "core" / "rules" / "agent-routing.md"
RUNTIME_PATH = REPO_ROOT / "core" / "scripts" / "crew-runtime.py"
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crew_runtime = _load_module(RUNTIME_PATH, "crew_runtime")


def _load_routing_text() -> str:
    return ROUTING_PATH.read_text(encoding="utf-8")


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


def test_mentor_is_registered_for_direct_invocation() -> None:
    rows = _table_rows(_load_routing_text(), "Agent Registry")
    mentor_rows = [row for row in rows if row.lstrip("| ").lower().startswith("mentor")]

    assert mentor_rows, "mentor registry row not found"
    assert mentor_rows[0].split("|")[4].strip().lower() == "yes"


def test_learning_mentor_remains_as_legacy_alias() -> None:
    rows = _table_rows(_load_routing_text(), "Agent Registry")
    alias_rows = [row for row in rows if row.lstrip("| ").lower().startswith("learning-mentor")]

    assert alias_rows, "learning-mentor compatibility row not found"
    assert "legacy" in alias_rows[0].lower()
    assert "prefer mentor" in alias_rows[0].lower()
    assert alias_rows[0].split("|")[4].strip().lower() == "yes"


def test_learning_keywords_auto_route_to_mentor() -> None:
    rows = _table_rows(_load_routing_text(), "Auto-Routing Rules")
    mentor_rows = [row for row in rows if row.lstrip("| ").startswith("9 |")]

    assert mentor_rows, "mentor auto-routing row not found"
    assert mentor_rows[0].split("|")[3].strip() == "mentor"
    assert "teach" in mentor_rows[0].lower()
    assert "learning" in mentor_rows[0].lower()


def test_runtime_auto_route_prefers_mentor_over_legacy_alias() -> None:
    agents = {
        "mentor": {"safe": "yes"},
        "learning-mentor": {"safe": "yes"},
    }

    agent_name, reason = crew_runtime.auto_route_agent(
        "teach me dependency injection with examples",
        agents,
    )

    assert agent_name == "mentor"
    assert "mentor" in reason
