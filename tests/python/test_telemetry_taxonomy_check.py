"""Tests for live telemetry correlation against retry-chaos taxonomy."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "telemetry-taxonomy-check.py"


def _write_progress(task_dir: Path, events: list[dict]) -> None:
    task_dir.mkdir(parents=True)
    payload = "\n".join(json.dumps(event) for event in events) + "\n"
    (task_dir / "progress.buffer.jsonl").write_text(payload, encoding="utf-8")


def _run(state_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--format",
            "json",
            *args,
        ],
        text=True,
        capture_output=True,
    )


def test_telemetry_taxonomy_check_accepts_known_retry_labels(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(
        task_dir,
        [
            {"event": "RETRY", "detail": "attempt 2 token_truncation resume"},
            {"event": "RETRY", "detail": "reviewer rejected reason=tests_failed"},
            {"event": "BLOCKED", "detail": "quality_loop_exhausted"},
        ],
    )

    result = _run(state_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    labels = set(payload["tasks"][0]["labels"])
    assert {"token_truncation", "tests_failed", "quality_loop_exhausted"}.issubset(labels)
    assert payload["summary"]["classified_events"] == 3


def test_telemetry_taxonomy_check_rejects_unknown_explicit_label(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(task_dir, [{"event": "RETRY", "retry_reason": "mystery_retry"}])

    result = _run(state_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["tasks"][0]["unknown_labels"] == ["mystery_retry"]


def test_telemetry_taxonomy_check_enforces_required_label(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(task_dir, [{"event": "RETRY", "detail": "token_truncation"}])

    result = _run(state_dir, "--require-label", "host_blocked")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["failures"] == [{"missing_required_labels": ["host_blocked"]}]


def test_telemetry_taxonomy_check_rejects_invalid_fixture(tmp_path: Path):
    state_dir = tmp_path / "state"
    fixture = tmp_path / "retry-chaos.json"
    fixture.write_text('{"schema_version": 1, "cases": []}\n', encoding="utf-8")

    result = _run(state_dir, "--fixture", str(fixture))

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error_type"] == "invalid_fixture"
