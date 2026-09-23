"""Durable regression tests for supervisor child lifecycle handling."""

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "core" / "scripts" / "stage_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("stage_lifecycle", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
stage_lifecycle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage_lifecycle)


def _state(
    *,
    stage_kind: str = "implementation",
    now: str = "2026-09-22T00:00:00Z",
    timeout_enforceable: bool = True,
    fallback_mode: str = "native",
) -> dict:
    return stage_lifecycle.new_stage_state(
        stage_index=1,
        agent="backend",
        stage_kind=stage_kind,
        unit_id="unit-backend",
        invocation_id="invocation-1",
        attempt=1,
        mutating=stage_kind in {"implementation", "test_writer"},
        now=now,
        timeout_enforceable=timeout_enforceable,
        fallback_mode=fallback_mode,
    )


def test_failure_case_unknown_custom_writer_defaults_to_mutating_fail_closed():
    sut = stage_lifecycle.new_stage_state(
        stage_index=2,
        agent="custom-resolver-writer",
        stage_kind="custom",
        unit_id="unit-custom",
        invocation_id="invocation-custom",
        attempt=1,
        now="2026-09-22T00:00:00Z",
    )

    decision = stage_lifecycle.decide_next_action(
        sut,
        now="2026-09-22T00:01:00Z",
        host_status="error",
    )

    assert sut["mutating"] is True
    assert decision["action"] == "interrupt_and_block"
    assert decision["retry_allowed"] is False


def test_boundary_case_fanout_state_paths_include_unique_invocation_identity(tmp_path):
    first = stage_lifecycle.lifecycle_state_path(
        tmp_path, stage_index=3, unit_id="api", invocation_id="invoke-a", attempt=1
    )
    second = stage_lifecycle.lifecycle_state_path(
        tmp_path, stage_index=3, unit_id="api", invocation_id="invoke-b", attempt=1
    )
    retry = stage_lifecycle.lifecycle_state_path(
        tmp_path, stage_index=3, unit_id="api", invocation_id="invoke-a", attempt=2
    )

    assert len({first, second, retry}) == 3
    assert "api" in first.name
    assert "invoke-a" in first.name
    assert "attempt-1" in first.name


def test_boundary_case_running_host_status_prevents_terminal_grace_interrupt():
    sut = _state(stage_kind="reviewer")
    stage_lifecycle.record_event(
        sut,
        event="artifact_ready",
        at="2026-09-22T00:00:01Z",
        reason="review artifact verified",
    )

    decision = stage_lifecycle.decide_next_action(
        sut,
        now="2026-09-22T00:01:01Z",
        required_artifacts_verified=True,
        host_status="running",
    )

    assert decision["action"] == "wait"
    assert decision["reason"] == "child_activity_in_progress"


def test_regression_case_phase1_children_bind_executable_lifecycle_controller():
    bootstrap = (REPO_ROOT / "core" / "agents" / "supervisor-bootstrap.md").read_text(
        encoding="utf-8"
    )

    for phase_kind in ("requirements", "brainstorm", "planning"):
        assert f"`{phase_kind}`" in bootstrap
    assert bootstrap.index("return block_before_dispatch now") < bootstrap.index(
        "Spawn through the proven adapter path"
    )
    assert "capture the returned host id" in bootstrap
    assert "stage_lifecycle.py path" in bootstrap
    assert "stage_lifecycle.py init" in bootstrap
    assert "stage_lifecycle.py event" in bootstrap
    assert "stage_lifecycle.py decide" in bootstrap
    assert "# stage_lifecycle.py init" not in bootstrap


