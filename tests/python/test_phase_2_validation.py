"""Tests for the phase-two validation runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "phase-2-validation.py"
DEFAULT_FRAMEWORK = REPO_ROOT / "core" / "evaluations" / "phase-2-validation.json"
WORKFLOW_REPLAY = REPO_ROOT / "core" / "evaluations" / "workflow-replay.json"


def write_framework(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "name": "test phase two framework",
                "objective": "exercise phase two runner",
                "levels": [
                    {
                        "id": "unit",
                        "commands": [
                            {
                                "id": "pass_cmd",
                                "label": "Passing command",
                                "command": ["{python}", "-c", "print('ok')"],
                                "allowed_returncodes": [0],
                                "criteria": ["quality"],
                            },
                            {
                                "id": "optional_fail",
                                "label": "Optional failure",
                                "command": ["{python}", "-c", "raise SystemExit(7)"],
                                "allowed_returncodes": [0],
                                "criteria": ["memory"],
                                "optional": True,
                            },
                        ],
                    }
                ],
                "criteria": [
                    {
                        "id": "quality",
                        "question": "quality?",
                        "phase_2_threshold": "required pass",
                        "follow_up_if_failed": "Fix required quality failures.",
                    },
                    {
                        "id": "memory",
                        "question": "memory?",
                        "phase_2_threshold": "record optional evidence",
                        "follow_up_if_failed": "Review optional memory evidence.",
                    },
                    {
                        "id": "maintainability",
                        "question": "maintainable?",
                        "phase_2_threshold": "must be measured before release",
                        "follow_up_if_unmeasured": "Add maintainability evidence.",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_runner(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--format", "json", *args],
        text=True,
        capture_output=True,
    )


def test_phase_2_validation_plan_only_preserves_levels_and_dimensions(tmp_path: Path):
    framework = tmp_path / "framework.json"
    write_framework(framework)

    result = run_runner("--framework", str(framework), "--plan-only")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 2
    assert payload["plan_only"] is True
    assert payload["passed"] is None
    assert [item["id"] for item in payload["commands"]] == ["pass_cmd", "optional_fail"]
    assert all(item["skipped"] for item in payload["commands"])
    assert {item["id"] for item in payload["criteria"]} == {
        "quality",
        "memory",
        "maintainability",
    }
    by_id = {item["id"]: item["status"] for item in payload["criteria"]}
    assert by_id["quality"] == "planned"
    assert by_id["memory"] == "planned"
    assert by_id["maintainability"] == "unmeasured"


def test_phase_2_validation_optional_failure_creates_gap_without_failing_run(tmp_path: Path):
    framework = tmp_path / "framework.json"
    output = tmp_path / "report.json"
    write_framework(framework)

    result = run_runner("--framework", str(framework), "--output", str(output))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    optional = next(item for item in payload["commands"] if item["id"] == "optional_fail")
    assert optional["passed"] is False
    memory = next(item for item in payload["criteria"] if item["id"] == "memory")
    assert memory["status"] == "provisional"
    assert any(gap["criterion_id"] == "memory" for gap in payload["gaps"])
    assert output.is_file()


def test_phase_2_validation_required_failure_fails_run_with_follow_up(tmp_path: Path):
    framework = tmp_path / "framework.json"
    write_framework(framework)
    data = json.loads(framework.read_text(encoding="utf-8"))
    data["levels"][0]["commands"][0]["command"] = ["{python}", "-c", "raise SystemExit(3)"]
    framework.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    result = run_runner("--framework", str(framework))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    quality = next(item for item in payload["criteria"] if item["id"] == "quality")
    assert quality["status"] == "needs_attention"
    assert any(action["criterion_id"] == "quality" for action in payload["recommended_follow_up_actions"])


def test_phase_2_validation_unmeasured_required_dimension_is_reported(tmp_path: Path):
    framework = tmp_path / "framework.json"
    write_framework(framework)

    result = run_runner("--framework", str(framework))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    maintainability = next(item for item in payload["criteria"] if item["id"] == "maintainability")
    assert maintainability["status"] == "unmeasured"
    assert any(gap["criterion_id"] == "maintainability" for gap in payload["gaps"])


def test_phase_2_unit_level_maps_lightweight_operational_assertions():
    framework = json.loads(DEFAULT_FRAMEWORK.read_text(encoding="utf-8"))
    unit_commands = {
        command["id"]: set(command.get("criteria", []))
        for level in framework["levels"]
        if level["id"] == "unit"
        for command in level["commands"]
    }

    runner_criteria = unit_commands["phase_2_runner_tests"]
    assert {"performance", "observability", "compatibility"}.issubset(runner_criteria)
    assert "runner command elapsed_ms" in _criterion(framework, "performance")["evidence"]
    assert "phase-two evidence JSON" in _criterion(framework, "observability")["evidence"]
    assert "Codex workflow guard tests" in _criterion(framework, "compatibility")["evidence"]


def test_phase_2_alpha_maps_progress_confidence_and_host_compatibility_scenarios():
    framework = json.loads(DEFAULT_FRAMEWORK.read_text(encoding="utf-8"))
    workflow_replay = _command(framework, "alpha", "workflow_replay")
    criteria = set(workflow_replay["criteria"])
    fixture = json.loads(WORKFLOW_REPLAY.read_text(encoding="utf-8"))
    case_ids = {case["id"] for case in fixture["cases"]}

    assert {"usability_progress_confidence", "compatibility"}.issubset(criteria)
    assert "progress_confidence_blocked_next_action" in case_ids
    assert "codex_host_capability_fallback_compatibility" in case_ids


def _command(framework: dict, level_id: str, command_id: str) -> dict:
    for level in framework["levels"]:
        if level["id"] != level_id:
            continue
        for command in level["commands"]:
            if command["id"] == command_id:
                return command
    raise AssertionError(f"missing command {level_id}/{command_id}")


def _criterion(framework: dict, criterion_id: str) -> dict:
    for criterion in framework["criteria"]:
        if criterion["id"] == criterion_id:
            return criterion
    raise AssertionError(f"missing criterion {criterion_id}")
