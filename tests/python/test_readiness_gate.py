"""Tests for readiness gate blocker reporting."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "readiness-gate.py"


def _load_module(path: Path, name: str):
    scripts_dir = str(path.parent)
    if scripts_dir in sys.path:
        sys.path.remove(scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


readiness_gate = _load_module(SCRIPT, "readiness_gate")


def test_readiness_gate_helpers_cover_loader_threshold_and_capability_edges(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(readiness_gate.importlib.util, "spec_from_file_location", lambda *_args, **_kwargs: None)
    try:
        readiness_gate.load_script_module("missing.py", "missing")
    except ValueError as exc:
        assert "cannot load helper script" in str(exc)
    else:
        raise AssertionError("expected load_script_module failure")

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    try:
        readiness_gate.load_json(invalid)
    except ValueError as exc:
        assert "cannot read JSON evidence" in str(exc)
    else:
        raise AssertionError("expected invalid JSON evidence to fail")

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    try:
        readiness_gate.load_json(array)
    except ValueError as exc:
        assert "must be an object" in str(exc)
    else:
        raise AssertionError("expected non-object JSON evidence to fail")

    thresholds = tmp_path / "thresholds.json"
    thresholds.write_text(json.dumps({"retry_rate": None, "task_success_rate": "0.9"}), encoding="utf-8")
    loaded = readiness_gate.load_thresholds(thresholds)
    assert loaded["retry_rate"] == readiness_gate.DEFAULT_THRESHOLDS["retry_rate"]
    assert loaded["task_success_rate"] == 0.9

    bad_thresholds = tmp_path / "bad-thresholds.json"
    bad_thresholds.write_text(json.dumps({"task_success_rate": "bad"}), encoding="utf-8")
    try:
        readiness_gate.load_thresholds(bad_thresholds)
    except ValueError as exc:
        assert "must be numeric" in str(exc)
    else:
        raise AssertionError("expected non-numeric threshold to fail")

    assert readiness_gate.generated_workload_evidence(None, recent=1, include_agent_requests=False) is None
    assert readiness_gate.load_capabilities(None) is None
    assert readiness_gate.load_capabilities(tmp_path / "missing-state") is None


def test_readiness_gate_metric_blocker_and_text_report_cover_threshold_core_objective():
    blocker = readiness_gate.metric_blocker(
        {
            "id": "retry_rate",
            "status": "failed",
            "value": 0.2,
            "threshold": 0.1,
            "direction": "at_most",
        },
        validation_reports_supplied=True,
    )

    assert blocker is not None
    assert blocker["id"] == "threshold:retry_rate"
    assert "<= 0.1" in blocker["reason"]

    text = readiness_gate.text_report({
        "passed": False,
        "evidence_mode": "unit",
        "blockers": [blocker],
        "metrics": {
            "metrics": [
                {
                    "id": "retry_rate",
                    "status": "failed",
                    "value": 0.2,
                    "threshold": 0.1,
                }
            ]
        },
        "core_objective": {
            "status": "host_limited_policy_fallback",
            "native_capability_count": 0,
            "total_capabilities": 6,
            "conditional_capabilities": [],
            "policy_only_capabilities": ["task_tools"],
            "unavailable_capabilities": ["monitor_tool"],
            "summary": "limited",
        },
    })

    assert "FAIL: readiness gate" in text
    assert "core_objective:" in text
    assert "host_runtime_ceiling=" in text


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
    assert payload["evidence_mode"] == "generated_local_state"


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
    assert payload["evidence_mode"] == "missing_workload_evidence"


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


def test_readiness_gate_prefers_explicit_workload_evidence_over_local_state(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260101-120000-0"
    task_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({"current_phase": "completed", "host_bridge_status": "manual_fallback_completed"}),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")
    (task_dir / "context").mkdir(exist_ok=True)
    (task_dir / "context" / "manual-fallback-repair.json").write_text("{}", encoding="utf-8")
    validation = tmp_path / "validation.json"
    workload = tmp_path / "workload.json"
    validation.write_text(json.dumps({"passed": True}), encoding="utf-8")
    workload.write_text(
        json.dumps({
            "source": "agent-crew-readiness-validation-workload",
            "adapter": "validation-workload",
            "tasks": 2,
            "successes": 2,
            "host_bridge_completed": 2,
            "manual_repairs": 0,
            "human_interventions": 0,
            "retries": 0,
        }),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--validation-report",
            str(validation),
            "--workload-evidence",
            str(workload),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["evidence_mode"] == "explicit_workload_evidence"
    assert payload["metrics"]["totals"]["manual_repairs"] == 0
    assert payload["evidence_sources"][0]["source"] == "agent-crew-readiness-validation-workload"


def test_readiness_gate_reports_codex_core_objective_host_ceiling(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260101-120000-0"
    task_dir.mkdir(parents=True)
    (state_dir / "capabilities.json").write_text(
        json.dumps({
            "adapter": "codex",
            "task_tools": False,
            "agent_background": False,
            "monitor_tool": False,
            "cost_tracking": False,
            "hook_system": False,
            "interactive_question": False,
        }),
        encoding="utf-8",
    )
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
    assert payload["core_objective"]["framework_gate_passed"] is True
    assert payload["core_objective"]["status"] == "host_limited_policy_fallback"
    assert payload["core_objective"]["host_native_runtime_capability_rate"] == 0.0
    assert "agent_background" in payload["core_objective"]["policy_only_capabilities"]


def test_readiness_gate_text_output_and_output_file(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260101-120000-0"
    task_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({"current_phase": "completed", "host_bridge_status": "auto_completed"}),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")
    validation = tmp_path / "validation.json"
    output = tmp_path / "reports" / "readiness.json"
    validation.write_text(json.dumps({"passed": True}), encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--validation-report",
            str(validation),
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: readiness gate" in result.stdout
    assert output.is_file()


def test_readiness_gate_cli_reports_invalid_evidence(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--validation-report", str(invalid)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "readiness-gate:" in result.stderr
