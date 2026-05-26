"""Tests for Codex workflow-state enforcement guard."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "codex-workflow-guard.py"


def _run(task_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--task-dir", str(task_dir), "--format", "json"],
        text=True,
        capture_output=True,
    )


def _run_text(task_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--task-dir", str(task_dir), *extra],
        text=True,
        capture_output=True,
    )


def test_codex_workflow_guard_accepts_complete_state(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    for name in ("handoff.md", "pipeline.json", "register.json"):
        (task_dir / name).write_text("{}\n", encoding="utf-8")

    result = _run(task_dir)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["missing"] == []


def test_codex_workflow_guard_blocks_missing_markers(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "handoff.md").write_text("handoff\n", encoding="utf-8")

    result = _run(task_dir)

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["blocker"] == "missing_required_state_markers"
    assert set(payload["missing"]) == {"pipeline", "register"}


def test_codex_workflow_guard_text_reports_ok(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()

    result = _run_text(task_dir, "--require", "task-dir")

    assert result.returncode == 0
    assert result.stdout == "STATUS: ok\n"


def test_codex_workflow_guard_text_reports_blocker(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()

    result = _run_text(task_dir, "--require", "pipeline")

    assert result.returncode == 2
    assert "STATUS: blocked" in result.stdout
    assert "BLOCKER: missing_required_state_markers" in result.stdout
    assert "MISSING: pipeline" in result.stdout
    assert "NEXT: Run crew:run/crew run" in result.stdout
