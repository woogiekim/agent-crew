"""Tests for readiness gate blocker reporting."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "readiness-gate.py"


def test_readiness_gate_passes_with_default_thresholds_and_local_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260101-120000-0"
    task_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({"current_phase": "completed", "host_bridge_status": "auto_completed"}),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"passed": True}), encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--validation-report",
            str(validation),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["blockers"] == []
    assert payload["thresholds"]["task_success_rate"] == 0.95


def test_readiness_gate_reports_missing_validation_and_unmeasured_workload(tmp_path: Path):
    result = subprocess.run(
        ["python3", str(SCRIPT), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    blocker_ids = {blocker["id"] for blocker in payload["blockers"]}
    assert "missing_validation_report" in blocker_ids
    assert "unmeasured:host_bridge_completion_rate" in blocker_ids
    assert payload["passed"] is False


def test_readiness_gate_includes_direct_agent_requests_in_generated_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260101-120000-0"
    request_dir = state_dir / "agent-requests" / "agent-20260101-120100-0"
    task_dir.mkdir(parents=True)
    request_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({"current_phase": "completed", "host_bridge_status": "auto_completed"}),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")
    (request_dir / "request.json").write_text(
        json.dumps({"status": "auto_completed", "agent": "analyst", "host_bridge_status": "auto_completed"}),
        encoding="utf-8",
    )
    (request_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"passed": True}), encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--include-agent-requests",
            "--validation-report",
            str(validation),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["metrics"]["totals"]["tasks"] == 2
    assert payload["metrics"]["totals"]["host_bridge_completed"] == 2
