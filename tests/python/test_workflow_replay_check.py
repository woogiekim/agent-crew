"""Tests for deterministic workflow replay fixtures."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "workflow-replay-check.py"
FIXTURE = REPO_ROOT / "core" / "evaluations" / "workflow-replay.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


workflow_replay = _load_module(SCRIPT, "workflow_replay_check")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--format", "json", *args],
        text=True,
        capture_output=True,
    )


def test_workflow_replay_check_passes_current_fixture():
    result = _run()

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"] == {"cases": 11, "passed": 11, "failed": 0}


def test_workflow_replay_check_detects_tool_flow_regression(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["cases"][0]["expected"]["tool_flow"][1]["returncode"] = 1
    path = tmp_path / "workflow-replay.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    first_failure = payload["failures"][0]
    assert first_failure["id"] == "mutating_tdd_review_happy_path"
    assert any("pipeline-quality-plan-check.py:returncode" in item for item in first_failure["failures"])


def test_workflow_replay_check_detects_invalid_state_transition(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["cases"][0]["state_transitions"] = ["phase_0", "completed"]
    path = tmp_path / "workflow-replay.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    first_failure = payload["failures"][0]
    assert "invalid_transition:phase_0->completed" in first_failure["failures"]


def test_workflow_replay_check_detects_extra_failure_code(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["cases"][1]["expected"]["tool_flow"][1]["failures"] = []
    path = tmp_path / "workflow-replay.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    first_failure = payload["failures"][0]
    assert first_failure["id"] == "missing_tdd_is_rejected"
    assert any("pipeline-quality-plan-check.py:failure_codes" in item for item in first_failure["failures"])


def test_workflow_replay_check_detects_issue_reporting_regression(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    case = next(item for item in fixture["cases"] if item["id"] == "normal_use_structured_blocker_reports_issue")
    case["auto_issue_payload"]["blocker"] = "ordinary_user_cancellation"
    path = tmp_path / "workflow-replay.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    issue_failure = next(
        failure for failure in payload["failures"]
        if failure["id"] == "normal_use_structured_blocker_reports_issue"
    )
    assert any("auto-issue-reporter.py:status:ignored!=expected:recorded" in item for item in issue_failure["failures"])


def test_workflow_replay_check_rejects_invalid_fixture(tmp_path: Path):
    path = tmp_path / "workflow-replay.json"
    path.write_text('{"schema_version": 1, "cases": []}\n', encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error_type"] == "invalid_fixture"


def test_workflow_replay_helpers_cover_invalid_json_and_transition_edges(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert workflow_replay.load_json(invalid)[0] is None
    invalid_payload = workflow_replay.evaluate(REPO_ROOT, invalid)
    assert invalid_payload["error_type"] == "invalid_fixture"

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert workflow_replay.load_json(array) == (None, "fixture root must be an object")

    result = workflow_replay.run_tool(
        ["python3", "-c", "print('not json')"],
        cwd=tmp_path,
        env={},
    )
    assert result["payload"] == {}

    assert workflow_replay.transition_failures([]) == ["missing_state_transitions"]
    assert workflow_replay.transition_failures(["unknown", "blocked"]) == ["unknown_state:unknown"]
    assert workflow_replay.transition_failures(["phase_0"]) == ["non_terminal_final_state:phase_0"]


def test_workflow_replay_case_reports_unknown_tool_and_expected_mismatches():
    case = {
        "id": "unknown-tool",
        "task": "Replay unknown tool",
        "pipeline": {"stages": ["planner"]},
        "progress_events": [],
        "state_transitions": ["phase_0", "blocked"],
        "expected": {
            "tool_flow": [{"tool": "missing-tool.py", "returncode": 0}],
            "final_phase": "completed",
            "passed": True,
        },
    }

    result = workflow_replay.replay_case(case, REPO_ROOT)

    assert "unknown_expected_tool:missing-tool.py" in result["failures"]
    assert "final_phase:blocked!=expected:completed" in result["failures"]
    assert "workflow_passed:False!=expected:True" in result["failures"]


def test_workflow_replay_rejects_non_object_cases(tmp_path: Path):
    fixture = tmp_path / "workflow-replay.json"
    fixture.write_text(
        json.dumps({"schema_version": 1, "cases": ["bad-case"]}),
        encoding="utf-8",
    )

    payload = workflow_replay.evaluate(REPO_ROOT, fixture)

    assert payload["error_type"] == "invalid_fixture"
    assert payload["failures"] == ["fixture cases must be objects"]


def test_workflow_replay_text_output_lists_failures(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["cases"][0]["state_transitions"] = ["phase_0", "completed"]
    path = tmp_path / "workflow-replay.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--fixture", str(path)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: workflow replay check" in result.stdout
    assert "cases=" in result.stdout
    assert "invalid_transition:phase_0->completed" in result.stdout
