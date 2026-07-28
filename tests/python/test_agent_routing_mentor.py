"""Tests for mentor agent registration and learning-mentor compatibility."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTING_PATH = REPO_ROOT / "core" / "rules" / "agent-routing.md"
RUNTIME_PATH = REPO_ROOT / "core" / "scripts" / "crew-runtime.py"
MENTOR_PATH = REPO_ROOT / "core" / "agents" / "mentor.md"
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


def test_runtime_auto_route_prefers_explicit_mentor_review_coaching() -> None:
    """success-case(regression) - TC-002 routes explicit Mentor coaching to mentor."""
    agents = {
        "analyst": {"safe": "yes"},
        "mentor": {"safe": "yes"},
        "learning-mentor": {"safe": "yes"},
    }

    for task in (
        "리뷰 결과를 멘토처럼 설명해줘",
        "리뷰 대응 코칭해줘",
        "coach me on this review feedback",
    ):
        agent_name, reason = crew_runtime.auto_route_agent(task, agents)

        assert agent_name == "mentor"
        assert "mentor" in reason


def test_tc001_runtime_auto_route_preserves_historian_before_mentor() -> None:
    """success-case(regression) - TC-001 preserves historian priority."""
    agents = {
        "historian": {"safe": "yes"},
        "mentor": {"safe": "yes"},
        "learning-mentor": {"safe": "yes"},
    }

    for task in (
        "what did we learn this session?",
        "what agent just ran for mentor?",
        "방금 멘토 에이전트가 동작한거야?",
    ):
        agent_name, reason = crew_runtime.auto_route_agent(task, agents)

        assert agent_name == "historian"
        assert "historian" in reason


def test_runtime_auto_route_keeps_broad_review_evaluation_with_analyst() -> None:
    """success-case(regression) - TC-007 keeps broad review analysis with analyst."""
    agents = {
        "analyst": {"safe": "yes"},
        "mentor": {"safe": "yes"},
        "learning-mentor": {"safe": "yes"},
    }

    for task in (
        "검토해줘",
        "평가해줘",
        "explain this reviewer feedback",
    ):
        agent_name, reason = crew_runtime.auto_route_agent(task, agents)

        assert agent_name == "analyst"
        assert "analyst" in reason


def test_tc002_runtime_auto_route_keeps_mentor_target_analysis_with_analyst() -> None:
    """success-case(regression) - TC-002 keeps Mentor target analysis with analyst."""
    agents = {
        "analyst": {"safe": "yes"},
        "mentor": {"safe": "yes"},
        "learning-mentor": {"safe": "yes"},
    }

    for task in (
        "Mentor Agent 동작 검증",
        "Analyze whether the Mentor agent works as designed",
        "멘토 에이전트 라우팅 문제를 검토해줘",
    ):
        agent_name, reason = crew_runtime.auto_route_agent(task, agents)

        assert agent_name == "analyst"
        assert "analyst" in reason


def test_mentor_prompt_declares_review_explanation_context_contract() -> None:
    text = MENTOR_PATH.read_text(encoding="utf-8")

    assert "Review Explanation Coaching Mode" in text
    assert "TASK_DIR" in text
    assert "MENTOR_CONTEXT_PATH" in text
    assert "context/review.md" in text
    assert "Do not re-review" in text


def test_tc004_runtime_mutating_mentor_gerunds_can_select_mentor() -> None:
    """success-case(regression) - TC-004 selects the agent; mutation policy is agent-owned."""
    agents = {
        "mentor": {"safe": "yes"},
        "learning-mentor": {"safe": "yes"},
    }

    for task in (
        "teach me while refactoring this function",
        "teach me while removing this file",
        "teach me while changing this hook",
        "teach me while testing this feature",
    ):
        agent_name, reason = crew_runtime.auto_route_agent(task, agents)

        assert crew_runtime.looks_mutating(task) is True
        assert agent_name == "mentor"
        assert "mentor" in reason


def test_tc005_runtime_historians_read_only_running_and_commit_noun_queries() -> None:
    """success-case(regression) - TC-005 routes running/commit noun queries to historian."""
    agents = {
        "historian": {"safe": "yes"},
        "analyst": {"safe": "yes"},
    }

    for task in (
        "what's running",
        "어떤 commit 있어?",
        "what is the latest commit?",
    ):
        agent_name, reason = crew_runtime.auto_route_agent(task, agents)

        assert crew_runtime.looks_mutating(task) is False
        assert agent_name == "historian"
        assert "historian" in reason


def test_runtime_resolves_installed_codex_bridge_default(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    bridge = home / "adapters" / "codex" / "bin" / "codex-host-bridge"
    capabilities = home / "state" / project.name / "capabilities.json"
    bridge.parent.mkdir(parents=True)
    capabilities.parent.mkdir(parents=True)
    bridge.write_text("#!/bin/sh\necho bridge\n", encoding="utf-8")
    bridge.chmod(0o755)
    capabilities.write_text(json.dumps({"host": "codex"}), encoding="utf-8")

    resolved = crew_runtime.resolve_host_bridge_command(None, home, project)

    assert resolved == str(bridge)


def test_runtime_resolves_active_codex_bridge_before_capabilities_host(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    codex_bridge = home / "adapters" / "codex" / "bin" / "codex-host-bridge"
    claude_bridge = home / "adapters" / "claude" / "bin" / "claude-host-bridge"
    capabilities = home / "state" / project.name / "capabilities.json"
    codex_bridge.parent.mkdir(parents=True)
    claude_bridge.parent.mkdir(parents=True)
    capabilities.parent.mkdir(parents=True)
    codex_bridge.write_text("#!/bin/sh\necho codex\n", encoding="utf-8")
    claude_bridge.write_text("#!/bin/sh\necho claude\n", encoding="utf-8")
    codex_bridge.chmod(0o755)
    claude_bridge.chmod(0o755)
    capabilities.write_text(json.dumps({"host": "claude"}), encoding="utf-8")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")

    resolved = crew_runtime.resolve_host_bridge_command(None, home, project)

    assert resolved == str(codex_bridge)
