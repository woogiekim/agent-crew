"""Tests for the phase-one validation runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "phase-1-validation.py"


def write_framework(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "test framework",
                "objective": "exercise runner",
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
                    {"id": "quality", "question": "quality?", "phase_1_threshold": "pass"},
                    {"id": "memory", "question": "memory?", "phase_1_threshold": "record"},
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


def test_phase_1_validation_plan_only_lists_commands(tmp_path: Path):
    framework = tmp_path / "framework.json"
    write_framework(framework)

    result = run_runner("--framework", str(framework), "--plan-only")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["plan_only"] is True
    assert payload["passed"] is None
    assert [item["id"] for item in payload["commands"]] == ["pass_cmd", "optional_fail"]
    assert all(item["skipped"] for item in payload["commands"])


def test_phase_1_validation_optional_failure_does_not_fail_run(tmp_path: Path):
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
    assert output.is_file()


def test_phase_1_validation_required_failure_fails_run(tmp_path: Path):
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
