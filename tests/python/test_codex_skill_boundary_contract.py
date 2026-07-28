"""Tests for Codex skill boundary wording in agent-crew routing."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_crew_run_wrapper_forbids_unapproved_third_party_skill_autoload():
    text = read("adapters/codex/skill/crew:run/SKILL.md")

    assert "Do not load unrelated host/plugin" in text
    assert "external-skill-approval.md" in text
    assert "domain-specific Codex skill context" not in text
    assert "Workflow Origin vs Target Scope" in text
    assert "A leading `$crew:run 코드리뷰` means" in text
    assert "Only treat the wrapper itself as the review target" in text


def test_codex_command_wrappers_preserve_prompt_compiler_contract():
    text = read("adapters/codex/skill/crew:run/SKILL.md")

    assert "`crew-run` from a natural-language implementation request" not in text
    assert "Use when the user explicitly mentions $crew:run" in text


def test_run_command_current_session_limits_automatic_skill_sources():
    text = read("core/commands/run.md")
    compact = " ".join(text.split())

    assert "Domain-match alone is not approval" in text
    assert "Do not auto-load unrelated host/plugin" in compact
    assert "~/.claude/agent-crew/skills/" in text
    assert "context/external-skill-approval.md" in text
    assert "Workflow Origin vs Target Scope" in text
    assert "workflow command token is the origin, not the target artifact" in text


def test_provider_neutral_global_rules_define_external_skill_boundary():
    text = read("core/global-agents.md")
    skill_rule = read("core/rules/agent-skill-loading.md")

    assert "Non-agent-crew host/plugin skills require explicit user approval" in text
    assert "Domain-match alone is not approval" in text
    assert "This applies to every host adapter, not only Codex" in skill_rule
    assert "~/.claude/agent-crew/skills/" in skill_rule