def test_regression_case_supervisor_produces_explicit_stage_and_host_capability():
    stages = (REPO_ROOT / "core" / "agents" / "supervisor-stages.md").read_text(
        encoding="utf-8"
    )
    codex = (REPO_ROOT / "adapters" / "codex" / "invocation.md").read_text(
        encoding="utf-8"
    )
    claude = (REPO_ROOT / "adapters" / "claude" / "invocation.md").read_text(
        encoding="utf-8"
    )

    assert 'STAGE_KIND="implementation"' in stages
    assert 'HOST_CHILD_TIMEOUT_ENFORCEABLE="true"' in codex
    assert 'HOST_CHILD_TIMEOUT_ENFORCEABLE="false"' in codex
    assert "interruptBackgroundAgent" in claude
    assert 'HOST_CHILD_TIMEOUT_ENFORCEABLE="true"' in claude
    assert 'set the capability to `false`' in claude


def test_regression_case_docs_do_not_restore_blanket_no_status_retry():
    quality = (REPO_ROOT / "core" / "rules" / "quality-loop.md").read_text(
        encoding="utf-8"
    )
    run = (REPO_ROOT / "core" / "commands" / "run.md").read_text(encoding="utf-8")

    assert "no STATUS returned at all): retry up to **5 times**" not in quality
    assert "every no-STATUS outcome is a crash" not in run
    assert "explicit mutating" in quality
    assert "mutating supervisor" in run
    assert "mutating_or_unclassified_no_status" in run
    assert "decision.mutating == false" in run


def test_regression_case_readme_and_diagnostics_describe_stage_specific_defaults():
    readme = (REPO_ROOT / "core" / "scripts" / "README.md").read_text(
        encoding="utf-8"
    )
    diagnostics = (REPO_ROOT / "core" / "scripts" / "crew-diagnostics.py").read_text(
        encoding="utf-8"
    )

    assert "stage_lifecycle.py" in readme
    assert '"stage_timeout_policy": "stage_specific_defaults"' in diagnostics


def test_success_case_terminal_child_resumes_parent_immediately():
    sut = _state()
    stage_lifecycle.record_event(
        sut,
        event="terminal_completed",
        at="2026-09-22T00:00:01Z",
        reason="STATUS: completed",
    )

    decision = stage_lifecycle.decide_next_action(
        sut,
        now="2026-09-22T00:00:01Z",
    )

    assert decision == {
        "action": "resume_parent",
        "reason": "terminal_completed",
        "retry_allowed": False,
    }


def test_failure_case_no_artifact_and_no_terminal_cannot_succeed():
    sut = _state()

    decision = stage_lifecycle.decide_next_action(
        sut,
        now="2026-09-22T00:00:10Z",
        host_status="unknown",
    )

    assert decision["action"] == "wait"
    assert decision["reason"] == "terminal_and_artifact_pending"


@pytest.mark.parametrize("stage_kind", ["analysis", "planning", "qa", "reviewer"])
def test_boundary_case_verified_read_only_artifact_uses_bounded_terminal_grace(
    stage_kind: str,
):
    sut = _state(stage_kind=stage_kind)
    stage_lifecycle.record_event(
        sut,
        event="artifact_ready",
        at="2026-09-22T00:00:01Z",
        reason="required artifact verified",
    )

    decision = stage_lifecycle.decide_next_action(
        sut,
        now="2026-09-22T00:01:01Z",
        required_artifacts_verified=True,
        host_status="completed",
    )

    assert decision["action"] == "interrupt_and_accept_verified_artifact"
    assert decision["reason"] == "terminal_only_missing_after_verified_artifact"
    assert decision["retry_allowed"] is False


def test_failure_case_mutating_artifact_without_terminal_blocks_without_retry():
    sut = _state(stage_kind="implementation")
    stage_lifecycle.record_event(
        sut,
        event="artifact_ready",
        at="2026-09-22T00:00:01Z",
        reason="diff exists",
    )

    decision = stage_lifecycle.decide_next_action(
        sut,
        now="2026-09-22T00:01:01Z",
        required_artifacts_verified=True,
        host_status="completed",
    )

    assert decision["action"] == "interrupt_and_block"
    assert decision["reason"] == "mutating_terminal_missing_after_verified_artifact"
    assert decision["retry_allowed"] is False


