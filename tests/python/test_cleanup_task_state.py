"""Tests for dry-run task-state cleanup planning."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "cleanup-task-state.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cleanup = _load_module(SCRIPT, "cleanup_task_state")


def test_cleanup_task_state_helpers_cover_missing_paths_and_destructive_summary(tmp_path: Path):
    assert cleanup.load_json(tmp_path / "missing.json") == {}
    assert cleanup.age_seconds(tmp_path / "missing-marker") == 0
    assert cleanup.discover(tmp_path / "missing-state", 0) == []
    assert cleanup.summarize([{"kind": "unknown", "destructive": True}])["destructive_deletions"] == 1


def test_cleanup_task_state_dry_run_lists_stale_markers_without_mutation(
    script_runner, env_with_home, state_dir
):
    tasks = state_dir / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    marker = tasks / "active.20260101-120000-0"
    pending_dir = tasks / "20260101-120000-0"
    pending_dir.mkdir()
    pending = pending_dir / "supervisor-pending.txt"
    marker.write_text("active\n", encoding="utf-8")
    pending.write_text("pending\n", encoding="utf-8")

    r = script_runner(
        "cleanup-task-state.py",
        "--state-dir", str(state_dir),
        "--handoff-ready-min-age-seconds", "0",
        "--format", "json",
        env=env_with_home,
    )

    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    kinds = {item["kind"] for item in payload["planned_changes"]}
    assert {"stale_active_marker", "stale_supervisor_pending"}.issubset(kinds)
    assert payload["summary"]["stale_active_markers"] == 1
    assert payload["summary"]["stale_supervisor_pending_sentinels"] == 1
    assert payload["summary"]["planned_archival_targets"] == 2
    pending_items = [item for item in payload["planned_changes"] if item["kind"] == "stale_supervisor_pending"]
    assert "crew trace --task-id 20260101-120000-0" in pending_items[0]["commands"]
    assert "operator_hint" in pending_items[0]
    assert marker.exists()
    assert pending.exists()
    assert payload["policy"]["destructive_deletion"] == "not performed by this command"


def test_cleanup_task_state_apply_archives_markers_and_sentinels_with_collision(
    script_runner, env_with_home, state_dir
):
    tasks = state_dir / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    marker = tasks / "active.20260101-120000-0"
    pending_dir = tasks / "20260101-120000-0"
    pending = pending_dir / "supervisor-pending.txt"
    archive_root = state_dir / "archive" / "task-state-cleanup"
    pending_dir.mkdir()
    archive_root.mkdir(parents=True)
    marker.write_text("active\n", encoding="utf-8")
    pending.write_text("pending\n", encoding="utf-8")
    (archive_root / marker.name).write_text("existing\n", encoding="utf-8")

    r = script_runner(
        "cleanup-task-state.py",
        "--state-dir", str(state_dir),
        "--apply",
        "--handoff-ready-min-age-seconds", "0",
        "--format", "json",
        env=env_with_home,
    )

    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert not marker.exists()
    assert not pending.exists()
    assert str(archive_root / f"{marker.name}.1") in payload["archived"]
    assert str(archive_root / pending.name) in payload["archived"]


def test_cleanup_task_state_reports_blocked_retention_policy(
    script_runner, env_with_home, state_dir
):
    task_dir = state_dir / "tasks" / "20260101-120000-0"
    task_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({"current_phase": "blocked"}),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: blocked\n", encoding="utf-8")

    r = script_runner(
        "cleanup-task-state.py",
        "--state-dir", str(state_dir),
        "--handoff-ready-min-age-seconds", "0",
        "--format", "json",
        env=env_with_home,
    )

    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    retention = [item for item in payload["planned_changes"] if item["kind"] == "task_retention_policy"]
    assert retention
    assert retention[0]["state"] == "blocked"
    assert "result.md" in retention[0]["retained"]


def test_cleanup_task_state_reports_stale_handoff_ready_review_target(
    script_runner, env_with_home, state_dir
):
    task_dir = state_dir / "tasks" / "20260101-130000-0"
    task_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({
            "current_phase": "handoff_ready",
            "host_bridge_status": "internal_handoff_ready",
        }),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: handoff_ready\n", encoding="utf-8")

    r = script_runner(
        "cleanup-task-state.py",
        "--state-dir", str(state_dir),
        "--handoff-ready-min-age-seconds", "0",
        "--format", "json",
        env=env_with_home,
    )

    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    review = [item for item in payload["planned_changes"] if item["kind"] == "stale_handoff_ready_task"]
    assert review
    assert payload["summary"]["stale_handoff_ready_tasks"] == 1
    assert payload["summary"]["operator_review_targets"] == 1
    assert "crew resume 20260101-130000-0" in review[0]["commands"]
    assert "repair it if completed manually" in review[0]["operator_hint"]


def test_cleanup_task_state_text_output_lists_policy_hints_and_commands(
    script_runner, env_with_home, state_dir
):
    tasks = state_dir / "tasks"
    marker = tasks / "active.20260101-120000-0"
    task_dir = tasks / "20260101-120000-0"
    pending = task_dir / "supervisor-pending.txt"
    task_dir.mkdir(parents=True)
    marker.write_text("active\n", encoding="utf-8")
    pending.write_text("pending\n", encoding="utf-8")

    r = script_runner(
        "cleanup-task-state.py",
        "--state-dir", str(state_dir),
        "--handoff-ready-min-age-seconds", "0",
        env=env_with_home,
    )

    assert r.returncode == 0, r.stderr
    assert "mode: dry-run" in r.stdout
    assert "stale_counts:" in r.stdout
    assert "policy: archival moves markers" in r.stdout
    assert "- stale_supervisor_pending 20260101-120000-0:" in r.stdout
    assert "hint:" in r.stdout
    assert "command: crew trace --task-id 20260101-120000-0" in r.stdout
