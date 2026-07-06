"""Regression tests for supervisor pipeline-bypass prevention."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SUPERVISOR = REPO_ROOT / "core" / "agents" / "supervisor.md"
BOOTSTRAP = REPO_ROOT / "core" / "agents" / "supervisor-bootstrap.md"
RUN_COMMAND = REPO_ROOT / "core" / "commands" / "run.md"
AGENT_COMMAND = REPO_ROOT / "core" / "commands" / "agent.md"
ANALYST = REPO_ROOT / "core" / "agents" / "analyst.md"
REVIEWER = REPO_ROOT / "core" / "agents" / "reviewer.md"
CODEX_SETUP = REPO_ROOT / "adapters" / "codex" / "setup.sh"
CLAUDE_SETUP = REPO_ROOT / "adapters" / "claude" / "setup.sh"


def test_supervisor_absolute_rules_forbid_fresh_run_pipeline_bypass():
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "allowed-tools:" in text
    assert "TaskCreate" in text
    assert "TaskOutput" in text
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


def test_bootstrap_log_progress_hard_blocks_stage_events_without_pipeline():
    text = BOOTSTRAP.read_text(encoding="utf-8")

    assert "progress_event_requires_pipeline" in text
    assert "STAGE|STAGE_DONE|STAGE_TDD_PARALLEL_STARTED" in text
    assert "BLOCKER: supervisor_pipeline_bypass_prevented" in text
    assert 'case "${event}" in' in text


def test_bootstrap_phase_1d_requires_pipeline_before_approval():
    text = BOOTSTRAP.read_text(encoding="utf-8")

    assert "Phase 1d pipeline existence gate" in text
    assert "[ ! -f \"${PIPELINE_PATH}\" ]" in text
    assert "pipeline_missing_before_plan_approval" in text


def test_run_passes_supervisor_mode_sentinel_to_every_supervisor_spawn():
    text = RUN_COMMAND.read_text(encoding="utf-8")

    assert "MODE: supervisor" in text
    assert "EXECUTION_MODE: single or parallel" in text
    assert "TASK, TASK_ID, TASK_DIR, PROJECT_ROOT, BRANCH," in text


def test_direct_command_keeps_direct_mode_sentinel():
    text = AGENT_COMMAND.read_text(encoding="utf-8")

    assert "MODE=direct" in text
    assert "You are running in MODE=direct" in text


def test_bootstrap_requires_supervisor_mode_sentinel_before_progress():
    text = BOOTSTRAP.read_text(encoding="utf-8")

    assert "supervisor_mode_sentinel_missing" in text
    assert "[ \"${MODE:-}\" != \"supervisor\" ]" in text
    assert "MODE=supervisor" in text
    assert "exit 1" in text


def test_supervisor_ignores_leaked_direct_mode_preamble():
    text = SUPERVISOR.read_text(encoding="utf-8")

    assert "MODE=direct" in text
    assert "direct-mode stateless-invocation preamble" in text
    assert "ignore it" in text
    assert "supervisor contract prevails" in text


def test_progress_guard_hook_is_registered_for_supported_hosts():
    hook = REPO_ROOT / "core" / "hooks" / "supervisor-progress-guard.sh"
    codex_setup = CODEX_SETUP.read_text(encoding="utf-8")
    claude_setup = CLAUDE_SETUP.read_text(encoding="utf-8")

    assert hook.is_file()
    assert "supervisor-progress-guard.sh" in codex_setup
    assert "supervisor-progress-guard.sh" in claude_setup


def test_analyst_skill_reads_have_supervisor_verified_evidence():
    analyst_text = ANALYST.read_text(encoding="utf-8")
    bootstrap_text = BOOTSTRAP.read_text(encoding="utf-8")

    assert "context/analyst-skill-load.md" in analyst_text
    assert "requirement-gathering.md" in analyst_text
    assert "pipeline-planning.md" in analyst_text
    assert "analyst_skill_read_evidence_missing" in bootstrap_text
    assert "context/analyst-skill-load.md" in bootstrap_text
    assert "requirement-gathering.md" in bootstrap_text
    assert "pipeline-planning.md" in bootstrap_text


def test_analyst_skill_load_artifact_is_pipeline_mode_only():
    analyst_text = ANALYST.read_text(encoding="utf-8")

    assert '[ "${MODE:-}" = "supervisor" ]' in analyst_text
    assert '[ -n "${TASK_DIR:-}" ]' in analyst_text
    assert "MODE=direct" in analyst_text
    assert "do not create task state" in analyst_text


def test_reviewer_rejects_code_changes_without_test_files_or_tdd_exception():
    text = REVIEWER.read_text(encoding="utf-8")

    assert "tests_absent_for_code_change" in text
    assert "context/tdd-exception.md" in text
    assert "DIFF_TEST_FILE_COUNT" in text
    assert "touched_code=true; diff_tests=0; tdd_exception=false" in text
