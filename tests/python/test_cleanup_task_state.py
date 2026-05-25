"""Tests for dry-run task-state cleanup planning."""

from __future__ import annotations

import json
from pathlib import Path


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
