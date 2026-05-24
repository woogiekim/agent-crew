"""Tests for pipeline-level TDD/reviewer quality-loop validation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO_ROOT / "core" / "scripts" / "quality-loop-check.py"
REPORT_CHECK = REPO_ROOT / "core" / "scripts" / "report-quality-check.py"


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
    (task_dir / "pipeline.json").write_text(
        json.dumps(pipeline or {
            "schema_version": 1,
            "task": "Implement production quality-loop behavior",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 2,
        }),
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
        "files": [],
    }


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
