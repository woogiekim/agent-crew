"""Tests for persistent workflow test strategy coverage."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECK = REPO_ROOT / "core" / "scripts" / "persistent-workflow-test-check.py"
FIXTURE = REPO_ROOT / "core" / "evaluations" / "persistent-workflow-test-strategy.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


persistent_check = _load_module(CHECK, "persistent_workflow_test_check")


def test_persistent_workflow_test_strategy_check_passes():
    result = subprocess.run(
        ["python3", str(CHECK), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"]["failed"] == 0


def test_persistent_workflow_strategy_fixture_covers_required_categories():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert fixture["system_identity"] == "Persistent AI Workforce System"
    assert fixture["round"] == 1
    assert fixture["completed_rounds"] == [1, 2]
    assert set(fixture["test_categories"]) == {
        "workflow_durability",
        "resume_and_recovery",
        "human_approval_integrity",
        "workflow_determinism",
        "workflow_observability",
        "plugin_isolation",
        "long_running_operational",
    }


def test_persistent_workflow_strategy_fixture_covers_chaos_and_metrics():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert "token exhaustion" in fixture["chaos_requirements"]
    assert "memory corruption" in fixture["chaos_requirements"]
    assert "Workflow Continuity Score" in fixture["success_metrics"]
    assert "superficial latency metrics" in fixture["anti_goals"]
    assert "core/evaluations/persistent-workflow-chaos.json" in fixture["round_2_evidence"]
    assert any("persistent-workflow-chaos-check.py" in command for command in fixture["round_2_commands"])


def test_persistent_workflow_strategy_fails_when_evidence_is_missing(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "core" / "evaluations").mkdir(parents=True)
    (tmp_path / "docs" / "persistent-workflow-test-strategy.md").write_text(
        "Persistent AI Workforce System",
        encoding="utf-8",
    )
    (tmp_path / "core" / "evaluations" / "persistent-workflow-test-strategy.json").write_text(
        json.dumps({
            "round": 1,
            "system_identity": "Persistent AI Workforce System",
            "objective": ["workflow durability"],
            "critical_questions": ["Can this AI continue working tomorrow?"],
            "test_categories": {
                "workflow_durability": {
                    "round_1_evidence": ["missing/check.py"],
                },
            },
        }),
        encoding="utf-8",
    )

    payload = persistent_check.evaluate(tmp_path)
    failed = {failure["name"] for failure in payload["failures"]}

    assert payload["passed"] is False
    assert "evidence_paths" in failed


def test_persistent_workflow_strategy_helpers_handle_invalid_shapes(tmp_path: Path):
    assert persistent_check.read_text(tmp_path) == ""
    assert persistent_check.read_json(tmp_path) == {}

    assert persistent_check.all_evidence_paths_exist(
        tmp_path,
        {"test_categories": []},
    ) is False
    assert persistent_check.all_evidence_paths_exist(
        tmp_path,
        {"test_categories": {"workflow_durability": []}},
    ) is False
    assert persistent_check.all_evidence_paths_exist(
        tmp_path,
        {"test_categories": {"workflow_durability": {}}},
    ) is False


def test_persistent_workflow_strategy_text_reports_failures(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "core" / "evaluations").mkdir(parents=True)
    (tmp_path / "docs" / "persistent-workflow-test-strategy.md").write_text(
        "incomplete strategy",
        encoding="utf-8",
    )
    (tmp_path / "core" / "evaluations" / "persistent-workflow-test-strategy.json").write_text(
        json.dumps({}),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["python3", str(CHECK), "--root", str(tmp_path)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: persistent workflow test strategy check" in result.stdout
    assert "FAIL: doc_core_terms" in result.stdout
