"""Tests for deterministic readiness workload validation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "readiness-workload-validate.py"
CREW = REPO_ROOT / "core" / "bin" / "crew"


def test_readiness_workload_validate_generates_clean_workload_evidence(tmp_path: Path):
    output = tmp_path / "workload.json"

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--crew-bin",
            str(CREW),
            "--output",
            str(output),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"] == "agent-crew-readiness-validation-workload"
    assert payload["validation_mode"] == "deterministic_host_bridge_smoke"
    assert payload["tasks"] == 2
    assert payload["successes"] == 2
    assert payload["host_bridge_completed"] == 2
    assert payload["human_interventions"] == 0
    assert payload["passed"] is True


def test_readiness_workload_validate_blocks_missing_crew_bin(tmp_path: Path):
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--crew-bin",
            str(tmp_path / "missing-crew"),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "crew CLI not found" in result.stderr
