"""Tests for pipeline-level TDD/reviewer quality-loop validation."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO_ROOT / "core" / "scripts" / "quality-loop-check.py"
REPORT_CHECK = REPO_ROOT / "core" / "scripts" / "report-quality-check.py"
QUALITY_LIB = REPO_ROOT / "core" / "scripts" / "quality_loop_lib.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


quality_loop = _load_module(QUALITY_LIB, "quality_loop_lib")


def write_task(task_dir: Path, rows: list[dict], pipeline: dict | None = None) -> None:
    task_dir.mkdir(parents=True)
    (task_dir / "context").mkdir()
    (task_dir / "register.json").write_text(
        json.dumps({
            "task_id": "20260522-000000-0",
            "session_id": "20260522-000000",
            "task": "Implement production quality-loop behavior",
            "current_phase": "completed",
        }),
        encoding="utf-8",
    )
    pipeline_payload = {
        "schema_version": 1,
        "task": "Implement production quality-loop behavior",
        "stages": [
            {"agents": ["backend"], "tdd_parallel": True},
            "reviewer",
        ],
        "completed_stages": 2,
    }
    if pipeline is not None:
        pipeline_payload = pipeline

    (task_dir / "pipeline.json").write_text(
        json.dumps(pipeline_payload),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text(
        "STATUS: completed\n"
        "MEASUREMENTS: 6 tests passed, 1 retry\n"
        "EVIDENCE: context/tdd_log.md\n"
        "EVIDENCE: context/review.md\n"
        "UNCERTAINTY: Unknown runtime variance remains.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd_log.md").write_text(
        "TDD: RED -> GREEN -> REFACTOR. tests passed 6.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused test failed as expected before implementation.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: no-op refactor review complete; post-refactor verification passed.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json after remediation.\n",
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
    with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def row(event: str, agent: str, detail: str, *, stage: int, attempt: int = 1) -> dict:
    return {
        "ts": f"2026-05-22T00:00:0{min(stage + attempt, 9)}Z",
        "trace_id": f"20260522-000000.20260522-000000-0.{stage}.{attempt}",
        "task_id": "20260522-000000-0",
        "session_id": "20260522-000000",
        "event": event,
        "stage": stage,
        "agent": agent,
        "attempt": attempt,
        "status": "completed",
        "detail": detail,
        "files": ["tests/test_quality_loop_pipeline.py"] if agent == "test-writer" else [],
    }


def write_finding_register(task_dir: Path, findings: list[dict]) -> None:
    (task_dir / "context" / "finding-register.json").write_text(
        json.dumps({"schema_version": 1, "findings": findings}),
        encoding="utf-8",
    )


def run_checker(task_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(CHECKER), "--task-dir", str(task_dir), "--format", "json", *extra],
        text=True,
        capture_output=True,
    )


def test_quality_loop_checker_blocks_reviewer_rejection_without_rework(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN REFACTOR, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: NEEDS_CHANGES", stage=2),
        ],
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_pipeline_reviewer_approval" in payload["failures"]
    assert "missing_rework_after_review_rejection" in payload["failures"]


def test_quality_loop_checker_blocks_missing_delegation_fidelity_evidence(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN REFACTOR, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
        pipeline={
            "schema_version": 1,
            "task": "Implement production quality-loop behavior",
            "requires_delegation_fidelity": True,
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 2,
        },
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_delegation_fidelity_evidence" in payload["failures"]
    assert "missing_tool_event_fidelity_evidence" in payload["failures"]


def test_quality_loop_checker_blocks_missing_human_acceptance_matrix(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN REFACTOR, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
        pipeline={
            "schema_version": 1,
            "task": "Implement user-facing workflow",
            "requires_human_acceptance": True,
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 2,
        },
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_human_acceptance_matrix" in payload["failures"]


def test_quality_loop_checker_blocks_missing_edd_metrics(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN REFACTOR, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
        pipeline={
            "schema_version": 1,
            "task": "Implement agentic evaluation workflow",
            "eval_command": "python3 evals/run.py",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 2,
        },
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_evaluation_metrics" in payload["failures"]


def test_quality_loop_checker_blocks_multi_agent_tdd_stage(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "frontend", "frontend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
        pipeline={
            "schema_version": 1,
            "task": "Implement production quality-loop behavior",
            "stages": [
                {"agents": ["backend", "frontend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 2,
        },
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_pipeline_tdd_stage" in payload["failures"]


def test_quality_loop_checker_blocks_rework_on_wrong_stage(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: NEEDS_CHANGES", stage=2),
            row("STAGE_DONE", "test-writer", "TDD REFACTOR, 6 tests passed", stage=3, attempt=2),
            row("STAGE_DONE", "backend", "backend remediation - N/A", stage=3, attempt=2),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2, attempt=2),
        ],
    )

    result = run_checker(task_dir, "--require-rework-cycle")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_rework_after_review_rejection" in payload["failures"]
    assert payload["rejection_followups"][0]["target_implementation_stage"] == 1
    assert payload["rejection_followups"][0]["implementer_retry"] is False
    assert payload["rejection_followups"][0]["tdd_retry"] is False


def test_quality_loop_checker_blocks_stale_attempt_rework(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: NEEDS_CHANGES", stage=2),
            row("STAGE_DONE", "test-writer", "TDD REFACTOR, 6 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend remediation - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2, attempt=2),
        ],
    )

    result = run_checker(task_dir, "--require-rework-cycle")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_rework_after_review_rejection" in payload["failures"]
    assert payload["rejection_followups"][0]["implementer_retry"] is False
    assert payload["rejection_followups"][0]["tdd_retry"] is False


def test_quality_loop_checker_requires_rework_cycle_when_requested(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
    )

    result = run_checker(task_dir, "--require-rework-cycle")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_rework_cycle" in payload["failures"]


def test_quality_loop_checker_blocks_implementation_stage_without_immediate_reviewer(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=2),
            row("STAGE_DONE", "frontend", "frontend - N/A", stage=2),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=3),
        ],
        pipeline={
            "schema_version": 1,
            "task": "Implement production full-stack behavior",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                {"agents": ["frontend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 3,
        },
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_pipeline_reviewer_after_each_implementer" in payload["failures"]
    assert payload["pipeline_shape"]["implementer_indexes_without_immediate_reviewer"] == [0]


def test_quality_loop_checker_accepts_qa_verify_quality_gate(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "qa-owner", "QA_STATUS: passed", stage=1),
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=2),
            row("STAGE_DONE", "backend", "backend - N/A", stage=2),
            row("STAGE_DONE", "qa-owner", "QA_STATUS: passed", stage=3),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=4),
        ],
        pipeline={
            "schema_version": 1,
            "task": "Implement production behavior with QA validation",
            "stages": [
                {"agents": ["qa-owner"], "qa_mode": "plan"},
                {"agents": ["backend"], "tdd_parallel": True},
                {
                    "agents": ["qa-owner"],
                    "qa_mode": "verify",
                    "qa_loop_target": "previous_implementation",
                },
                "reviewer",
            ],
            "completed_stages": 4,
        },
    )

    result = run_checker(task_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["pipeline_shape"]["qa_verify_indexes"] == [2]
    assert payload["pipeline_shape"]["has_quality_gate_after_each_implementer"] is True


def test_quality_loop_checker_blocks_open_finding_register_entries(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row(
                "STAGE_DONE",
                "reviewer",
                "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
                stage=2,
            ),
        ],
    )
    write_finding_register(
        task_dir,
        [
            {
                "id": "F-duplicate-nickname-self-exclude",
                "title": "nickname duplicate guard lacks self-exclude",
                "severity": "P1",
                "status": "open",
                "source": {"artifact": "context/review.md"},
                "affected": [
                    {
                        "file": "BylineReviewProfileCommandService.kt",
                        "function": "upsert",
                    }
                ],
                "recommended_fix": "exclude the current profile id from duplicate checks",
                "verification": {
                    "test_targets": [
                        "BylineReviewProfileCommandServiceTest::resaves existing nickname",
                    ],
                },
            }
        ],
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "unresolved_finding_register_entries" in payload["failures"]
    assert payload["finding_register"]["open_ids"] == ["F-duplicate-nickname-self-exclude"]


def test_quality_loop_checker_blocks_terminal_finding_without_test_mapping(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row(
                "STAGE_DONE",
                "reviewer",
                "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
                stage=2,
            ),
        ],
    )
    write_finding_register(
        task_dir,
        [
            {
                "id": "F-coverage-gap",
                "title": "confirmed finding was fixed without linked verification",
                "severity": "P1",
                "status": "fixed",
                "source": {"artifact": "context/review.md"},
                "affected": [{"file": "core/scripts/quality_loop_lib.py"}],
                "recommended_fix": "link the focused regression test",
                "verification": {},
            }
        ],
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_finding_test_mapping" in payload["failures"]
    assert payload["finding_register"]["missing_test_mapping_ids"] == ["F-coverage-gap"]


def test_quality_loop_checker_blocks_invalid_finding_register_status(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row(
                "STAGE_DONE",
                "reviewer",
                "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
                stage=2,
            ),
        ],
    )
    write_finding_register(
        task_dir,
        [
            {
                "id": "F-invalid-status",
                "title": "finding has an unsupported status",
                "severity": "P2",
                "status": "resolved-ish",
                "source": {"artifact": "context/review.md"},
                "affected": [{"file": "core/scripts/quality_loop_lib.py"}],
                "recommended_fix": "use one of the documented statuses",
                "verification": {"test_targets": "tests/python/test_quality_loop_pipeline_check.py"},
            }
        ],
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "invalid_finding_register" in payload["failures"]
    assert payload["finding_register"]["unknown_status_ids"] == ["F-invalid-status"]


def test_quality_loop_checker_blocks_terminal_scope_status_without_owner(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row(
                "STAGE_DONE",
                "reviewer",
                "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
                stage=2,
            ),
        ],
    )
    write_finding_register(
        task_dir,
        [
            {
                "id": "F-out-of-scope",
                "title": "scoped-out finding lacks follow-up metadata",
                "severity": "P2",
                "status": "out-of-scope",
                "source": {"artifact": "context/review.md"},
                "affected": [{"file": "core/agents/reviewer.md"}],
                "recommended_fix": "record owner or follow-up",
                "verification": {
                    "test_exception": "scope decision is verified by review artifact",
                },
            }
        ],
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_finding_owner_or_followup" in payload["failures"]
    assert payload["finding_register"]["missing_owner_or_followup_ids"] == ["F-out-of-scope"]


def test_quality_loop_checker_accepts_terminal_findings_with_test_mapping_or_exception(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row(
                "STAGE_DONE",
                "reviewer",
                "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
                stage=2,
            ),
        ],
    )
    write_finding_register(
        task_dir,
        [
            {
                "id": "F-fixed-with-test",
                "title": "fixed finding includes focused verification",
                "severity": "P1",
                "status": "fixed",
                "source": {"artifact": "context/review.md"},
                "affected": [{"file": "core/scripts/quality_loop_lib.py"}],
                "recommended_fix": "enforce register status",
                "verification": {
                    "test_targets": [
                        "tests/python/test_quality_loop_pipeline_check.py::"
                        "test_quality_loop_checker_blocks_open_finding_register_entries",
                    ],
                },
            },
            {
                "id": "F-accepted-risk-with-exception",
                "title": "accepted risk has an explicit verification exception",
                "severity": "P2",
                "status": "accepted-risk",
                "source": {"artifact": "context/review.md"},
                "affected": [{"file": "core/agents/reviewer.md"}],
                "recommended_fix": "document accepted scope with owner",
                "verification": {
                    "test_exception": "Documentation-only reviewer guidance is verified by markdown review.",
                },
                "owner": "reviewer",
            },
        ],
    )

    result = run_checker(task_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["finding_register"]["terminal_count"] == 2


def test_quality_loop_checker_reloops_reviewer_after_qa_to_implementation(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "qa-owner", "QA_STATUS: planned", stage=1),
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=2),
            row("STAGE_DONE", "backend", "backend - N/A", stage=2),
            row("STAGE_DONE", "qa-owner", "QA_STATUS: passed", stage=3),
            row("STAGE_DONE", "reviewer", "REVIEW: NEEDS_CHANGES", stage=4),
            row("STAGE_DONE", "test-writer", "TDD REFACTOR, 5 tests passed", stage=2, attempt=2),
            row("STAGE_DONE", "backend", "backend remediation - N/A", stage=2, attempt=2),
            row("STAGE_DONE", "qa-owner", "QA_STATUS: passed", stage=3, attempt=2),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=4, attempt=2),
        ],
        pipeline={
            "schema_version": 1,
            "task": "Implement production behavior with QA validation",
            "stages": [
                {"agents": ["qa-owner"], "qa_mode": "plan"},
                {"agents": ["backend"], "tdd_parallel": True},
                {
                    "agents": ["qa-owner"],
                    "qa_mode": "verify",
                    "qa_loop_target": "previous_implementation",
                },
                "reviewer",
            ],
            "completed_stages": 4,
        },
    )

    result = run_checker(task_dir, "--require-rework-cycle")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["rejection_followups"][0]["target_implementation_stage"] == 2
    assert payload["rejection_followups"][0]["ordered"] is True


def test_quality_loop_checker_accepts_rework_and_reapproval(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: NEEDS_CHANGES", stage=2),
            row("STAGE_DONE", "test-writer", "TDD REFACTOR, 6 tests passed", stage=1, attempt=2),
            row("STAGE_DONE", "backend", "backend remediation - N/A", stage=1, attempt=2),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2, attempt=2),
        ],
    )

    result = run_checker(task_dir, "--require-rework-cycle")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["rejection_followups"][0]["ordered"] is True
    assert payload["reviewer_approval_count"] == 1


def test_quality_loop_checker_blocks_approval_without_quality_metrics_file(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row(
                "STAGE_DONE",
                "reviewer",
                "REVIEW: APPROVED QUALITY_METRICS: context/missing-quality-metrics.json",
                stage=2,
            ),
        ],
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_reviewer_quality_metrics_artifact" in payload["failures"]
    assert "missing_pipeline_reviewer_approval" in payload["failures"]
    assert payload["reviewer_approved_without_quality_metrics_count"] == 1
    assert payload["reviewer_quality_metrics_errors"] == ["missing_quality_metrics_artifact"]


def test_quality_loop_checker_blocks_malformed_quality_metrics_artifact(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
    )
    (task_dir / "context" / "quality-metrics.json").write_text("{not json", encoding="utf-8")

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "invalid_reviewer_quality_metrics_artifact" in payload["failures"]
    assert "missing_pipeline_reviewer_approval" in payload["failures"]
    assert payload["reviewer_quality_metrics_errors"] == ["malformed_quality_metrics_json"]


def test_quality_loop_checker_blocks_schema_invalid_quality_metrics_artifact(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(
        task_dir,
        [
            row("STAGE_DONE", "test-writer", "TDD RED GREEN, 3 tests passed", stage=1),
            row("STAGE_DONE", "backend", "backend - N/A", stage=1),
            row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
    )
    (task_dir / "context" / "quality-metrics.json").write_text(
        json.dumps({
            "schema_version": 2,
            "hallucination_detected": "no",
            "factuality_review": "maybe",
            "extra": True,
        }),
        encoding="utf-8",
    )

    result = run_checker(task_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "invalid_reviewer_quality_metrics_artifact" in payload["failures"]
    assert "missing_pipeline_reviewer_approval" in payload["failures"]
    assert set(payload["reviewer_quality_metrics_errors"]) == {
        "invalid_quality_metrics_factuality_review",
        "invalid_quality_metrics_hallucination_detected",
        "invalid_quality_metrics_schema_version",
        "unexpected_quality_metrics_fields",
    }


def test_quality_loop_library_helpers_cover_schema_and_path_edges(tmp_path: Path):
    assert quality_loop.load_json(tmp_path) == {}
    assert quality_loop.load_text(tmp_path) == ""

    jsonl = tmp_path / "events.jsonl"
    jsonl.write_text("not json\n" + json.dumps({"event": "ok"}) + "\n", encoding="utf-8")
    assert quality_loop.load_jsonl(tmp_path / "missing.jsonl") == []
    assert quality_loop.load_jsonl(jsonl) == [{"event": "ok"}]
    assert quality_loop.stage_agents({"agents": "backend"}) == []
    assert quality_loop.is_tdd_capable_stage(["test-writer"]) is True
    assert quality_loop.is_completed("completed", {}, "") is True

    absolute = tmp_path / "quality.json"
    assert quality_loop.resolve_event_quality_metrics_path("", tmp_path) is None
    assert quality_loop.resolve_event_quality_metrics_path(str(absolute), None) == absolute
    assert quality_loop.resolve_event_quality_metrics_path("quality.json", tmp_path) == tmp_path / "quality.json"

    assert quality_loop.quality_metrics_schema_errors(tmp_path) == [
        "unreadable_quality_metrics_artifact"
    ]
    array_metrics = tmp_path / "array.json"
    array_metrics.write_text("[]", encoding="utf-8")
    assert quality_loop.quality_metrics_schema_errors(array_metrics) == ["quality_metrics_not_object"]

    invalid = tmp_path / "invalid-quality.json"
    invalid.write_text(
        json.dumps({
            "schema_version": 1,
            "hallucination_detected": False,
            "rollback_performed": False,
            "human_intervention_required": False,
            "factuality_review": "passed",
            "evidence_paths": [42],
            "notes": [],
        }),
        encoding="utf-8",
    )
    assert set(quality_loop.quality_metrics_schema_errors(invalid)) == {
        "invalid_quality_metrics_evidence_paths",
        "invalid_quality_metrics_notes",
    }

    assert quality_loop.event_quality_metrics_errors({"detail": "REVIEW: APPROVED"}, tmp_path) == [
        "missing_quality_metrics_pointer"
    ]
    assert quality_loop.event_stage({"stage": "x"}) is None
    assert quality_loop.event_attempt({"attempt": "x"}) == 0
    assert quality_loop.task_description(tmp_path, {}, {"task": "Pipeline task"}, "") == "Pipeline task"
    assert quality_loop.task_description(tmp_path, {}, {}, "# Result heading\n") == "Result heading"


def test_quality_loop_library_reports_missing_required_pipeline_and_events(tmp_path: Path):
    missing_pipeline = tmp_path / "missing-pipeline"
    write_task(missing_pipeline, [], pipeline={})

    result = quality_loop.check_quality_loop(missing_pipeline)

    assert "missing_pipeline" in result["failures"]
    assert "missing_pipeline_implementation_stage" in result["failures"]
    assert "missing_pipeline_reviewer_stage" in result["failures"]
    assert "missing_pipeline_reviewer_after_implementer" in result["failures"]
    assert "missing_progress_events" in result["failures"]

    missing_events = tmp_path / "missing-events"
    write_task(
        missing_events,
        [
            row(
                "STAGE_DONE",
                "reviewer",
                "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
                stage=1,
            )
        ],
        pipeline={"schema_version": 1, "stages": ["reviewer"]},
    )

    event_result = quality_loop.check_quality_loop(missing_events)

    assert "missing_pipeline_implementation_completion" in event_result["failures"]
    assert "missing_pipeline_tdd_event" in event_result["failures"]


def test_report_quality_fails_when_only_evidence_files_exist(tmp_path: Path):
    task_dir = tmp_path / "task"
    write_task(task_dir, [])

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(task_dir / "result.md"),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_progress_events" in payload["failures"]
