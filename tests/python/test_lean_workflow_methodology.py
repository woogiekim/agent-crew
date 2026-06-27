"""Contracts for the lightweight workflow methodology borrowed from cowave."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
METHODOLOGY = REPO_ROOT / "core" / "rules" / "lean-workflow-methodology.md"


def read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_lean_workflow_methodology_defines_provider_neutral_phases() -> None:
    text = METHODOLOGY.read_text(encoding="utf-8")

    assert "Thin Harness, Fat Rules" in text
    assert "Align -> Plan -> Execute/TDD -> Review" in text
    assert "Context Diet" in text
    assert "Workflow Origin vs Target Scope" in text
    assert "Fake Completion Guard" in text
    assert "provider-neutral" in text
    assert "Claude-only" not in text
    assert "Codex-only" not in text


def test_core_agents_reference_lean_methodology_without_copying_it() -> None:
    for rel_path in (
        "core/commands/run.md",
        "core/agents/analyst.md",
        "core/agents/planner.md",
        "core/agents/reviewer.md",
        "core/agents/test-writer.md",
        "core/agents/supervisor-stages.md",
        "core/agents/supervisor-retry.md",
    ):
        text = read(rel_path)
        assert "core/rules/lean-workflow-methodology.md" in text, rel_path


def test_context_diet_contract_is_documented_for_agent_outputs() -> None:
    text = METHODOLOGY.read_text(encoding="utf-8")

    assert "Do not inline broad file dumps" in text
    assert "Return conclusions, file:line references, and risks" in text
    assert "Pass large artifacts by path" in text


def test_run_command_states_workflow_origin_contract_once() -> None:
    text = read("core/commands/run.md")
    phrase = "workflow command token is the origin, not the target artifact"

    assert text.lower().count(phrase) == 1


def test_supervisor_modified_files_collection_uses_nul_safe_porcelain_parser() -> None:
    text = read("core/agents/supervisor-stages.md")

    assert "git status --porcelain=v1 -z" in text
    assert "awk '{print $2}'" not in text
    assert "split(b\"\\0\")" in text
    assert "porcelain -z emits destination path then original path" in text


def test_supervisor_modified_files_parser_handles_rename_delete_and_space_paths() -> None:
    text = read("core/agents/supervisor-stages.md")
    marker = "python3 -c '\n"
    start = text.index(marker) + len(marker)
    end = text.index("\n'\n)", start)
    parser = text[start:end]
    porcelain_payload = (
        b" M src/with space.py\0"
        b"R  src/new name.py\0src/old name.py\0"
        b" D src/deleted file.py\0"
        b"?? src/new file.py\0"
    )

    result = subprocess.run(
        ["python3", "-c", parser],
        input=porcelain_payload,
        capture_output=True,
        check=True,
    )

    assert json.loads(result.stdout) == [
        "src/with space.py",
        "src/new name.py",
        "src/deleted file.py",
        "src/new file.py",
    ]
