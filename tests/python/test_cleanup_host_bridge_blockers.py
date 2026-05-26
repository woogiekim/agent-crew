"""Tests for stale host bridge blocker cleanup."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "cleanup-host-bridge-blockers.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cleanup = _load_module(SCRIPT, "cleanup_host_bridge_blockers")


def _write_task(state_dir: Path, task_id: str, register: dict, result: str = "") -> Path:
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text(json.dumps(register), encoding="utf-8")
    if result:
        (task_dir / "result.md").write_text(result, encoding="utf-8")
    return task_dir


def test_cleanup_helpers_cover_invalid_dates_and_missing_roots(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert cleanup.load_json(invalid) == {}

    assert cleanup.parse_iso("") is None
    assert cleanup.parse_iso("not a date") is None
    assert cleanup.find_matches(tmp_path / "state", 0) == []

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    assert cleanup.has_host_bridge_blocker(task_dir, {"current_phase": "running"}) is False
    assert cleanup.has_host_bridge_blocker(task_dir, {"current_phase": "completed"}) is False


def test_cleanup_task_age_uses_mtime_when_progress_is_malformed(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "progress.buffer.jsonl").write_text("not json\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(task_dir, (old, old))

    assert cleanup.task_age_seconds(task_dir, {}) >= 100

    (task_dir / "progress.buffer.jsonl").write_text(
        json.dumps({"event": "STARTED", "ts": "2026-01-01T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    assert cleanup.task_age_seconds(task_dir, {}) >= 0


def test_cleanup_find_matches_respects_min_age(tmp_path: Path):
    state_dir = tmp_path / "state"
    (state_dir / "tasks" / "missing-register").mkdir(parents=True)
    _write_task(
        state_dir,
        "task-1",
        {"current_phase": "blocked", "blocked_by": ["host_bridge_not_invoked"]},
        "STATUS: blocked\nBLOCKER: host_bridge_not_invoked\n",
    )

    assert cleanup.find_matches(state_dir, 999999) == []

    task_dir = state_dir / "tasks" / "task-1"
    assert cleanup.has_host_bridge_blocker(
        task_dir,
        {"current_phase": "blocked", "blocked_by": []},
    ) is True


def test_cleanup_repair_task_supports_blocked_status(tmp_path: Path):
    helper = tmp_path / "repair.py"
    helper.write_text("import sys\nraise SystemExit(0)\n", encoding="utf-8")

    assert cleanup.repair_task(helper, tmp_path / "state", "task-1", "blocked", "note") == 0


def test_cleanup_text_output_lists_matches_and_failed_repairs(tmp_path: Path):
    state_dir = tmp_path / "state"
    _write_task(
        state_dir,
        "task-1",
        {
            "task": "Implement a mutating change",
            "current_phase": "blocked",
            "blocked_by": ["host_bridge_not_invoked"],
        },
        "STATUS: blocked\nBLOCKER: host_bridge_not_invoked\n",
    )

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--apply",
            "--status",
            "completed",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "repaired: 0 host_bridge_not_invoked task(s)" in result.stdout
    assert "- task-1 age=" in result.stdout
    assert "failed: task-1" in result.stdout


def test_cleanup_json_output_and_successful_apply(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _write_task(
        state_dir,
        "task-1",
        {
            "task": "Read current status",
            "current_phase": "blocked",
            "blocked_by": ["host_bridge_not_invoked"],
        },
        "STATUS: blocked\nBLOCKER: host_bridge_not_invoked\n",
    )
    (task_dir / "pipeline.json").write_text(json.dumps({"stages": ["supervisor"]}), encoding="utf-8")

    dry_run = subprocess.run(
        ["python3", str(SCRIPT), "--state-dir", str(state_dir), "--format", "json"],
        text=True,
        capture_output=True,
    )
    assert dry_run.returncode == 0, dry_run.stdout + dry_run.stderr
    payload = json.loads(dry_run.stdout)
    assert payload["matched"][0]["task_id"] == "task-1"

    applied = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--apply",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert applied.returncode == 0, applied.stdout + applied.stderr
    payload = json.loads(applied.stdout)
    assert payload["repaired"] == ["task-1"]
