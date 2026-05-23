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


def _write_coverage_files(state_dir: Path, task_id: str) -> None:
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "tool-events.jsonl").write_text('{"tool":"bash"}\n', encoding="utf-8")
    (task_dir / "delegation.jsonl").write_text('{"agent_role":"backend"}\n', encoding="utf-8")
    cost_dir = state_dir / "cost"
    cost_dir.mkdir(parents=True, exist_ok=True)
    (cost_dir / f"{task_id}.jsonl").write_text('{"input_tokens":1,"output_tokens":1}\n', encoding="utf-8")


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
    _write_coverage_files(state_dir, "20260523-010203-0")

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
    _write_coverage_files(state_dir, "20260523-010203-0")

    result = _run(state_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["tasks"][0]["unknown_labels"] == ["mystery_retry"]


def test_telemetry_taxonomy_check_enforces_required_label(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(task_dir, [{"event": "RETRY", "detail": "token_truncation"}])
    _write_coverage_files(state_dir, "20260523-010203-0")

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


def test_telemetry_taxonomy_check_rejects_empty_event_stream(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    task_dir.mkdir(parents=True)
    (task_dir / "progress.buffer.jsonl").write_text("", encoding="utf-8")

    result = _run(state_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["failures"][0]["code"] == "insufficient_telemetry_coverage"


def test_telemetry_taxonomy_check_rejects_absent_task_streams(tmp_path: Path):
    state_dir = tmp_path / "state"

    result = _run(state_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["failures"][0]["code"] == "insufficient_telemetry_coverage"
    assert "no task telemetry streams" in payload["failures"][0]["detail"]


def test_telemetry_taxonomy_check_reports_weak_coverage_categories(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(task_dir, [{"event": "RETRY", "detail": "token_truncation"}])

    result = _run(state_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["failures"][0]["code"] == "weak_telemetry_coverage"
    assert set(payload["failures"][0]["weak_categories"]) == {"tool", "delegation", "token"}
