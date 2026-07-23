"""Tests for the phase-two validation runner."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "phase-2-validation.py"
DEFAULT_FRAMEWORK = REPO_ROOT / "core" / "evaluations" / "phase-2-validation.json"
WORKFLOW_REPLAY = REPO_ROOT / "core" / "evaluations" / "workflow-replay.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


phase_two = _load_module(SCRIPT, "phase_2_validation")


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


def test_phase_2_validation_timeout_records_failure_without_hanging(tmp_path: Path):
    framework = tmp_path / "framework.json"
    write_framework(framework)
    data = json.loads(framework.read_text(encoding="utf-8"))
    data["levels"][0]["commands"][0]["command"] = [
        "{python}",
        "-c",
        "import time; print('before sleep'); time.sleep(5)",
    ]
    data["levels"][0]["commands"][0]["timeout_seconds"] = 0.1
    framework.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    result = run_runner("--framework", str(framework))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    command = next(item for item in payload["commands"] if item["id"] == "pass_cmd")
    assert command["timed_out"] is True
    assert command["timeout_seconds"] == 0.1
    assert command["returncode"] == 124
    assert command["passed"] is False
    assert "timed out after 0.1s" in command["stderr_tail"]


def test_phase_2_validation_failure_artifacts_preserve_markers_before_tail(tmp_path: Path):
    framework = tmp_path / "framework.json"
    output = tmp_path / "report.json"
    write_framework(framework)
    data = json.loads(framework.read_text(encoding="utf-8"))
    data["levels"][0]["commands"][0]["command"] = [
        "{python}",
        "-c",
        (
            "import sys; "
            "print('--- test_flaky_shell.bash ---'); "
            "print('NOT ok exact failure marker'); "
            "print('x' * 5000); "
            "print('failed:'); "
            "print('  - exact failed-list entry: expected exit=7 actual=0'); "
            "raise SystemExit(3)"
        ),
    ]
    framework.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    result = run_runner("--framework", str(framework), "--output", str(output))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    command = next(item for item in payload["commands"] if item["id"] == "pass_cmd")
    assert Path(command["stdout_path"]).is_file()
    assert Path(command["stderr_path"]).is_file()
    assert command["stdout_sha256"]
    assert any("NOT ok exact failure marker" in marker["text"] for marker in command["failure_markers"])
    assert any("exact failed-list entry" in marker["text"] for marker in command["failure_markers"])
    assert any(marker.get("section") == "test_flaky_shell.bash" for marker in command["failure_markers"])


def test_phase_2_validation_rerun_failed_once_marks_flake_and_passes_gate(tmp_path: Path):
    framework = tmp_path / "framework.json"
    output = tmp_path / "report.json"
    marker = tmp_path / "already_failed"
    flaky = tmp_path / "flaky.py"
    flaky.write_text(
        (
            "from pathlib import Path\n"
            "import sys\n"
            f"marker = Path({str(marker)!r})\n"
            "if not marker.exists():\n"
            "    marker.write_text('failed once', encoding='utf-8')\n"
            "    print('FAIL first attempt')\n"
            "    raise SystemExit(7)\n"
            "print('PASS rerun')\n"
        ),
        encoding="utf-8",
    )
    write_framework(framework)
    data = json.loads(framework.read_text(encoding="utf-8"))
    data["levels"][0]["commands"][0]["command"] = ["{python}", str(flaky)]
    framework.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    result = run_runner(
        "--framework",
        str(framework),
        "--output",
        str(output),
        "--rerun-failed-once",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    command = next(item for item in payload["commands"] if item["id"] == "pass_cmd")
    assert command["passed"] is True
    assert command["flaky"] is True
    assert command["initial_returncode"] == 7
    assert command["rerun_returncode"] == 0
    assert command["initial_failure_markers"]
    assert Path(command["rerun_stdout_path"]).is_file()


def test_phase_2_validation_unmeasured_required_dimension_is_reported(tmp_path: Path):
    framework = tmp_path / "framework.json"
    write_framework(framework)

    result = run_runner("--framework", str(framework))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    maintainability = next(item for item in payload["criteria"] if item["id"] == "maintainability")
    assert maintainability["status"] == "unmeasured"
    assert any(gap["criterion_id"] == "maintainability" for gap in payload["gaps"])


def test_phase_2_validation_helpers_cover_selection_and_status_branches(tmp_path: Path):
    assert phase_two.tail("abcdef", 3) == "def"
    assert phase_two.selected("unit", "cmd", {"integration"}, set()) is False
    assert phase_two.gap_summary("compatibility", "custom") == "compatibility status is custom."
    assert phase_two.action_for({}, "passed") is None
    assert phase_two.criterion_summary(
        {"criteria": [{"id": "optional"}]},
        [{"id": "optional_cmd", "criteria": ["optional"], "optional": True, "passed": True}],
        plan_only=False,
    )[0]["status"] == "passed"

    framework = {
        "levels": [
            {
                "id": "unit",
                "commands": [
                    {
                        "id": "pass_cmd",
                        "label": "Passing command",
                        "command": ["{python}", "-c", "print('ok')"],
                        "criteria": ["quality"],
                    }
                ],
            },
            {"id": "unselected", "commands": []},
        ],
        "criteria": [
            {"id": "quality"},
        ],
    }
    report = phase_two.build_report(
        framework,
        root=tmp_path,
        plan_only=False,
        levels=set(),
        commands=set(),
    )

    assert {item["id"]: item["status"] for item in report["criteria"]}["quality"] == "passed"
    assert {item["id"]: item["status"] for item in report["levels"]}["unselected"] == "unselected"


def test_phase_2_framework_bounds_shell_smoke_command_runtime():
    framework = json.loads(DEFAULT_FRAMEWORK.read_text(encoding="utf-8"))
    smoke_commands = {
        command["id"]: command
        for level in framework["levels"]
        if level["id"] == "smoke"
        for command in level["commands"]
    }

    assert smoke_commands["shell_suite"]["timeout_seconds"] <= 180


def test_phase_2_validation_command_filter_can_skip_unselected_commands(tmp_path: Path):
    framework = tmp_path / "framework.json"
    write_framework(framework)

    result = run_runner("--framework", str(framework), "--command", "missing")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["commands"] == []
    assert any(level["status"] == "unselected" for level in payload["levels"])


def test_phase_2_validation_text_output_lists_gaps_and_actions(tmp_path: Path):
    framework = tmp_path / "framework.json"
    write_framework(framework)
    data = json.loads(framework.read_text(encoding="utf-8"))
    data["levels"][0]["commands"][0]["command"] = ["{python}", "-c", "raise SystemExit(3)"]
    framework.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--framework", str(framework)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: phase-two validation" in result.stdout
    assert "criteria:" in result.stdout
    assert "gaps:" in result.stdout
    assert "follow-up actions:" in result.stdout


def test_phase_2_validation_text_output_skips_unselected_levels(capsys):
    phase_two.emit_text({
        "plan_only": False,
        "passed": True,
        "levels": [
            {"id": "unit", "status": "unselected", "commands": []},
        ],
        "criteria": [],
        "gaps": [],
        "recommended_follow_up_actions": [],
    })

    assert "level/unit" not in capsys.readouterr().out


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
