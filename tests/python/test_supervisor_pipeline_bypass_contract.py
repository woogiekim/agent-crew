"""Regression tests for supervisor pipeline-bypass prevention."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SUPERVISOR = REPO_ROOT / "core" / "agents" / "supervisor.md"
BOOTSTRAP = REPO_ROOT / "core" / "agents" / "supervisor-bootstrap.md"


def test_supervisor_absolute_rules_forbid_fresh_run_pipeline_bypass():
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "Pipeline Bypass Prohibition" in text
    assert "pipeline.json" in text
    assert "Phase 1b+1c" in text
    assert "Phase 1d plan approval" in text
    assert "Phase 2 has spawned every planned stage agent" in text
    assert "STATUS: completed" in text
    assert "supervisor_pipeline_bypass_prevented" in text


def test_supervisor_requirements_file_cannot_skip_planning_or_review():
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "{TASK_DIR}/context/requirements.md" in text
    assert "never proof that analysis/planning" in text
    assert "final reviewer may be skipped" in text


def test_bootstrap_documents_required_fresh_run_sequence():
    text = BOOTSTRAP.read_text(encoding="utf-8")

    assert "Direct implementation bypass guard" in text
    assert "there is no\n\"simple enough\" shortcut" in text
    assert "Phase 1a requirement gate" in text
    assert "Phase 1b+1c analyst planning spawn" in text
    assert "Phase 1d plan approval gate" in text
    assert "Phase 2 stage-agent execution" in text
    assert "reviewer stage completion" in text


def test_bootstrap_blocks_inline_all_layers_completion_pattern():
    text = BOOTSTRAP.read_text(encoding="utf-8")

    assert "PHASE | Implementation" in text
    assert "STAGE_DONE | all layers" in text
    assert "STATUS: blocked" in text
    assert "BLOCKER: supervisor_pipeline_bypass_prevented" in text