def test_boundary_case_running_subprocess_prevents_early_interrupt():
    sut = _state(stage_kind="reviewer")
    stage_lifecycle.record_event(
        sut,
        event="artifact_ready",
        at="2026-09-22T00:00:01Z",
        reason="review draft exists",
    )

    decision = stage_lifecycle.decide_next_action(
        sut,
        now="2026-09-22T00:01:01Z",
        required_artifacts_verified=True,
        subprocess_running=True,
        host_status="running",
    )

    assert decision == {
        "action": "wait",
        "reason": "child_activity_in_progress",
        "retry_allowed": False,
    }


def test_failure_case_running_invocation_deadline_requests_interrupt():
    sut = _state(stage_kind="qa")

    decision = stage_lifecycle.decide_next_action(
        sut,
        now="2026-09-22T00:16:00Z",
        host_status="running",
    )

    assert decision["action"] == "interrupt_and_block"
    assert decision["reason"] == "stage_timeout"


def test_failure_case_uncancellable_host_fails_before_bounded_stage_start():
    sut = _state(stage_kind="qa", timeout_enforceable=False)

    decision = stage_lifecycle.preflight_action(sut)

    assert decision["action"] == "block_before_dispatch"
    assert decision["reason"] == "stage_timeout_unenforceable"


def test_regression_case_current_session_fallback_uses_same_state_machine():
    native = _state(stage_kind="reviewer", fallback_mode="native")
    fallback = _state(stage_kind="reviewer", fallback_mode="current_session")
    for sut in (native, fallback):
        stage_lifecycle.record_event(
            sut,
            event="artifact_ready",
            at="2026-09-22T00:00:01Z",
            reason="review artifact verified",
        )

    native_decision = stage_lifecycle.decide_next_action(
        native,
        now="2026-09-22T00:01:01Z",
        required_artifacts_verified=True,
        host_status="running",
    )
    fallback_decision = stage_lifecycle.decide_next_action(
        fallback,
        now="2026-09-22T00:01:01Z",
        required_artifacts_verified=True,
        host_status="running",
    )

    assert native_decision == fallback_decision


def test_regression_case_no_status_mutating_child_is_never_retried_from_scratch():
    sut = _state(stage_kind="test_writer")

    decision = stage_lifecycle.decide_next_action(
        sut,
        now="2026-09-22T00:20:01Z",
        host_status="error",
    )

    assert decision["retry_allowed"] is False
    assert decision["action"] == "interrupt_and_block"


def test_success_case_child_context_defaults_to_no_history():
    context = stage_lifecycle.build_child_context(
        task_dir="/tmp/task",
        project_root="/tmp/project",
        handoff_path="/tmp/task/handoff.md",
        acceptance_criteria=["AC-001"],
        skill_paths=["/tmp/skill.md"],
        verified_artifact_paths=["/tmp/task/context/prd.md"],
        branch="main",
        permissions=["workspace_write"],
    )

    assert context["fork_turns"] == "none"
    assert "conversation_history" not in context
    assert context["acceptance_criteria"] == ["AC-001"]


def test_failure_case_full_history_requires_reason_and_has_small_cap():
    with pytest.raises(ValueError, match="history_reason_required"):
        stage_lifecycle.build_child_context(
            task_dir="/tmp/task",
            project_root="/tmp/project",
            handoff_path="/tmp/task/handoff.md",
            acceptance_criteria=[],
            skill_paths=[],
            verified_artifact_paths=[],
            branch="main",
            permissions=[],
            history_turns=2,
        )

    with pytest.raises(ValueError, match="history_turn_limit_exceeded"):
        stage_lifecycle.build_child_context(
            task_dir="/tmp/task",
            project_root="/tmp/project",
            handoff_path="/tmp/task/handoff.md",
            acceptance_criteria=[],
            skill_paths=[],
            verified_artifact_paths=[],
            branch="main",
            permissions=[],
            history_turns=4,
            history_reason="needs recent approval decision",
        )


