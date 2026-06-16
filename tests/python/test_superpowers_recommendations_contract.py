"""Contract tests for the Superpowers benchmark follow-up improvements."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_systematic_debugging_skill_exists_and_defines_four_phase_flow() -> None:
    text = read("core/agents/skills/systematic-debugging.md")

    assert "Root cause investigation" in text
    assert "Pattern analysis" in text
    assert "Hypothesis" in text
    assert "Implement" in text
    assert "3" in text and "architecture" in text.lower()


def test_human_acceptance_matrix_rule_is_connected_to_qa_owner() -> None:
    rule = read("core/rules/human-acceptance-matrix.md")
    qa_owner = read("core/agents/qa-owner.md")

    assert "requirement" in rule.lower()
    assert "manual acceptance" in rule.lower()
    assert "evidence" in rule.lower()
    assert "human-acceptance-matrix.md" in qa_owner


def test_evaluation_driven_development_rule_is_connected_to_pipeline() -> None:
    rule = read("core/rules/evaluation-driven-development.md")
    quality_loop = read("core/rules/quality-loop.md")
    pipeline_state = read("core/rules/state-files/pipeline-json.md")

    assert "eval_command" in rule
    assert "evaluation-metrics.json" in rule
    assert "eval_command" in quality_loop
    assert "eval_command" in pipeline_state


def test_run_command_documents_structured_close_out_menu() -> None:
    text = read("core/commands/run.md")

    assert "Close-Out Menu" in text
    for expected in ("merge locally", "push", "keep branch", "discard"):
        assert expected in text.lower()


def test_superpowers_benchmark_doc_has_current_status_sections() -> None:
    text = read("docs/superpowers-benchmark/findings.md")

    assert "Implemented" in text
    assert "Still Open" in text
    assert "New 2026-06" in text


def test_claude_plugin_manifest_exists_and_points_to_provider_neutral_core() -> None:
    manifest = json.loads(read(".claude-plugin/plugin.json"))

    assert manifest["name"] == "agent-crew"
    assert manifest["version"]
    assert manifest["description"]
    assert manifest["repository"]
    assert manifest["entrypoints"]["provider_neutral_core"] == "core/"
