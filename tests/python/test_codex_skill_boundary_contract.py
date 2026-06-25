"""Tests for Codex skill boundary wording in agent-crew routing."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_crew_run_wrapper_forbids_unapproved_third_party_skill_autoload():
    text = read("adapters/codex/skill/crew-run/SKILL.md")

    assert "Do not load unrelated Codex/plugin" in text
    assert "external-skill-approval.md" in text
    assert "domain-specific Codex skill context" not in text


def test_agent_crew_bootstrap_preserves_only_explicit_skill_context():
    text = read("adapters/codex/skill/agent-crew/SKILL.md")

    assert "preserves explicitly invoked Codex skill context" in text
    assert "Do not auto-load a non-agent-crew or third-party" in text
    assert "domain-specific Codex skill context" not in text


def test_run_command_current_session_limits_automatic_skill_sources():
    text = read("core/commands/run.md")

    assert "Domain-match alone is not approval" in text
    assert "Do not auto-load unrelated Codex/plugin" in text
    assert "context/external-skill-approval.md" in text
