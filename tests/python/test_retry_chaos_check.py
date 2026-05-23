"""Tests for deterministic retry chaos replay fixtures."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "retry-chaos-check.py"
FIXTURE = REPO_ROOT / "core" / "evaluations" / "retry-chaos.json"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--format", "json", *args],
        text=True,
        capture_output=True,
    )


def test_retry_chaos_check_passes_current_fixture():
    result = _run()

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"] == {"cases": 6, "passed": 6, "failed": 0}


def test_retry_chaos_check_detects_retry_budget_regression(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["cases"][1]["expected"]["final_status"] = "completed"
    path = tmp_path / "retry-chaos.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    first_failure = payload["failures"][0]
    assert first_failure["id"] == "crash_budget_exhaustion_blocks"
    assert any("final_status" in item for item in first_failure["failures"])


def test_retry_chaos_check_detects_token_resume_regression(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["budgets"]["max_token_truncation_resumes"] = 0
    path = tmp_path / "retry-chaos.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    first_failure = payload["failures"][0]
    assert first_failure["id"] == "token_truncation_resume_then_success"
    assert any("token_resumes" in item for item in first_failure["failures"])


def test_retry_chaos_check_rejects_invalid_fixture(tmp_path: Path):
    path = tmp_path / "retry-chaos.json"
    path.write_text('{"schema_version": 1, "cases": []}\n', encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error_type"] == "invalid_fixture"
