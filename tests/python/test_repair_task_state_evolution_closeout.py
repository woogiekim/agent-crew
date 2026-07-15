"""Repair closeout coverage for self-evolution artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"


def _write_task(state_dir: Path, task_id: str, *, task: str = "Inspect project status") -> Path:
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({
            "schema_version": 1,
            "task_id": task_id,
            "session_id": task_id.rsplit("-", 1)[0],
            "task": task,
            "project_root": str(state_dir.parent / "repo"),
            "current_phase": "handoff_ready",
            "host_bridge_status": "current_session_required",
            "blocked_by": [],
        }) + "\n",
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps({"schema_version": 1, "stages": ["supervisor"], "completed_stages": 0}) + "\n",
        encoding="utf-8",
    )
    (task_dir / "progress.buffer.jsonl").write_text("", encoding="utf-8")
    (task_dir / "result.md").write_text("STATUS: handoff_ready\n", encoding="utf-8")
    return task_dir


def _write_skill_depth_report(task_dir: Path, candidate_name: str = "skill-content-hardening") -> None:
    (task_dir / "context" / "evolution-report.json").write_text(
        json.dumps({
            "schema_version": 1,
            "task_id": task_dir.name,
            "generation_mode": "report_only",
            "meaningful": True,
            "observed_patterns": [{
                "kind": "skill_content_depth",
                "summary": "Skill content audit found shallow skill material.",
                "evidence_refs": ["context/skill-content-audit.json"],
            }],
            "asset_candidates": [],
            "rejected_candidates": [{
                "asset_type": "skill",
                "name": candidate_name,
                "rejection_reason": "insufficient_repeated_evidence",
            }],
        }) + "\n",
        encoding="utf-8",
    )


def test_completed_repair_runs_evolution_closeout_and_surfaces_pending_proposals(tmp_path: Path):
    state_dir = tmp_path / "state"
    previous = _write_task(state_dir, "20260101-120000-0")
    _write_skill_depth_report(previous)

    task_id = "20260102-120000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "skill-content-audit.json").write_text(
        json.dumps({
            "shallow_findings": [{"skill": "example", "reason": "thin"}],
            "effective_followups": [],
        }) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state-dir", str(state_dir),
            "--status", "completed",
            "--note", "manual completion",
            task_id,
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (task_dir / "context" / "evolution-report.json").is_file()
    assert (task_dir / "context" / "evolution-report.md").is_file()
    summary = task_dir / "context" / "evolution-proposals-summary.txt"
    assert summary.is_file()
    assert "SELF_EVOLUTION_PROPOSALS: 1 pending" in summary.read_text(encoding="utf-8")
    assert "Self-Evolution Proposals" in (task_dir / "result.md").read_text(encoding="utf-8")

    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["evolution_closeout"]["analyzer"] == "completed"
    assert repair["evolution_closeout"]["pending_proposals"] == 1
