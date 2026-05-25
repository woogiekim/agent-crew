"""Tests for round 2 persistent workflow operational chaos coverage."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECK = REPO_ROOT / "core" / "scripts" / "persistent-workflow-chaos-check.py"
FIXTURE = REPO_ROOT / "core" / "evaluations" / "persistent-workflow-chaos.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


chaos_check = _load_module(CHECK, "persistent_workflow_chaos_check")


def test_persistent_workflow_chaos_check_passes():
    result = subprocess.run(
        ["python3", str(CHECK), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["chaos_covered"] == 7


def test_persistent_workflow_chaos_fixture_covers_required_chaos_and_metrics():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert fixture["round"] == 2
    assert set(fixture["chaos_requirements"]) == chaos_check.REQUIRED_CHAOS
    assert set(fixture["success_metrics"]) == chaos_check.REQUIRED_METRICS
    assert {case["id"] for case in fixture["cases"]} == {
        "process_crash_resume_success",
        "runtime_restart_approval_pause",
        "token_exhaustion_partial_replay",
        "plugin_failure_isolated",
        "partial_persistence_failure_safe_block",
        "memory_corruption_recovery_blocks",
        "infrastructure_interruption_rehydrate",
    }


def test_persistent_workflow_chaos_metrics_are_derived_from_cases():
    payload = chaos_check.evaluate(FIXTURE)

    assert payload["metrics"]["Resume Success Rate"] == 1.0
    assert payload["metrics"]["Workflow Survival Rate"] == 1.0
    assert payload["metrics"]["Approval Integrity"] == 1.0
    assert payload["metrics"]["Deterministic Stability"] == 1.0
    assert payload["metrics"]["Workflow Continuity Score"] >= 0.9


def test_persistent_workflow_chaos_fails_on_unsafe_approval_bypass(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    case = fixture["cases"][1]
    case["events"][-1]["status"] = "executed"
    case["expected"]["unsafe_execution"] = False
    path = tmp_path / "unsafe.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    payload = chaos_check.evaluate(path)

    assert payload["passed"] is False
    assert "Approval Integrity" in "".join(str(failure) for failure in payload["failures"])
    assert "unsafe_execution" in "".join(str(failure) for failure in payload["failures"])


def test_persistent_workflow_chaos_fails_when_metric_is_missing(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["success_metrics"].remove("Workflow Continuity Score")
    path = tmp_path / "missing-metric.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    payload = chaos_check.evaluate(path)

    assert payload["passed"] is False
    assert payload["error_type"] == "invalid_fixture"
    assert "success metrics" in payload["failures"][0]
