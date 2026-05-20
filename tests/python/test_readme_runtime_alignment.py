"""README alignment checks for runtime behavior that has drifted before."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
README = REPO_ROOT / "README.md"


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_documents_merged_analyst_planner_flow():
    text = readme_text()
    assert "analyst+planner" in text
    assert "Phase 1b+1c" in text
    assert "requirements → analyst → planner" not in text
    assert "Phase 1b: analyst" not in text
    assert "Phase 1c: planner" not in text


def test_readme_documents_sufficiency_gated_requirements():
    text = readme_text()
    assert "Requirements sufficiency gate" in text
    assert "Sufficiency-Gated Architecture" in text
    assert "delegate to requirements agent only when ambiguous" in text


def test_readme_documents_codex_capability_fallbacks():
    text = readme_text()
    assert "Host Capability Caveat" in text
    assert "Codex currently runs in guided prompt mode" in text
    assert "`agent_background`, `task_tools`" in text
    assert "inline execution and markdown/file" in text
    assert "fallbacks instead of claiming native background sessions" in text
    assert "advisory prompt-workflow guardrails" in text
    assert "not as enforced `hook_system=true` guarantees" in text


def test_readme_documents_native_cli_boundary():
    text = readme_text()
    assert "`crew` is the native shell entrypoint" in text
    assert "`crew setup`, `crew status`,\n`crew update --local`, and the initial `crew run` state transition are\ndeterministic CLI paths" in text
    assert "`crew run` writes task state and a supervisor handoff" in text
    assert "`crew agent` still fails fast" in text


def test_readme_defines_prompt_internal_control_layer():
    text = readme_text()
    assert "orchestration layer that runs inside\nhost AI prompt workflows" in text
    assert "It is not a replacement for Codex, Claude, Copilot" in text
    assert "The host AI remains the execution plane" in text
    assert "agent-crew\nprovides the local control plane" in text
