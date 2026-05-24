"""Tests for commercialization readiness metric aggregation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "readiness-metrics.py"


def test_readiness_metrics_reports_requested_decision_metrics(tmp_path: Path):
    validation_one = tmp_path / "phase-1.json"
    validation_two = tmp_path / "phase-2.json"
    workload = tmp_path / "hosted.json"
    thresholds = tmp_path / "thresholds.json"

    validation_one.write_text(json.dumps({"passed": True}), encoding="utf-8")
    validation_two.write_text(json.dumps({"passed": True}), encoding="utf-8")
    workload.write_text(
        json.dumps({
            "tasks": 10,
            "successes": 9,
            "host_bridge_completed": 9,
            "manual_repairs": 0,
            "retries": 1,
        }),
        encoding="utf-8",
    )
    thresholds.write_text(
        json.dumps({
            "consecutive_clean_full_validation_runs": 2,
            "host_bridge_completion_rate": 0.9,
            "human_intervention_rate": 0.0,
            "retry_rate": 0.1,
            "task_success_rate": 0.9,
        }),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--validation-report",
            str(validation_one),
            "--validation-report",
            str(validation_two),
            "--workload-evidence",
            str(workload),
            "--thresholds",
            str(thresholds),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    metrics = {metric["id"]: metric for metric in payload["metrics"]}
    assert set(metrics) == {
        "consecutive_clean_full_validation_runs",
        "host_bridge_completion_rate",
        "human_intervention_rate",
        "retry_rate",
        "task_success_rate",
    }
    assert metrics["consecutive_clean_full_validation_runs"]["value"] == 2
    assert metrics["host_bridge_completion_rate"]["value"] == 0.9
    assert payload["passed"] is True


def test_readiness_metrics_fails_when_threshold_not_met(tmp_path: Path):
    validation = tmp_path / "phase-2.json"
    workload = tmp_path / "hosted.json"
    thresholds = tmp_path / "thresholds.json"
    validation.write_text(json.dumps({"passed": False}), encoding="utf-8")
    workload.write_text(json.dumps({"tasks": 4, "successes": 2}), encoding="utf-8")
    thresholds.write_text(
        json.dumps({
            "consecutive_clean_full_validation_runs": 1,
            "task_success_rate": 0.9,
        }),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--validation-report",
            str(validation),
            "--workload-evidence",
            str(workload),
            "--thresholds",
            str(thresholds),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "needs_attention task_success_rate" in result.stdout
