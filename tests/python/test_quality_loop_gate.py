"""Tests for mandatory TDD/reviewer quality-loop evidence gates."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPAIR = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"


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


def test_repair_blocks_mutating_task_without_quality_loop_evidence(tmp_path: Path):
    state_dir, task_id, _task_dir = make_task(tmp_path, "Implement a new update gate")

    result = run_repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_quality_loop_evidence" in result.stderr


def test_repair_accepts_tdd_and_reviewer_evidence(tmp_path: Path):
    state_dir, task_id, task_dir = make_task(tmp_path, "Implement a new update gate")
    (task_dir / "context" / "tdd_log.md").write_text(
        "TDD: RED -> GREEN -> REFACTOR. tests passed 12.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED after refactor.\n",
        encoding="utf-8",
    )

    result = run_repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["passed"] is True
    assert repair["quality_gate"]["tdd_evidence_paths"] == ["context/tdd_log.md"]
    assert repair["quality_gate"]["review_evidence_paths"] == ["context/review.md"]
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "QUALITY_LOOP: passed" in result_text
    assert "TDD_EVIDENCE: context/tdd_log.md" in result_text
    assert "REVIEW_EVIDENCE: context/review.md" in result_text


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