def test_success_case_small_bounded_policy_keeps_tdd_and_independent_review():
    policy = stage_lifecycle.bounded_lifecycle_policy(
        classification="bounded",
        requirements_complete=True,
        risk_tags=[],
    )

    assert policy["optimized"] is True
    assert policy["sequential_steps"] == [
        "bounded_design_and_plan",
        "tdd_controller",
        "independent_reviewer",
    ]
    assert policy["tdd_required"] is True
    assert policy["independent_review_required"] is True


@pytest.mark.parametrize(
    "classification,risk_tags",
    [
        ("architectural", []),
        ("bounded", ["security"]),
        ("bounded", ["migration"]),
        ("bounded", ["destructive"]),
    ],
)
def test_failure_case_high_risk_work_never_uses_bounded_fast_path(
    classification: str,
    risk_tags: list[str],
):
    policy = stage_lifecycle.bounded_lifecycle_policy(
        classification=classification,
        requirements_complete=True,
        risk_tags=risk_tags,
    )

    assert policy["optimized"] is False
    assert policy["tdd_required"] is True
    assert policy["independent_review_required"] is True


def test_success_case_state_records_phase_timing_terminal_reason_and_elapsed():
    sut = _state()
    stage_lifecycle.record_event(
        sut,
        event="first_output",
        at="2026-09-22T00:00:02Z",
        reason="first commentary",
    )
    stage_lifecycle.record_event(
        sut,
        event="artifact_ready",
        at="2026-09-22T00:00:04Z",
        reason="artifact verified",
    )
    stage_lifecycle.record_event(
        sut,
        event="terminal_completed",
        at="2026-09-22T00:00:06Z",
        reason="STATUS: completed",
    )
    stage_lifecycle.record_event(
        sut,
        event="parent_resume",
        at="2026-09-22T00:00:07Z",
        reason="stage accepted",
    )

    assert sut["timing"] == {
        "dispatched_at": "2026-09-22T00:00:00Z",
        "first_output_at": "2026-09-22T00:00:02Z",
        "artifact_ready_at": "2026-09-22T00:00:04Z",
        "terminal_at": "2026-09-22T00:00:06Z",
        "parent_resume_at": "2026-09-22T00:00:07Z",
    }
    assert sut["outcome"]["terminal_state"] == "terminal_completed"
    assert sut["outcome"]["terminal_reason"] == "STATUS: completed"
    assert sut["elapsed_seconds"]["total"] == 7.0


def test_regression_case_timeout_then_interrupt_preserves_both_outcome_flags():
    sut = _state(stage_kind="qa")
    stage_lifecycle.record_event(
        sut,
        event="timed_out",
        at="2026-09-22T00:15:00Z",
        reason="stage deadline reached",
    )
    stage_lifecycle.record_event(
        sut,
        event="interrupted",
        at="2026-09-22T00:15:01Z",
        reason="host child interrupted after timeout",
    )

    assert sut["outcome"]["timed_out"] is True
    assert sut["outcome"]["interrupted"] is True


def test_regression_case_foreground_background_contract_remains_unchanged():
    run_contract = (REPO_ROOT / "core" / "commands" / "run.md").read_text(
        encoding="utf-8"
    )

    assert "default execution policy is foreground" in run_contract
    assert 'crew:run --finalize-background' in run_contract


def test_regression_case_missing_lifecycle_artifact_is_valid_legacy_state(
    tmp_path: Path,
):
    missing_path = tmp_path / "context" / "stage-lifecycle" / "stage-1.json"

    assert stage_lifecycle.load_state(missing_path) is None


def test_failure_case_event_timestamps_cannot_move_backwards():
    sut = _state()
    stage_lifecycle.record_event(
        sut,
        event="first_output",
        at="2026-09-22T00:00:02Z",
        reason="first output",
    )

    with pytest.raises(ValueError, match="event_timestamp_regressed"):
        stage_lifecycle.record_event(
            sut,
            event="artifact_ready",
            at="2026-09-22T00:00:01Z",
            reason="invalid ordering",
        )


