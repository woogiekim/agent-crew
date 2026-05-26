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


def test_persistent_workflow_chaos_helpers_cover_invalid_json_and_edges(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert chaos_check.load_json(invalid)[0] is None
    assert chaos_check.evaluate(invalid)["error_type"] == "invalid_fixture"

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert chaos_check.load_json(array) == (None, "fixture root must be an object")

    assert chaos_check.transition_failures([]) == ["missing_state_sequence"]
    assert "unknown_state:UNKNOWN" in chaos_check.transition_failures(["UNKNOWN", "COMPLETED"])
    assert "invalid_transition:PLANNING->COMPLETED" in chaos_check.transition_failures(["PLANNING", "COMPLETED"])
    assert "non_terminal_final_state:PLANNING" in chaos_check.transition_failures(["PLANNING"])
    assert chaos_check.has_observability_trace([]) is False
    assert chaos_check.metric_value("Resume Success Rate", []) == 0.0
    assert chaos_check.metric_value("Resume Success Rate", [{"chaos": [], "observed": {}}]) == 0.0
    assert chaos_check.metric_value("unknown", [{"chaos": [], "observed": {}}]) == 0.0


def test_persistent_workflow_chaos_unsafe_execution_and_recovery_branches():
    assert chaos_check.has_unsafe_execution([{"unsafe_execution": True}]) is True
    assert chaos_check.has_unsafe_execution([
        {"kind": "dangerous_action", "approved": True, "status": "executed"}
    ]) is False
    assert chaos_check.has_unsafe_execution([
        {"kind": "dangerous_action", "approved": False, "status": "executed"}
    ]) is True

    assert chaos_check.observed_recovery_accuracy(
        {"memory corruption"},
        ["PLANNING", "BLOCKED_SAFELY"],
        {"memory_quarantine"},
    ) == "safe_block"
    assert chaos_check.observed_recovery_accuracy(
        {"runtime restart"},
        ["PLANNING", "WAITING_APPROVAL", "COMPLETED"],
        {"approval_rehydrated"},
    ) == "approval_preserved"
    assert chaos_check.observed_recovery_accuracy({"process crash"}, ["COMPLETED"], set()) == "missing"


def test_persistent_workflow_chaos_simulates_missing_data_and_score_thresholds():
    missing = chaos_check.simulate_case({"id": "missing"})

    assert "missing_state_sequence" in missing["failures"]
    assert "missing_chaos" in missing["failures"]
    assert "missing_events" in missing["failures"]
    assert "workflow_continuity_score_min_missing" in missing["failures"]

    low_score = chaos_check.simulate_case({
        "id": "low-score",
        "chaos": ["process crash"],
        "state_sequence": ["PLANNING", "INTERRUPTED", "RECOVERING", "COMPLETED"],
        "events": [
            {"trace_id": "t1", "state": "PLANNING", "kind": "started"},
        ],
        "expected": {
            "terminal_status": "completed",
            "workflow_survived": True,
            "resume_success": False,
            "recovery_accuracy": "missing",
            "approval_integrity": True,
            "plugin_isolated": True,
            "deterministic_stability": True,
            "observability_trace": True,
            "unsafe_execution": False,
            "workflow_continuity_score_min": 1.1,
        },
    })

    assert any(item.startswith("workflow_continuity_score:") for item in low_score["failures"])


def test_persistent_workflow_chaos_evaluate_rejects_fixture_shapes_and_thresholds(tmp_path: Path):
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"schema_version": 1, "round": 2, "cases": []}), encoding="utf-8")
    assert "schema_version=1" in chaos_check.evaluate(empty)["failures"][0]

    non_object_case = json.loads(FIXTURE.read_text(encoding="utf-8"))
    non_object_case["cases"] = ["bad-case"]
    non_object_path = tmp_path / "non-object-case.json"
    non_object_path.write_text(json.dumps(non_object_case), encoding="utf-8")
    assert chaos_check.evaluate(non_object_path)["failures"] == ["fixture cases must be objects"]

    missing_chaos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    missing_chaos["chaos_requirements"].remove("process crash")
    missing_chaos_path = tmp_path / "missing-chaos.json"
    missing_chaos_path.write_text(json.dumps(missing_chaos), encoding="utf-8")
    assert "chaos requirements" in chaos_check.evaluate(missing_chaos_path)["failures"][0]

    threshold_fail = json.loads(FIXTURE.read_text(encoding="utf-8"))
    threshold_fail["metric_thresholds"]["Workflow Continuity Score"] = 2
    threshold_path = tmp_path / "threshold-fail.json"
    threshold_path.write_text(json.dumps(threshold_fail), encoding="utf-8")
    payload = chaos_check.evaluate(threshold_path)
    assert any("Workflow Continuity Score" in str(failure) for failure in payload["failures"])


def test_persistent_workflow_chaos_text_output_lists_metrics_and_failures(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["metric_thresholds"]["Workflow Continuity Score"] = 2
    path = tmp_path / "threshold-fail.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")

    result = subprocess.run(
        ["python3", str(CHECK), "--fixture", str(path)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: persistent workflow chaos check" in result.stdout
    assert "Workflow Continuity Score:" in result.stdout
    assert "- Workflow Continuity Score:" in result.stdout
