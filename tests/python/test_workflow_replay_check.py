"""Tests for deterministic workflow replay fixtures."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "workflow-replay-check.py"
FIXTURE = REPO_ROOT / "core" / "evaluations" / "workflow-replay.json"


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
    assert payload["summary"] == {"cases": 3, "passed": 3, "failed": 0}


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


def test_workflow_replay_check_rejects_invalid_fixture(tmp_path: Path):
    path = tmp_path / "workflow-replay.json"
    path.write_text('{"schema_version": 1, "cases": []}\n', encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error_type"] == "invalid_fixture"