def test_success_case_duplicate_event_id_is_idempotent():
    sut = _state()
    stage_lifecycle.record_event(
        sut,
        event="first_output",
        at="2026-09-22T00:00:02Z",
        reason="first output",
        event_id="event-1",
    )

    stage_lifecycle.record_event(
        sut,
        event="first_output",
        at="2026-09-22T00:00:02Z",
        reason="first output",
        event_id="event-1",
    )

    assert len(sut["events"]) == 2


def test_success_case_atomic_write_round_trip(tmp_path: Path):
    path = tmp_path / "stage-1-backend.json"
    state = _state()

    stage_lifecycle.write_state_atomic(path, state)

    assert stage_lifecycle.load_state(path) == state
    assert json.loads(path.read_text(encoding="utf-8"))["agent"] == "backend"


def test_success_case_default_timeouts_are_bounded_and_stage_specific():
    assert stage_lifecycle.DEFAULT_TIMEOUT_SECONDS["requirements"] > 0
    assert stage_lifecycle.DEFAULT_TIMEOUT_SECONDS["planning"] > 0
    assert stage_lifecycle.DEFAULT_TIMEOUT_SECONDS["implementation"] > 0
    assert stage_lifecycle.DEFAULT_TIMEOUT_SECONDS["reviewer"] > 0
    assert len(set(stage_lifecycle.DEFAULT_TIMEOUT_SECONDS.values())) > 1


def test_regression_case_supervisor_runtime_invokes_lifecycle_helper():
    stages = (REPO_ROOT / "core" / "agents" / "supervisor-stages.md").read_text(
        encoding="utf-8"
    )
    retry = (REPO_ROOT / "core" / "agents" / "supervisor-retry.md").read_text(
        encoding="utf-8"
    )

    assert "stage_lifecycle.py init" in stages
    assert "stage_lifecycle.py event" in stages
    assert "stage_lifecycle.py decide" in retry
    assert "interrupt_and_accept_verified_artifact" in retry
    assert "mutating_terminal_missing_after_verified_artifact" in retry
    assert "must not re-invoke the mutating child from scratch" in retry


def test_regression_case_current_session_sop_reuses_native_lifecycle_artifact():
    sop = (
        REPO_ROOT / "core" / "docs" / "host-bridge-handoff-sop.md"
    ).read_text(encoding="utf-8")

    assert "stage_lifecycle.py" in sop
    assert "fallback-mode current_session" in sop
    assert "same provider-neutral lifecycle state" in sop


def test_regression_case_codex_adapter_binds_minimal_context_wait_and_interrupt():
    codex = (REPO_ROOT / "adapters" / "codex" / "invocation.md").read_text(
        encoding="utf-8"
    )

    assert 'fork_turns="none"' in codex
    assert "wait_agent" in codex
    assert "interrupt_agent" in codex
    assert "stage_timeout_unenforceable" in codex


def test_success_case_lifecycle_schema_exposes_required_timing_and_outcomes():
    schema = json.loads(
        (REPO_ROOT / "core" / "schemas" / "stage-lifecycle.schema.json").read_text(
            encoding="utf-8"
        )
    )
    timing = schema["properties"]["timing"]["properties"]
    outcome = schema["properties"]["outcome"]["properties"]

    for field in (
        "dispatched_at",
        "first_output_at",
        "artifact_ready_at",
        "terminal_at",
        "parent_resume_at",
    ):
        assert field in timing
    assert set(outcome["terminal_state"]["enum"]) >= {
        "terminal_completed",
        "terminal_blocked",
        "terminal_failed",
        "timed_out",
        "interrupted",
    }


def test_success_case_runtime_register_points_to_lifecycle_directory():
    runtime = (REPO_ROOT / "core" / "scripts" / "crew-runtime.py").read_text(
        encoding="utf-8"
    )
    register_schema = json.loads(
        (REPO_ROOT / "core" / "schemas" / "register.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert '"stage_lifecycle_dir"' in runtime
    assert "stage_lifecycle_dir" in register_schema["properties"]
