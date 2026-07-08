"""Tests for mandatory TDD/reviewer quality-loop evidence gates."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPAIR = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"
QUALITY_CHECK = REPO_ROOT / "core" / "scripts" / "quality-loop-check.py"
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"
QUALITY_LIB = SCRIPTS_DIR / "quality_loop_lib.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair_state = _load_module(REPAIR, "repair_task_state")
quality_loop = _load_module(QUALITY_LIB, "quality_loop_lib_under_test")


def make_task(tmp_path: Path, task: str) -> tuple[Path, str, Path]:
    state_dir = tmp_path / "state" / "project"
    task_id = "20260522-000000-0"
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({
            "task_id": task_id,
            "session_id": "20260522-000000",
            "task": task,
            "current_phase": "blocked",
            "blocked_by": ["host_bridge_not_invoked"],
        }),
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps({"stages": ["supervisor"], "completed_stages": 0}),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: blocked\n", encoding="utf-8")
    (task_dir / "progress.log").write_text("started\n", encoding="utf-8")
    return state_dir, task_id, task_dir


def write_test_checklist_artifacts(task_dir: Path) -> None:
    (task_dir / "context" / "test-checklist.md").write_text(
        "# Test Checklist\n\n"
        "| TC-ID | Category | Given | When | Then | Priority | MUST / SHOULD / SUGGESTION | Reason |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| TC-001 | Normal | a configured update gate | the gate runs | it accepts valid completion | P1 | MUST | Required behavior |\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "test-checklist-review.md").write_text(
        "REVIEW: APPROVED\n"
        "CHECKLIST_REVIEW_RESULT: approved\n"
        "- Missing MUST: none\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "test-case-mapping.md").write_text(
        "# Test Case Mapping\n\n"
        "| TC-ID | Test | Covered | Notes |\n"
        "|---|---|---|---|\n"
        "| TC-001 | tests/test_update_gate.py::test_update_gate_accepts_valid_completion | YES | Covers the normal case |\n",
        encoding="utf-8",
    )


def write_quality_loop_trace(task_dir: Path, *, include_test_file: bool = True) -> None:
    task_id = "20260522-000000-0"
    session_id = "20260522-000000"
    (task_dir / "pipeline.json").write_text(
        json.dumps({
            "schema_version": 1,
            "task": "Implement a new update gate",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 2,
        }),
        encoding="utf-8",
    )
    rows = [
        {
            "ts": "2026-05-22T00:00:00Z",
            "trace_id": f"{session_id}.{task_id}.1.1",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "test-writer",
            "attempt": 1,
            "status": "completed",
            "detail": "TDD RED GREEN REFACTOR, 3 tests passed",
            "files": ["tests/test_update_gate.py"] if include_test_file else [],
        },
        {
            "ts": "2026-05-22T00:00:01Z",
            "trace_id": f"{session_id}.{task_id}.1.1",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "backend",
            "attempt": 1,
            "status": "completed",
            "detail": "backend - N/A",
            "files": [],
        },
        {
            "ts": "2026-05-22T00:00:02Z",
            "trace_id": f"{session_id}.{task_id}.2.1",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STAGE_DONE",
            "stage": 2,
            "agent": "reviewer",
            "attempt": 1,
            "status": "completed",
            "detail": "reviewer - REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
            "files": [],
        },
    ]
    with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    (task_dir / "context" / "quality-metrics.json").write_text(
        json.dumps({
            "schema_version": 1,
            "hallucination_detected": False,
            "rollback_performed": False,
            "human_intervention_required": False,
            "factuality_review": "passed",
            "evidence_paths": ["context/review.md"],
        }),
        encoding="utf-8",
    )
    write_test_checklist_artifacts(task_dir)


def run_repair(state_dir: Path, task_id: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(REPAIR),
            "--state-dir",
            str(state_dir),
            "--status",
            "completed",
            "--note",
            "manual completion",
            *extra,
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def run_quality_loop_check(task_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(QUALITY_CHECK),
            "--task-dir",
            str(task_dir),
            *extra,
        ],
        text=True,
        capture_output=True,
    )


def test_repair_blocks_mutating_task_without_quality_loop_evidence(tmp_path: Path):
    state_dir, task_id, _task_dir = make_task(tmp_path, "Implement a new update gate")

    result = run_repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_quality_loop_evidence" in result.stderr


def test_repair_does_not_require_quality_loop_for_operational_git_update_closeout(tmp_path: Path):
    state_dir, task_id, task_dir = make_task(
        tmp_path,
        "Merge local changes, push origin/main, and update global agent-crew assets.",
    )
    register_path = task_dir / "register.json"
    register = json.loads(register_path.read_text(encoding="utf-8"))
    register["host_bridge_status"] = "current_session_required"
    register_path.write_text(json.dumps(register), encoding="utf-8")

    result = run_repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["required"] is False
    assert repair["required_capability_gate"]["advisory"] is True


def test_quality_gate_classifier_excludes_non_code_artifact_tasks():
    assert repair_state.looks_quality_gated_task("Implement a new update gate") is True
    assert repair_state.looks_quality_gated_task("Update API implementation") is True
    assert repair_state.looks_quality_gated_task("Update backend service") is True
    assert repair_state.looks_quality_gated_task("Update runtime code") is True
    assert repair_state.looks_quality_gated_task("Fix runtime bug") is True
    assert repair_state.looks_quality_gated_task("Fix backend service and commit changes") is True
    assert repair_state.looks_quality_gated_task("Update backend service and push") is True
    assert repair_state.looks_quality_gated_task("Fix API behavior and push changes") is True
    assert repair_state.looks_quality_gated_task("Fix documentation generator source code") is True
    assert repair_state.looks_quality_gated_task("Update documentation generator implementation") is True
    assert repair_state.looks_quality_gated_task("Fix README parser source code") is True
    assert repair_state.looks_quality_gated_task("Update report exporter source code") is True
    assert repair_state.looks_quality_gated_task("Fix changelog renderer code") is True
    assert repair_state.looks_quality_gated_task("Fix documentation generator") is True
    assert repair_state.looks_quality_gated_task("Create docs generator") is True
    assert repair_state.looks_quality_gated_task("Update report exporter") is True
    assert repair_state.looks_quality_gated_task("Fix README parser") is True
    assert repair_state.looks_quality_gated_task("Fix changelog renderer") is True
    assert repair_state.looks_quality_gated_task("Write README documentation") is False
    assert repair_state.looks_quality_gated_task("Edit docs only") is False
    assert repair_state.looks_quality_gated_task("Create release notes") is False
    assert repair_state.looks_quality_gated_task("Write CLI usage documentation") is False
    assert repair_state.looks_quality_gated_task("Edit runtime guide") is False
    assert repair_state.looks_quality_gated_task("Create backend architecture report") is False
    assert repair_state.looks_quality_gated_task("Write implementation guide") is False
    assert repair_state.looks_quality_gated_task("Create implementation report") is False
    assert repair_state.looks_quality_gated_task("Write documentation generator guide") is False
    assert repair_state.looks_quality_gated_task("Write source code documentation") is False
    assert repair_state.looks_quality_gated_task("Update source code docs") is False
    assert repair_state.looks_quality_gated_task("Update runtime assets source code") is True
    assert repair_state.looks_quality_gated_task("Update installed runtime assets") is False


def test_repair_classifier_shares_read_only_overrides_with_quality_loop():
    """success-case(regression) - TC-006 keeps repair read-only classifiers in sync."""
    read_only_tasks = (
        "Read-only review. Output sections: Must Fix, Should Fix.",
        "$review 코드리뷰. Must Fix / Should Fix 형식으로 보고.",
        "코드리뷰만 해줘, 수정하지 마.",
        "최근 bridge 개선한거 리뷰해줘.",
        "개선 우선순위 항목들을 더 면밀하게 분석 검토하고 구현 계획을 수립해.",
        "구현 계획만 수립해. 수정하지 마세요.",
        "어떤 commit 있어?",
        "what is the latest commit?",
    )

    for task in read_only_tasks:
        assert quality_loop.looks_mutating_task(task) is False
        assert repair_state.looks_mutating_task(task) is False
        assert repair_state.looks_quality_gated_task(task) is False


def test_repair_classifier_keeps_korean_exploration_and_complaints_read_only():
    """success-case(regression) - Korean exploration/meta complaints stay read-only."""
    # given
    read_only_tasks = (
        "ai가 최소구현만 해서 그런지 제대로 구현하는게 아니라 많이 비어있는 구현을 하는 양상을 개선 할 수 있는 방법을 모색해봐",
        "방법을 모색하라고 했는데 구현을 해버리네",
        "구현하지 말고 개선 방안만 모색해줘",
        "왜 구현을 했는지 분석해줘",
    )

    # when / then
    for task in read_only_tasks:
        assert quality_loop.looks_mutating_task(task) is False
        assert repair_state.looks_mutating_task(task) is False
        assert repair_state.looks_quality_gated_task(task) is False


def test_repair_classifier_keeps_korean_review_and_test_follow_up_mutating():
    """failure-case(regression) - Korean follow-up requests that run tests stay mutating."""
    # given
    task = "구현한거 리뷰하고 테스트해줘"

    # when / then
    assert quality_loop.looks_mutating_task(task) is True
    assert repair_state.looks_mutating_task(task) is True
    assert repair_state.looks_quality_gated_task(task) is True


def test_repair_classifier_keeps_korean_test_before_review_follow_up_mutating():
    """failure-case(regression) - Korean test-before-review follow-ups stay mutating."""
    # given
    task = "구현한거 테스트하고 리뷰해줘"

    # when / then
    assert quality_loop.looks_mutating_task(task) is True
    assert repair_state.looks_mutating_task(task) is True
    assert repair_state.looks_quality_gated_task(task) is True


def test_repair_classifier_keeps_korean_particle_test_execution_mutating():
    """failure-case(regression) - Korean test commands with particles stay mutating."""
    # given
    tasks = (
        "테스트도 해줘",
        "테스트를 돌려줘",
        "구현한거 리뷰하고 테스트도 해줘",
    )

    # when / then
    for task in tasks:
        assert quality_loop.looks_mutating_task(task) is True
        assert repair_state.looks_mutating_task(task) is True
        assert repair_state.looks_quality_gated_task(task) is True


def test_repair_classifier_keeps_korean_noun_form_test_execution_mutating():
    """failure-case(regression) - terse Korean noun-form test commands stay mutating."""
    # given
    tasks = (
        "테스트",
        "테스트만",
        "테스트 실행",
        "테스트 수행",
    )

    # when / then
    for task in tasks:
        assert quality_loop.looks_mutating_task(task) is True
        assert repair_state.looks_mutating_task(task) is True
        assert repair_state.looks_quality_gated_task(task) is True


def test_repair_classifier_keeps_korean_bare_imperative_test_execution_mutating():
    """failure-case(regression) - Korean bare imperative test commands stay mutating."""
    # given
    tasks = (
        "테스트해",
        "테스트 해",
        "테스트 돌려",
    )

    # when / then
    for task in tasks:
        assert quality_loop.looks_mutating_task(task) is True
        assert repair_state.looks_mutating_task(task) is True
        assert repair_state.looks_quality_gated_task(task) is True


def test_repair_classifier_keeps_korean_test_artifact_reviews_read_only():
    """failure-case(regression) - Korean test artifact reviews stay read-only."""
    # given
    tasks = (
        "테스트 결과 확인해줘",
        "테스트 로그 검토해줘",
    )

    # when / then
    for task in tasks:
        assert quality_loop.looks_mutating_task(task) is False
        assert repair_state.looks_mutating_task(task) is False
        assert repair_state.looks_quality_gated_task(task) is False


def test_repair_classifier_keeps_korean_test_subject_questions_read_only():
    """failure-case(regression) - Korean test subject questions stay read-only."""
    # given
    tasks = (
        "테스트하고 싶은데 방법 알려줘",
        "테스트해줘야 하는지 확인해줘",
    )

    # when / then
    for task in tasks:
        assert quality_loop.looks_mutating_task(task) is False
        assert repair_state.looks_mutating_task(task) is False
        assert repair_state.looks_quality_gated_task(task) is False


def test_repair_classifier_keeps_korean_past_or_negated_test_reviews_read_only():
    """failure-case(regression) - Korean past or negated test review requests stay read-only."""
    # given
    tasks = (
        "테스트해본 결과 확인해줘",
        "테스트해주지 말고 리뷰만 해줘",
        "테스트 돌리지 말고 리뷰만 해줘",
    )

    # when / then
    for task in tasks:
        assert quality_loop.looks_mutating_task(task) is False
        assert repair_state.looks_mutating_task(task) is False
        assert repair_state.looks_quality_gated_task(task) is False


def test_repair_does_not_require_quality_loop_for_documentation_only_task(tmp_path: Path):
    state_dir, task_id, task_dir = make_task(tmp_path, "Write README documentation")
    register_path = task_dir / "register.json"
    register = json.loads(register_path.read_text(encoding="utf-8"))
    register["host_bridge_status"] = "current_session_required"
    register_path.write_text(json.dumps(register), encoding="utf-8")

    result = run_repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["required"] is False


def test_repair_blocks_evidence_only_without_pipeline_quality_loop(tmp_path: Path):
    state_dir, task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    (task_dir / "context" / "tdd_log.md").write_text(
        "TDD: RED -> GREEN -> REFACTOR. tests passed 12.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: refactor review complete; post-refactor pytest passed.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json after refactor.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "quality-metrics.json").write_text(
        json.dumps({
            "schema_version": 1,
            "hallucination_detected": False,
            "rollback_performed": False,
            "human_intervention_required": False,
            "factuality_review": "passed",
            "evidence_paths": ["context/review.md"],
        }),
        encoding="utf-8",
    )

    result = run_repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_quality_loop_pipeline" in result.stderr
    assert "missing_pipeline_tdd_stage" in result.stderr


def test_repair_accepts_tdd_and_reviewer_evidence(tmp_path: Path):
    state_dir, task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir)
    (task_dir / "context" / "tdd_log.md").write_text(
        "TDD: RED -> GREEN -> REFACTOR. tests passed 12.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: refactor review complete; post-refactor pytest passed.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json after refactor.\n",
        encoding="utf-8",
    )

    result = run_repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["passed"] is True
    assert repair["quality_gate"]["tdd_evidence_paths"] == ["context/tdd-red.md", "context/tdd_log.md"]
    assert repair["quality_gate"]["red_phase_evidence_paths"] == ["context/tdd-red.md"]
    assert repair["quality_gate"]["green_phase_passed"] is True
    assert repair["quality_gate"]["refactor_phase_evidence_paths"] == ["context/tdd-refactor.md"]
    assert repair["quality_gate"]["refactor_phase_passed"] is True
    assert repair["quality_gate"]["review_evidence_paths"] == ["context/review.md"]
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "QUALITY_LOOP: passed" in result_text
    assert "PIPELINE_QUALITY_LOOP: passed" in result_text
    assert "TDD_GREEN_PHASE: passed" in result_text
    assert "TDD_EVIDENCE: context/tdd_log.md" in result_text
    assert "TDD_RED_EVIDENCE: context/tdd-red.md" in result_text
    assert "TDD_REFACTOR_EVIDENCE: context/tdd-refactor.md" in result_text
    assert "REVIEW_EVIDENCE: context/review.md" in result_text


def test_repair_accepts_pipeline_quality_outcomes_without_proof_files(tmp_path: Path):
    state_dir, task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir)

    result = run_repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["passed"] is True
    assert repair["quality_gate"]["tdd_outcome_source"] == "pipeline"
    assert repair["quality_gate"]["review_outcome_source"] == "pipeline"
    assert repair["quality_gate"]["red_phase_advisory"] is True
    assert repair["quality_gate"]["refactor_phase_advisory"] is True
    assert repair["quality_gate"]["tdd_evidence_paths"] == []
    assert repair["quality_gate"]["review_evidence_paths"] == []
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "QUALITY_LOOP: passed" in result_text
    assert "TDD_OUTCOME: pipeline" in result_text
    assert "REVIEW_OUTCOME: pipeline" in result_text
    assert "TDD_RED_PHASE: advisory" in result_text
    assert "TDD_REFACTOR_PHASE: advisory" in result_text


def test_repair_blocks_open_finding_register_entry(tmp_path: Path):
    state_dir, task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir)
    (task_dir / "context" / "tdd_log.md").write_text(
        "TDD: RED -> GREEN -> REFACTOR. tests passed 12.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: no-op refactor review complete; post-refactor pytest passed.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json after refactor.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "finding-register.json").write_text(
        json.dumps({
            "schema_version": 1,
            "findings": [
                {
                    "id": "F-open",
                    "title": "confirmed finding remains unresolved",
                    "severity": "P1",
                    "status": "open",
                    "source": {"artifact": "context/review.md"},
                    "affected": [{"file": "core/scripts/quality_loop_lib.py"}],
                    "recommended_fix": "move finding to a terminal status before completion",
                    "verification": {
                        "test_targets": [
                            "tests/python/test_quality_loop_gate.py::"
                            "test_repair_blocks_open_finding_register_entry",
                        ],
                    },
                }
            ],
        }),
        encoding="utf-8",
    )

    result = run_repair(state_dir, task_id)

    assert result.returncode != 0
    assert "unresolved_finding_register_entries" in result.stderr


def test_repair_records_explicit_quality_bypass_reason(tmp_path: Path):
    state_dir, task_id, task_dir = make_task(tmp_path, "Implement a new update gate")

    result = run_repair(
        state_dir,
        task_id,
        "--quality-bypass-reason",
        "emergency documentation-only repair; reviewer unavailable",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["bypassed"] is True
    assert repair["quality_gate"]["bypass_reason"] == "emergency documentation-only repair; reviewer unavailable"
    assert "QUALITY_LOOP: bypassed" in (task_dir / "result.md").read_text(encoding="utf-8")


def test_repair_helpers_cover_fallback_paths(tmp_path: Path):
    assert repair_state.load_json(tmp_path / "missing.json") == {}

    try:
        repair_state.resolve_task_dir(tmp_path / "state", "missing-task")
    except SystemExit as exc:
        assert "task not found" in str(exc)
    else:
        raise AssertionError("missing task should exit")

    repair_state.backup_result(tmp_path)
    paths = repair_state.resolve_quality_paths(tmp_path / "task", ["context/custom-review.md"])
    assert tmp_path / "task" / "context" / "custom-review.md" in paths

    rendered = repair_state.render_result(
        "Implement memory logging",
        "task-1",
        "completed",
        "done",
        "",
        ["context/evidence.md"],
        ["memory-1"],
        True,
    )

    assert "EVIDENCE: context/evidence.md" in rendered
    assert "MEMORY_IDS: memory-1" in rendered
    assert "MEMORY_CONTEXT_REUSED: yes" in rendered
    blocked = repair_state.render_result(
        "Implement memory logging",
        "task-1",
        "blocked",
        "",
        "manual_blocker",
        [],
        [],
        False,
    )
    assert "BLOCKER: manual_blocker" in blocked


def test_repair_json_format_outputs_repair_record(tmp_path: Path):
    state_dir, task_id, task_dir = make_task(tmp_path, "Read current status")

    result = run_repair(state_dir, task_id, "--format", "json")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["task_id"] == task_id
    assert payload["status"] == "completed"
    assert (task_dir / "context" / "manual-fallback-repair.json").is_file()


def test_quality_loop_check_rejects_missing_task_dir(tmp_path: Path):
    result = run_quality_loop_check(tmp_path / "missing")

    assert result.returncode == 2
    assert "quality-loop-check: task dir not found" in result.stderr


def test_quality_loop_check_text_reports_failures(tmp_path: Path):
    _state_dir, _task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    result = run_quality_loop_check(task_dir)

    assert result.returncode == 1
    assert "FAIL: pipeline quality loop" in result.stdout
    assert "- missing_pipeline_implementation_stage" in result.stdout


def test_quality_loop_check_target_status_enforces_pre_completion_gate(tmp_path: Path):
    _state_dir, _task_id, task_dir = make_task(tmp_path, "Implement a new update gate")

    result = run_quality_loop_check(task_dir, "--target-status", "completed")

    assert result.returncode == 1
    assert "- missing_pipeline_tdd_stage" in result.stdout


def test_quality_loop_check_requires_test_file_for_tdd_stage(tmp_path: Path):
    _state_dir, _task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir, include_test_file=False)
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    result = run_quality_loop_check(task_dir)

    assert result.returncode == 1
    assert "- missing_tdd_test_file" in result.stdout


def test_quality_loop_check_requires_test_checklist_artifacts_for_tdd_stage(tmp_path: Path):
    _state_dir, _task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir)
    (task_dir / "context" / "test-checklist.md").unlink()
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    result = run_quality_loop_check(task_dir)

    assert result.returncode == 1
    assert "- missing_test_checklist" in result.stdout


def test_quality_loop_check_requires_test_case_mapping_coverage(tmp_path: Path):
    _state_dir, _task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir)
    (task_dir / "context" / "test-case-mapping.md").write_text(
        "# Test Case Mapping\n\n| TC-ID | Test | Covered | Notes |\n|---|---|---|---|\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    result = run_quality_loop_check(task_dir)

    assert result.returncode == 1
    assert "- missing_test_case_mapping_coverage" in result.stdout


def test_quality_loop_check_rejects_must_mapping_without_test_or_exception(tmp_path: Path):
    _state_dir, _task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir)
    (task_dir / "context" / "test-case-mapping.md").write_text(
        "# Test Case Mapping\n\n"
        "| TC-ID | Test | Covered | Notes |\n"
        "|---|---|---|---|\n"
        "| TC-001 | N/A | NO | not implemented yet |\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    result = run_quality_loop_check(task_dir)

    assert result.returncode == 1
    assert "- missing_must_test_case_mapping" in result.stdout


def test_quality_loop_check_rejects_must_mapping_with_empty_test_reference(tmp_path: Path):
    _state_dir, _task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir)
    (task_dir / "context" / "test-case-mapping.md").write_text(
        "# Test Case Mapping\n\n"
        "| TC-ID | Test | Covered | Notes |\n"
        "|---|---|---|---|\n"
        "| TC-001 |  | YES | missing test reference |\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    result = run_quality_loop_check(task_dir)

    assert result.returncode == 1
    assert "- missing_must_test_case_mapping" in result.stdout


def test_checklist_only_reviewer_rejection_is_not_final_rework_rejection():
    checklist_row = {
        "agent": "reviewer",
        "detail": "MODE=test-checklist REVIEW: NEEDS_CHANGES CHECKLIST_REVIEW_RESULT: rejected",
    }
    final_row = {
        "agent": "reviewer",
        "detail": "REVIEW: NEEDS_CHANGES REPORT: context/review.md",
    }

    assert quality_loop.event_is_reviewer_rejected(checklist_row) is False
    assert quality_loop.event_is_reviewer_rejected(final_row) is True


def test_quality_loop_check_requires_tdd_red_and_refactor_artifacts(tmp_path: Path):
    _state_dir, _task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir)
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    result = run_quality_loop_check(task_dir)

    assert result.returncode == 0
    assert "PASS: pipeline quality loop" in result.stdout
    assert "WARNINGS: missing_tdd_red_phase_evidence, missing_tdd_refactor_phase_evidence" in result.stdout
    assert "- missing_tdd_red_phase_evidence" in result.stdout
    assert "- missing_tdd_refactor_phase_evidence" in result.stdout


def test_quality_loop_check_accepts_tdd_exception_without_test_file(tmp_path: Path):
    _state_dir, _task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    write_quality_loop_trace(task_dir, include_test_file=False)
    (task_dir / "context" / "tdd-exception.md").write_text(
        "TDD-EXCEPTION: no runnable test harness for this host-only regression.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: no-op refactor review complete; post-refactor verification passed.\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    result = run_quality_loop_check(task_dir)

    assert result.returncode == 0, result.stdout + result.stderr
