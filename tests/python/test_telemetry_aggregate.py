"""Tests for core/scripts/telemetry-aggregate.py.

Exit code contract:
  0 — success
  3 — invalid args / unreadable state dir
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TELEMETRY = REPO_ROOT / "core" / "scripts" / "telemetry-aggregate.py"


def _load_module(path: Path, name: str):
    script_dir = str(path.parent)
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


telemetry = _load_module(TELEMETRY, "telemetry_aggregate")


def _write_register(task_dir: Path, *, task_id: str,
                    current_phase: str = "completed",
                    project_root: str = "/tmp/proj") -> None:
    session_id = task_id.rsplit("-", 1)[0]
    reg = {
        "schema_version": 1,
        "task_id": task_id,
        "session_id": session_id,
        "task": "telemetry test task",
        "branch": "test/example",
        "project_root": project_root,
        "task_dir": str(task_dir),
        "execution_mode": "single",
        "current_phase": current_phase,
        "approval_status": "approved",
        "verification_status": "passed",
    }
    (task_dir / "register.json").write_text(json.dumps(reg))


def _write_progress_jsonl(task_dir: Path, rows: list[dict]) -> None:
    with (task_dir / "progress.buffer.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _selector_args(**overrides):
    values = {
        "project_root": None,
        "task_id": None,
        "session_id": None,
        "recent": None,
        "since": None,
        "until": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_direct_resolvers_parse_helpers_and_project_matching(monkeypatch, tmp_path: Path):
    state = tmp_path / "state"
    monkeypatch.setenv("AGENT_CREW_STATE_DIR", str(state))
    assert telemetry.resolve_state_dir(None) == state

    monkeypatch.delenv("AGENT_CREW_STATE_DIR")
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_CREW_PROJECT", "project")
    assert telemetry.resolve_state_dir(None) == tmp_path / "home" / "state" / "project"
    assert telemetry.parse_iso_ts("not-a-date") is None
    assert telemetry.parse_date_arg("2026-99-99") is None

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    assert telemetry.task_matches_project_root(task_dir, "") is True
    assert telemetry.task_matches_project_root(task_dir, str(tmp_path / "project")) is True
    (task_dir / "project-root.txt").write_text(str(tmp_path / "foreign"), encoding="utf-8")
    assert telemetry.task_matches_project_root(task_dir, str(tmp_path / "project")) is False


def test_direct_readers_skip_bad_lines_and_legacy_logs(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260101-120000-0"
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "progress.buffer.jsonl").write_text("\n{bad json\n{}\n", encoding="utf-8")
    assert telemetry.read_progress_buffer(task_dir) == [{}]

    (task_dir / "progress.log").write_text(
        "2026-01-01T12:00:00Z | LEGACY | detailed event\n"
        "raw legacy line\n",
        encoding="utf-8",
    )
    log_rows = telemetry.read_progress_log(task_dir)
    assert log_rows[0]["event"] == "LEGACY"
    assert log_rows[1]["event"] == "LOG"
    assert telemetry.latest_progress_event(task_dir, [])["detail"] == "raw legacy line"

    assert telemetry.read_cost_file(state_dir, task_id) is None
    cost_file = state_dir / "cost" / f"{task_id}.jsonl"
    cost_file.parent.mkdir(parents=True)
    cost_file.write_text(
        "\n{bad json\n"
        + json.dumps({"input_tokens": 1200, "output_tokens": 300})
        + "\n",
        encoding="utf-8",
    )
    assert telemetry.read_cost_file(state_dir, task_id)["tokens_total"] == 1500
    cost_file.write_text(
        json.dumps({"input_tokens": 0, "output_tokens": 0, "total_tokens": 28904})
        + "\n",
        encoding="utf-8",
    )
    assert telemetry.read_cost_file(state_dir, task_id) == {
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_total": 28904,
    }

    (task_dir / "tool-events.jsonl").write_text("\n{bad json\n{}\n", encoding="utf-8")
    assert telemetry.read_tool_events(task_dir) == [{}]

    (task_dir / "context").mkdir()
    (task_dir / "context" / "quality-metrics.json").write_text("{bad json", encoding="utf-8")
    assert telemetry.read_quality_metrics(task_dir) == {}

    (state_dir / "capabilities.json").write_text("{bad json", encoding="utf-8")
    assert telemetry.read_capabilities(state_dir) is None
    (state_dir / "capabilities.json").unlink()
    assert telemetry.read_capabilities(state_dir) is None


def test_direct_runtime_thresholds_health_and_guidance(monkeypatch, tmp_path: Path):
    assert telemetry.phase_runtime_metrics([{"event": "STAGE", "ts": "bad"}]) == []

    monkeypatch.setenv("AGENT_CREW_SUPERVISOR_BOOT_TIMEOUT_SECONDS", "bad")
    monkeypatch.setenv("AGENT_CREW_STALE_HOST_BRIDGE_SECONDS", "bad")
    monkeypatch.setenv("AGENT_CREW_STALLED_PROGRESS_SECONDS", "bad")
    assert telemetry.supervisor_boot_timeout_seconds() == 30
    assert telemetry.stale_host_bridge_seconds() == 600
    assert telemetry.stalled_progress_seconds() == 300

    class BadStat:
        def stat(self):
            raise OSError("no stat")

    assert telemetry.task_age_seconds(BadStat(), None) == 0
    assert telemetry.event_age_seconds({}, BadStat()) == 0
    assert telemetry.health_classification("running", "supervisor_handoff_pending", [], {}, tmp_path) == "booting"

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "task.txt").write_text("pending task", encoding="utf-8")
    monkeypatch.setenv("AGENT_CREW_SUPERVISOR_BOOT_TIMEOUT_SECONDS", "999999")
    pending = telemetry.missing_supervisor_boot_state(
        task_dir,
        has_register=False,
        has_events=False,
        has_result=False,
    )
    assert pending["status"] == "running"
    assert pending["current_phase"] == "supervisor_handoff_pending"

    assert "Supervisor boot is pending" in telemetry.guidance_for([], "running", "supervisor_handoff_pending")[0]
    assert "Inspect result.md" in telemetry.guidance_for([], "blocked", "")[0]
    assert telemetry.host_bridge_status({"manual_fallback_repair_path": "context/repair.json"}) == "manual_fallback_completed"

    empty_dir = tmp_path / "empty-task"
    empty_dir.mkdir()
    assert telemetry.missing_supervisor_boot_state(
        empty_dir,
        has_register=False,
        has_events=False,
        has_result=False,
    ) is None


def test_direct_aggregate_task_terminal_event_and_register_edges(tmp_path: Path):
    state_dir = tmp_path / "state"
    tasks = state_dir / "tasks"
    tasks.mkdir(parents=True)

    cancelled_reg = tasks / "20260101-120000-0"
    cancelled_reg.mkdir()
    _write_register(cancelled_reg, task_id=cancelled_reg.name, current_phase="cancelled")
    assert telemetry.aggregate_task(state_dir, cancelled_reg)["status"] == "cancelled"

    unknown_reg = tasks / "20260101-120001-0"
    unknown_reg.mkdir()
    _write_register(unknown_reg, task_id=unknown_reg.name, current_phase="")
    assert telemetry.aggregate_task(state_dir, unknown_reg)["status"] == "unknown"

    completed = tasks / "20260101-120002-0"
    completed.mkdir()
    _write_progress_jsonl(completed, [
        {"ts": "2026-01-01T12:00:00Z", "event": "STARTED", "detail": "started detail"},
        {"ts": "2026-01-01T12:00:10Z", "event": "COMPLETED"},
    ])
    (completed / "pipeline.json").write_text("{bad json", encoding="utf-8")
    completed_row = telemetry.aggregate_task(state_dir, completed)
    assert completed_row["status"] == "completed"
    assert completed_row["task"] == "started detail"

    cancelled = tasks / "20260101-120003-0"
    cancelled.mkdir()
    _write_progress_jsonl(cancelled, [
        {"ts": "2026-01-01T12:00:00Z", "event": "STARTED"},
        {"ts": "2026-01-01T12:00:10Z", "event": "CANCELLED"},
    ])
    assert telemetry.aggregate_task(state_dir, cancelled)["status"] == "cancelled"

    blocked = tasks / "20260101-120004-0"
    blocked.mkdir()
    _write_progress_jsonl(blocked, [
        {"ts": "2026-01-01T12:00:00Z", "event": "STARTED"},
        {"ts": "2026-01-01T12:00:10Z", "event": "COST_BLOCKED", "detail": "budget exhausted"},
    ])
    blocked_row = telemetry.aggregate_task(state_dir, blocked)
    assert blocked_row["status"] == "blocked"
    assert blocked_row["blockers"] == ["budget exhausted"]

    unusual_result = tasks / "20260101-120005-0"
    unusual_result.mkdir()
    (unusual_result / "result.md").write_text("STATUS: paused\n", encoding="utf-8")
    assert telemetry.read_result_md(unusual_result)["status"] == "paused"


def test_direct_selection_quality_and_stale_marker_edges(tmp_path: Path):
    state_dir = tmp_path / "state"
    assert telemetry.list_task_dirs(state_dir, _selector_args()) == []

    tasks = state_dir / "tasks"
    tasks.mkdir(parents=True)
    first = tasks / "20260101-120000-0"
    second = tasks / "20260101-120001-0"
    custom = tasks / "custom-task"
    for task_dir in (first, second, custom):
        task_dir.mkdir()
        _write_register(task_dir, task_id=task_dir.name)

    assert [p.name for p in telemetry.list_task_dirs(
        state_dir,
        _selector_args(session_id="20260101-120000"),
    )] == [first.name]
    assert [p.name for p in telemetry.list_task_dirs(
        state_dir,
        _selector_args(task_id=second.name),
    )] == [second.name]

    os.utime(custom, (1893456000, 1893456000))
    assert [p.name for p in telemetry.list_task_dirs(
        state_dir,
        _selector_args(task_id=None, since="2030-01-01"),
    )] == ["custom-task"]
    assert telemetry.list_task_dirs(
        state_dir,
        _selector_args(until="2025-01-01"),
    ) == []

    assert telemetry.explicit_quality_bool({"quality_metrics": "bad"}, "hallucination_detected") is None

    terminal = tasks / "20260101-120002-0"
    terminal.mkdir()
    _write_register(terminal, task_id=terminal.name, current_phase="blocked")
    assert telemetry.terminal_task_state(terminal) == "blocked"
    assert telemetry.active_marker_task_dir(tasks, tasks / "active") is None
    assert telemetry.active_marker_task_dir(tasks, tasks / "active.") is None

    no_tasks_state = tmp_path / "no-tasks"
    assert telemetry.stale_state_counts(no_tasks_state)["stale_active_markers"] == 0
    (tasks / f"active.{terminal.name}").write_text("active\n", encoding="utf-8")
    (tasks / "active.directory").mkdir()
    (terminal / "supervisor-pending.txt").mkdir()
    counts = telemetry.stale_state_counts(state_dir)
    assert counts["terminal_active_markers"] == 1


def test_direct_formatters_and_rich_text_render(capsys):
    assert telemetry.format_duration(3661) == "1h01m"
    assert telemetry.format_tokens(1_500_000) == "1.5M"
    assert telemetry.format_tokens(1500) == "1.5k"
    assert telemetry.format_rate(None) == "—"
    assert telemetry.format_progress_event({
        "latest_progress": {"event": "STAGE", "agent": "backend", "detail": "x" * 100},
        "last_update_age_seconds": 65,
    }).endswith("...")

    row = {
        "task_id": "20260101-120000-0",
        "task": "render task",
        "status": "blocked",
        "health": "blocked",
        "current_phase": "blocked",
        "duration_seconds": 65,
        "stages_completed": None,
        "stages_total": 0,
        "retries": 1,
        "tokens_total": 1500,
        "latest_progress": {"event": "BLOCKED", "stage": 1, "detail": "blocked"},
        "last_update_age_seconds": 65,
        "guidance": ["Inspect result.md"],
    }
    summary = {
        "tasks_total": 1,
        "tasks_completed": 0,
        "tasks_cancelled": 0,
        "tasks_blocked": 1,
        "tasks_stale_blocked": 0,
        "tasks_running": 0,
        "mean_duration_seconds": 65,
        "median_duration_seconds": 65,
        "total_retries": 1,
        "total_tokens": 1500,
        "total_tool_events": 2,
        "total_tool_failures": 1,
        "total_tool_unrecovered_failures": 1,
        "operational_quality": {
            "success_rate": 0.0,
            "retry_rate": 1.0,
            "human_intervention_rate": 1.0,
            "rollback_frequency": 1,
            "hallucination_signal_rate": 1.0,
        },
        "stale_state_counts": {
            "stale_active_markers": 1,
            "stale_supervisor_pending_sentinels": 1,
            "terminal_active_markers": 1,
            "terminal_supervisor_pending_sentinels": 1,
        },
        "by_blocker": {"host_bridge_not_invoked": 1},
        "by_host_bridge_status": {"manual_fallback_completed": 1},
        "core_objective": telemetry.capability_ceiling({"adapter": "codex"}),
        "by_stale_blocker": {"host_bridge_not_invoked": 1},
    }

    telemetry.render_text([row], summary)
    out = capsys.readouterr().out
    assert "Historical cleanup markers" in out
    assert "Blockers: host_bridge_not_invoked=1" in out
    assert "Stale blockers: host_bridge_not_invoked=1" in out
    assert "Guidance:" in out


def test_review_fix_loop_summary_reports_no_loop_without_invention(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260101-120600-0"
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)

    _write_register(task_dir, task_id=task_id, current_phase="completed")
    _write_progress_jsonl(task_dir, [
        {"ts": "2026-01-01T12:06:00Z", "event": "STARTED", "detail": "clean run"},
        {"ts": "2026-01-01T12:06:10Z", "event": "COMPLETED"},
    ])
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    row = telemetry.aggregate_task(state_dir, task_dir)

    assert row["review_fix_loop_summary"]["total_cycles"] == 0
    assert row["review_fix_loop_summary"]["cycles"] == []
    assert row["review_fix_loop_summary"]["sources"] == ["progress.buffer.jsonl"]


def test_review_fix_loop_summary_uses_review_ledger_json_and_retry_events(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260101-120601-0"
    task_dir = state_dir / "tasks" / task_id
    context = task_dir / "context"
    context.mkdir(parents=True)

    _write_register(task_dir, task_id=task_id, current_phase="completed")
    _write_progress_jsonl(task_dir, [
        {"ts": "2026-01-01T12:06:00Z", "event": "STARTED", "detail": "loop run"},
        {
            "ts": "2026-01-01T12:06:20Z",
            "event": "RETRY",
            "stage": 2,
            "agent": "reviewer",
            "detail": "attempt 2 — reviewer_rejected reason=review_needs_changes",
        },
        {
            "ts": "2026-01-01T12:06:40Z",
            "event": "STAGE_DONE",
            "stage": 2,
            "agent": "backend",
            "detail": "backend — APPROVED",
        },
        {
            "ts": "2026-01-01T12:06:50Z",
            "event": "STAGE_DONE",
            "stage": 3,
            "agent": "reviewer",
            "detail": "reviewer — REVIEW: APPROVED",
        },
        {"ts": "2026-01-01T12:07:00Z", "event": "COMPLETED"},
    ])
    (context / "review-ledger.json").write_text(
        json.dumps({
            "items": [
                {
                    "source": "reviewer",
                    "finding": "status output does not explain retry loop",
                    "disposition": "implemented",
                    "evidence": "core/scripts/telemetry-aggregate.py",
                    "verification": "tests/python/test_telemetry_aggregate.py",
                }
            ]
        }),
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    row = telemetry.aggregate_task(state_dir, task_dir)
    summary = row["review_fix_loop_summary"]

    assert summary["total_cycles"] == 1
    assert summary["cycles"][0]["review"] == "reviewer, REVIEW: NEEDS_CHANGES"
    assert summary["cycles"][0]["finding"] == "status output does not explain retry loop"
    assert summary["cycles"][0]["fix"] == "implemented: core/scripts/telemetry-aggregate.py"
    assert summary["cycles"][0]["verification"] == "tests/python/test_telemetry_aggregate.py"
    assert "context/review-ledger.json" in summary["sources"]


def test_review_fix_loop_summary_marks_missing_artifacts_unknown(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260101-120602-0"
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)

    _write_register(task_dir, task_id=task_id, current_phase="completed")
    (task_dir / "progress.log").write_text(
        "2026-01-01T12:06:20Z | RETRY | attempt 2 — reviewer_rejected reason=review_needs_changes\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

    row = telemetry.aggregate_task(state_dir, task_dir)
    cycle = row["review_fix_loop_summary"]["cycles"][0]

    assert cycle["finding"] == "Unknown"
    assert cycle["fix"] == "Unknown"
    assert cycle["verification"] == "Unknown"
    assert "review ledger: not found" in row["review_fix_loop_summary"]["notes"]


def test_render_text_includes_compact_review_fix_loop_summary(capsys):
    row = {
        "task_id": "20260101-120603-0",
        "task": "render loop task",
        "status": "completed",
        "health": "completed",
        "current_phase": "completed",
        "duration_seconds": 10,
        "stages_completed": None,
        "stages_total": 0,
        "retries": 1,
        "tokens_total": None,
        "latest_progress": {"event": "COMPLETED", "stage": 0, "detail": ""},
        "last_update_age_seconds": 0,
        "guidance": [],
        "review_fix_loop_summary": {
            "total_cycles": 1,
            "cycles": [
                {
                    "cycle": 1,
                    "review": "reviewer, REVIEW: NEEDS_CHANGES",
                    "finding": "missing loop summary",
                    "fix": "implemented: telemetry summary",
                    "verification": "focused pytest",
                }
            ],
            "sources": ["progress.buffer.jsonl", "context/review-ledger.json"],
            "notes": [],
        },
    }
    summary = {
        "tasks_total": 1,
        "tasks_completed": 1,
        "tasks_cancelled": 0,
        "tasks_blocked": 0,
        "tasks_stale_blocked": 0,
        "tasks_running": 0,
        "mean_duration_seconds": 10,
        "median_duration_seconds": 10,
        "total_retries": 1,
        "total_tokens": 0,
        "total_tool_events": 0,
        "total_tool_failures": 0,
        "total_tool_unrecovered_failures": 0,
        "operational_quality": {},
        "stale_state_counts": {},
        "by_blocker": {},
        "by_host_bridge_status": {},
    }

    telemetry.render_text([row], summary)
    out = capsys.readouterr().out

    assert "Review / Fix Loop Summary:" in out
    assert "총 loop: 1 cycles" in out
    assert "Cycle 1" in out
    assert "missing loop summary" in out


class TestTelemetryAggregate:
    def test_empty_state_dir_emits_no_tasks(
        self, script_runner, env_with_home, state_dir
    ):
        """tasks/ exists but has no entries → exit 0 with empty report."""
        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        # Text format prints "(no tasks matched)"
        assert "no tasks" in r.stdout.lower() or r.stdout.strip() == ""

    def test_single_completed_task_reports_duration_and_stages(
        self, script_runner, env_with_home, state_dir
    ):
        """A task with register + progress buffer reports duration/stages."""
        task_id = "20260101-120000-0"
        td = state_dir / "tasks" / task_id
        (td / "context").mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="completed")
        # Pipeline with 2 completed stages
        (td / "pipeline.json").write_text(json.dumps({
            "schema_version": 1,
            "task": "telemetry test",
            "stages": ["planner", "backend"],
            "completed_stages": 2,
        }))
        _write_progress_jsonl(td, [
            {"ts": "2026-01-01T12:00:00Z", "trace_id": "x",
             "task_id": task_id, "event": "STARTED"},
            {"ts": "2026-01-01T12:00:30Z", "trace_id": "x",
             "task_id": task_id, "event": "STAGE"},
            {"ts": "2026-01-01T12:05:00Z", "trace_id": "x",
             "task_id": task_id, "event": "COMPLETED"},
        ])

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["summary"]["tasks_total"] == 1
        assert payload["summary"]["tasks_completed"] == 1
        # Duration should be 300 seconds (12:00:00 -> 12:05:00)
        task_row = payload["tasks"][0]
        assert task_row["duration_seconds"] == 300.0
        assert task_row["stages_completed"] == 2

    def test_summary_reports_stale_state_marker_counts(
        self, script_runner, env_with_home, state_dir
    ):
        """Status summaries expose stale marker/sentinel counts."""
        tasks = state_dir / "tasks"
        task_id = "20260101-120001-0"
        td = tasks / task_id
        td.mkdir(parents=True)
        (tasks / f"active.{task_id}").write_text("active\n", encoding="utf-8")
        (td / "supervisor-pending.txt").write_text("pending\n", encoding="utf-8")
        _write_register(td, task_id=task_id, current_phase="phase_0")

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        counts = json.loads(r.stdout)["summary"]["stale_state_counts"]
        assert counts["stale_active_markers"] == 1
        assert counts["stale_supervisor_pending_sentinels"] == 1
        assert counts["terminal_active_markers"] == 0
        assert counts["terminal_supervisor_pending_sentinels"] == 0

    def test_completed_task_pending_sentinel_is_historical_cleanup_marker(
        self, script_runner, env_with_home, state_dir
    ):
        """Completed tasks should not inflate current stale-pending counts."""
        tasks = state_dir / "tasks"
        task_id = "20260101-120002-0"
        td = tasks / task_id
        td.mkdir(parents=True)
        (td / "supervisor-pending.txt").write_text("pending\n", encoding="utf-8")
        _write_register(td, task_id=task_id, current_phase="completed")
        (td / "result.md").write_text("STATUS: completed\n", encoding="utf-8")

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        counts = json.loads(r.stdout)["summary"]["stale_state_counts"]
        assert counts["stale_supervisor_pending_sentinels"] == 0
        assert counts["terminal_supervisor_pending_sentinels"] == 1

    def test_summary_reports_core_objective_host_ceiling(
        self, script_runner, env_with_home, state_dir
    ):
        """Status summaries expose host-native capability ceilings."""
        task_id = "20260101-120003-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="completed")
        (state_dir / "capabilities.json").write_text(
            json.dumps({
                "adapter": "codex",
                "task_tools": False,
                "agent_background": False,
                "monitor_tool": False,
                "cost_tracking": False,
                "hook_system": False,
                "interactive_question": False,
            }),
            encoding="utf-8",
        )

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        core_objective = json.loads(r.stdout)["summary"]["core_objective"]
        assert core_objective["status"] == "host_limited_policy_fallback"
        assert core_objective["native_capability_count"] == 0
        assert "interactive_question" in core_objective["policy_only_capabilities"]

    def test_phase_runtime_metrics_include_retries_blocked_handoffs_and_wait(
        self, script_runner, env_with_home, state_dir
    ):
        """Phase telemetry exposes stage duration, retries, blockers, and wait."""
        task_id = "20260101-120050-0"
        td = state_dir / "tasks" / task_id
        (td / "context").mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="blocked")
        _write_progress_jsonl(td, [
            {"ts": "2026-01-01T12:00:00Z", "trace_id": "x",
             "task_id": task_id, "event": "STARTED"},
            {"ts": "2026-01-01T12:00:10Z", "trace_id": "x",
             "task_id": task_id, "event": "STAGE", "stage": 1,
             "agent": "backend", "detail": "1/1 — backend"},
            {"ts": "2026-01-01T12:00:20Z", "trace_id": "x",
             "task_id": task_id, "event": "RETRY", "stage": 1,
             "agent": "backend"},
            {"ts": "2026-01-01T12:00:25Z", "trace_id": "x",
             "task_id": task_id, "event": "BLOCKED", "stage": 1,
             "agent": "backend", "detail": "stage_timeout"},
            {"ts": "2026-01-01T12:00:40Z", "trace_id": "x",
             "task_id": task_id, "event": "STAGE_DONE", "stage": 1,
             "agent": "backend"},
        ])

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        task = payload["tasks"][0]
        metric = task["phase_metrics"][0]
        assert metric["stage_duration_seconds"] == 30.0
        assert metric["retries"] == 1
        assert metric["blocked_handoffs"] == 1
        assert metric["user_visible_wait_seconds"] == 30.0
        assert task["blocked_handoffs"] == 1
        assert task["user_visible_wait_seconds"] == 30.0

    def test_summary_reports_operational_quality_metrics(
        self, script_runner, env_with_home, state_dir
    ):
        """Required quality metrics are surfaced as stable summary rates."""
        completed_id = "20260101-120051-0"
        completed_dir = state_dir / "tasks" / completed_id
        completed_dir.mkdir(parents=True)
        _write_register(completed_dir, task_id=completed_id, current_phase="completed")

        blocked_id = "20260101-120052-0"
        blocked_dir = state_dir / "tasks" / blocked_id
        blocked_dir.mkdir(parents=True)
        _write_register(blocked_dir, task_id=blocked_id, current_phase="blocked")
        blocked_reg = json.loads((blocked_dir / "register.json").read_text())
        blocked_reg["task"] = "rollback failed hallucination remediation"
        blocked_reg["blocked_by"] = ["hallucination suspected"]
        (blocked_dir / "register.json").write_text(json.dumps(blocked_reg))
        _write_progress_jsonl(blocked_dir, [
            {"ts": "2026-01-01T12:00:00Z", "trace_id": "x",
             "task_id": blocked_id, "event": "STARTED"},
            {"ts": "2026-01-01T12:00:10Z", "trace_id": "x",
             "task_id": blocked_id, "event": "STAGE", "stage": 1,
             "agent": "backend"},
            {"ts": "2026-01-01T12:00:20Z", "trace_id": "x",
             "task_id": blocked_id, "event": "RETRY", "stage": 1,
             "agent": "backend"},
        ])
        (blocked_dir / "tool-events.jsonl").write_text(
            json.dumps({"status": "failed"}) + "\n" +
            json.dumps({"status": "completed"}) + "\n",
            encoding="utf-8",
        )

        manual_id = "20260101-120053-0"
        manual_dir = state_dir / "tasks" / manual_id
        manual_dir.mkdir(parents=True)
        _write_register(manual_dir, task_id=manual_id, current_phase="completed")
        manual_reg = json.loads((manual_dir / "register.json").read_text())
        manual_reg["host_bridge_status"] = "manual_fallback_completed"
        (manual_dir / "register.json").write_text(json.dumps(manual_reg))

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        quality = json.loads(r.stdout)["summary"]["operational_quality"]
        assert quality["denominator_tasks"] == 3
        assert quality["success_rate"] == 0.6667
        assert quality["retry_rate"] == 0.3333
        assert quality["hallucination_signal_rate"] == 0.3333
        assert quality["rollback_frequency"] == 1
        assert quality["human_intervention_rate"] == 0.3333
        assert quality["tool_failure_rate"] == 0.5
        assert quality["unrecovered_tool_failure_rate"] == 0.5

    def test_operational_quality_prefers_evaluator_labeled_metrics(
        self, script_runner, env_with_home, state_dir
    ):
        """context/quality-metrics.json overrides weaker text-signal inference."""
        task_id = "20260101-120054-0"
        td = state_dir / "tasks" / task_id
        (td / "context").mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="blocked")
        reg = json.loads((td / "register.json").read_text())
        reg["task"] = "rollback hallucination words appear but evaluator cleared them"
        reg["blocked_by"] = ["manual review required"]
        (td / "register.json").write_text(json.dumps(reg))
        (td / "context" / "quality-metrics.json").write_text(
            json.dumps({
                "schema_version": 1,
                "hallucination_detected": False,
                "rollback_performed": False,
                "human_intervention_required": True,
                "factuality_review": "passed",
                "evidence_paths": ["context/review.md"],
            }),
            encoding="utf-8",
        )

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        task = payload["tasks"][0]
        quality = payload["summary"]["operational_quality"]
        assert task["quality_metrics"]["factuality_review"] == "passed"
        assert quality["hallucination_signal_rate"] == 0.0
        assert quality["rollback_frequency"] == 0
        assert quality["human_intervention_rate"] == 1.0

    def test_phase_events_are_closed_by_next_phase(
        self, script_runner, env_with_home, state_dir
    ):
        """Prompt-runtime phase spans are available before stage execution."""
        task_id = "20260101-120055-0"
        td = state_dir / "tasks" / task_id
        (td / "context").mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="completed")
        _write_progress_jsonl(td, [
            {"ts": "2026-01-01T12:00:00Z", "trace_id": "x",
             "task_id": task_id, "event": "STARTED"},
            {"ts": "2026-01-01T12:00:05Z", "trace_id": "x",
             "task_id": task_id, "event": "PHASE", "stage": 0,
             "agent": "", "detail": "1a — Requirement collection"},
            {"ts": "2026-01-01T12:00:35Z", "trace_id": "x",
             "task_id": task_id, "event": "PHASE", "stage": 0,
             "agent": "", "detail": "1b — Planning"},
            {"ts": "2026-01-01T12:01:00Z", "trace_id": "x",
             "task_id": task_id, "event": "COMPLETED", "stage": 0,
             "agent": ""},
        ])

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        metrics = json.loads(r.stdout)["tasks"][0]["phase_metrics"]
        assert metrics[0]["phase"] == "1a — Requirement collection"
        assert metrics[0]["stage_duration_seconds"] == 30.0
        assert metrics[1]["phase"] == "1b — Planning"
        assert metrics[1]["stage_duration_seconds"] == 25.0

    def test_missing_register_shows_dash_status(
        self, script_runner, env_with_home, state_dir
    ):
        """Task dir without register.json: status falls back from events."""
        task_id = "20260101-120100-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        # No register.json; events only
        _write_progress_jsonl(td, [
            {"ts": "2026-01-01T12:01:00Z", "trace_id": "x",
             "task_id": task_id, "event": "STARTED"},
        ])

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert payload["summary"]["tasks_total"] == 1
        # No COMPLETED/BLOCKED event → status = running
        task = payload["tasks"][0]
        assert task["status"] in ("running", "unknown")
        # current_phase empty when register missing & no terminal event
        assert task["current_phase"] in ("", None)

    def test_missing_register_uses_result_md_terminal_status(
        self, script_runner, env_with_home, state_dir
    ):
        """Legacy task dirs with only result.md are not reported as running."""
        task_id = "20260101-120200-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        (td / "result.md").write_text(
            "# Legacy task\n\n"
            "DESCRIPTION: Legacy completed task\n"
            "BRANCH: feat/legacy\n"
            "STATUS: completed\n"
        )

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        task = payload["tasks"][0]
        assert task["status"] == "completed"
        assert task["current_phase"] == "completed"
        assert task["task"] == "Legacy completed task"
        assert payload["summary"]["tasks_completed"] == 1
        assert payload["summary"]["tasks_running"] == 0

    def test_stale_register_is_overridden_by_result_md_terminal_status(
        self, script_runner, env_with_home, state_dir
    ):
        """A stale phase_0 register should not hide a completed result.md."""
        task_id = "20260101-120300-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="phase_0")
        (td / "result.md").write_text(
            "# Stale register task\n\n"
            "**Task:** Stale register completed task\n"
            "**Status:** completed\n"
        )
        _write_progress_jsonl(td, [
            {"ts": "2026-01-01T12:03:00Z", "trace_id": "x",
             "task_id": task_id, "event": "STARTED"},
            {"ts": "2026-01-01T12:04:00Z", "trace_id": "x",
             "task_id": task_id, "event": "COMPLETED"},
        ])
        (td / "tool-events.jsonl").write_text(
            json.dumps({"status": "failed"}) + "\n",
            encoding="utf-8",
        )

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        task = payload["tasks"][0]
        assert task["status"] == "completed"
        assert task["current_phase"] == "completed"
        assert task["duration_seconds"] == 60.0
        assert task["tool_failures_total"] == 1
        assert task["tool_failures_unrecovered"] == 0
        assert payload["summary"]["tasks_completed"] == 1
        assert payload["summary"]["tasks_running"] == 0
        assert payload["summary"]["total_tool_failures"] == 1
        assert payload["summary"]["total_tool_unrecovered_failures"] == 0

    def test_cancelled_result_md_counts_as_terminal_cancelled(
        self, script_runner, env_with_home, state_dir
    ):
        """Plan-cancelled tasks are terminal, not blocked/running."""
        task_id = "20260101-120400-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        (td / "result.md").write_text(
            "# Cancelled task\n\n"
            "STATUS: CANCELLED\n"
        )

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        task = payload["tasks"][0]
        assert task["status"] == "cancelled"
        assert task["current_phase"] == "cancelled"
        assert task["health"] == "cancelled"
        assert task["blockers"] == []
        assert payload["summary"]["tasks_cancelled"] == 1
        assert payload["summary"]["tasks_blocked"] == 0
        assert payload["summary"]["operational_quality"]["denominator_tasks"] == 0
        assert payload["summary"]["operational_quality"]["cancelled_tasks"] == 1
        assert payload["summary"]["operational_quality"]["success_rate"] is None

    def test_supervisor_handoff_without_progress_is_actionable(
        self, script_runner, env_with_home, state_dir
    ):
        """A task created before supervisor Phase 0 should not look healthy."""
        task_id = "20260101-120450-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        (td / "task.txt").write_text("Fix latency and quality blockers")
        (td / "branch.txt").write_text("fix/latency-quality")
        env = {
            **env_with_home,
            "AGENT_CREW_SUPERVISOR_BOOT_TIMEOUT_SECONDS": "0",
        }

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        task = payload["tasks"][0]
        assert task["status"] == "blocked"
        assert task["current_phase"] == "supervisor_handoff_stalled"
        assert task["blockers"] == ["supervisor_handoff_not_started"]
        assert "supervisor did not produce progress artifacts" in task["guidance"][0]

    def test_host_bridge_blocker_includes_guidance(
        self, script_runner, env_with_home, state_dir
    ):
        """Blocked native handoff rows include an operator next step."""
        task_id = "20260101-120451-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="blocked")
        reg = json.loads((td / "register.json").read_text())
        reg["blocked_by"] = ["host_bridge_not_invoked"]
        (td / "register.json").write_text(json.dumps(reg))

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        guidance = payload["tasks"][0]["guidance"]
        assert guidance
        assert "Continue from task_dir/handoff.md" in guidance[0]
        assert "crew repair TASK_ID --status completed" in guidance[0]
        assert "continue the supervisor task manually" not in guidance[0]

    def test_host_bridge_guidance_is_deduplicated(
        self, script_runner, env_with_home, state_dir
    ):
        """Equivalent host-bridge blockers should not repeat the same guidance."""
        task_id = "20260101-120452-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="blocked")
        reg = json.loads((td / "register.json").read_text())
        reg["blocked_by"] = [
            "host AI bridge has not completed this handoff",
            "host_bridge_not_invoked",
        ]
        (td / "register.json").write_text(json.dumps(reg))

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        guidance = payload["tasks"][0]["guidance"]
        assert len(guidance) == 1
        assert "Continue from task_dir/handoff.md" in guidance[0]
        assert "crew repair TASK_ID --status completed" in guidance[0]

    def test_host_bridge_blocker_summary_is_canonicalized(
        self, script_runner, env_with_home, state_dir
    ):
        """Equivalent host-bridge blockers should count as one blocker label."""
        task_id = "20260101-120453-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="blocked")
        reg = json.loads((td / "register.json").read_text())
        reg["blocked_by"] = ["host_bridge_not_invoked"]
        (td / "register.json").write_text(json.dumps(reg))
        (td / "result.md").write_text(
            "# Native handoff\n\n"
            "STATUS: blocked\n"
            "BLOCKER: host AI bridge has not completed this handoff\n"
        )

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["tasks"][0]["blockers"] == [
            "host AI bridge has not completed this handoff",
            "host_bridge_not_invoked",
        ]
        assert payload["summary"]["by_blocker"] == {"host_bridge_not_invoked": 1}

    def test_completed_result_md_suppresses_stale_host_bridge_register(
        self, script_runner, env_with_home, state_dir
    ):
        """Completed result.md evidence wins over stale blocked register state."""
        task_id = "20260101-120453-1"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="blocked")
        reg = json.loads((td / "register.json").read_text())
        reg["blocked_by"] = ["host_bridge_not_invoked"]
        (td / "register.json").write_text(json.dumps(reg))
        (td / "result.md").write_text(
            "# Completed native handoff\n\n"
            "STATUS: completed\n"
        )

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        task = payload["tasks"][0]
        assert task["status"] == "completed"
        assert task["current_phase"] == "completed"
        assert task["blockers"] == []
        assert task["guidance"] == []
        assert payload["summary"]["by_blocker"] == {}

    def test_recent_selection_ignores_stale_latest_task_id_file(
        self, script_runner, env_with_home, state_dir
    ):
        """--recent selection uses task mtimes, not stale latest-task-id.txt."""
        old_id = "20260101-120453-2"
        new_id = "20260101-120453-3"
        old_td = state_dir / "tasks" / old_id
        new_td = state_dir / "tasks" / new_id
        old_td.mkdir(parents=True)
        new_td.mkdir(parents=True)
        _write_register(old_td, task_id=old_id, current_phase="blocked")
        old_reg = json.loads((old_td / "register.json").read_text())
        old_reg["blocked_by"] = ["host_bridge_not_invoked"]
        (old_td / "register.json").write_text(json.dumps(old_reg))
        (old_td / "result.md").write_text("STATUS: blocked\n")
        _write_register(new_td, task_id=new_id, current_phase="completed")
        (new_td / "result.md").write_text("STATUS: completed\n")
        (state_dir / "latest-task-id.txt").write_text(old_id)
        os.utime(old_td, (1000, 1000))
        os.utime(new_td, (2000, 2000))

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--recent", "1",
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert [task["task_id"] for task in payload["tasks"]] == [new_id]
        assert payload["tasks"][0]["guidance"] == []

    def test_project_root_filter_excludes_same_basename_foreign_checkout(
        self, script_runner, env_with_home, state_dir
    ):
        """Current-project status should not inherit same-basename state noise."""
        current_id = "20260101-120453-4"
        foreign_id = "20260101-120453-5"
        current_td = state_dir / "tasks" / current_id
        foreign_td = state_dir / "tasks" / foreign_id
        current_td.mkdir(parents=True)
        foreign_td.mkdir(parents=True)
        current_root = "/tmp/danawa/shopping-frontend"
        foreign_root = "/tmp/connect-wave/shopping-frontend"
        _write_register(
            current_td,
            task_id=current_id,
            current_phase="completed",
            project_root=current_root,
        )
        _write_register(
            foreign_td,
            task_id=foreign_id,
            current_phase="blocked",
            project_root=foreign_root,
        )
        foreign_reg = json.loads((foreign_td / "register.json").read_text())
        foreign_reg["blocked_by"] = ["host_bridge_not_invoked"]
        (foreign_td / "register.json").write_text(json.dumps(foreign_reg))

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--project-root", current_root,
            "--recent", "10",
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert [task["task_id"] for task in payload["tasks"]] == [current_id]
        assert payload["summary"]["by_blocker"] == {}

    def test_project_root_filter_keeps_current_project_worktrees(
        self, script_runner, env_with_home, state_dir
    ):
        """Parallel worktree task roots still belong to the parent project."""
        task_id = "20260101-120453-6"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        current_root = "/tmp/danawa/shopping-frontend"
        worktree_root = f"{current_root}/.crew-worktrees/{task_id}"
        _write_register(
            td,
            task_id=task_id,
            current_phase="completed",
            project_root=worktree_root,
        )

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--project-root", current_root,
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert [task["task_id"] for task in payload["tasks"]] == [task_id]

    def test_stale_host_bridge_blocker_is_separated_from_current_blockers(
        self, script_runner, env_with_home, state_dir
    ):
        """Old host bridge fallback blockers should not pollute current blockers."""
        task_id = "20260101-120454-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id, current_phase="blocked")
        reg = json.loads((td / "register.json").read_text())
        reg["blocked_by"] = ["host_bridge_not_invoked"]
        (td / "register.json").write_text(json.dumps(reg))
        _write_progress_jsonl(td, [
            {"ts": "2026-01-01T12:04:54Z", "trace_id": "x",
             "task_id": task_id, "event": "STARTED"},
        ])
        env = dict(env_with_home)
        env["AGENT_CREW_STALE_HOST_BRIDGE_SECONDS"] = "600"

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        task = payload["tasks"][0]
        assert task["status"] == "stale_blocked"
        assert task["current_phase"] == "stale_host_bridge_fallback"
        assert task["stale_blocker"] is True
        assert task["blockers"] == ["stale_host_bridge_not_invoked"]
        assert payload["summary"]["tasks_blocked"] == 0
        assert payload["summary"]["tasks_stale_blocked"] == 1
        assert payload["summary"]["by_blocker"] == {}
        assert payload["summary"]["by_stale_blocker"] == {
            "host_bridge_not_invoked": 1
        }
        assert "cleanup-host-bridge --apply" in task["guidance"][0]

    def test_recent_selector_limits_count(
        self, script_runner, env_with_home, state_dir
    ):
        """--recent N limits the number of tasks reported."""
        for i in range(5):
            tid = f"20260101-12000{i}-0"
            td = state_dir / "tasks" / tid
            td.mkdir(parents=True)
            _write_register(td, task_id=tid)

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--recent", "2",
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert payload["summary"]["tasks_total"] == 2

    def test_since_filter_uses_task_id_date_without_type_error(
        self, script_runner, env_with_home, state_dir
    ):
        """Date filters should not parse filesystem mtimes as ISO strings."""
        old_id = "20250101-120000-0"
        new_id = "20260101-120000-0"
        for task_id in (old_id, new_id):
            td = state_dir / "tasks" / task_id
            td.mkdir(parents=True)
            _write_register(td, task_id=task_id)

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--since", "2026-01-01",
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert [task["task_id"] for task in payload["tasks"]] == [new_id]

    def test_stray_tasks_subdirectory_is_ignored(
        self, script_runner, env_with_home, state_dir
    ):
        """Non-task folders under tasks/ should not pollute telemetry."""
        (state_dir / "tasks" / "context").mkdir(parents=True)
        task_id = "20260101-120500-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id)

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert [t["task_id"] for t in payload["tasks"]] == [task_id]
        assert payload["summary"]["tasks_total"] == 1

    def test_format_json_is_valid_json(
        self, script_runner, env_with_home, state_dir
    ):
        """--format json output parses cleanly."""
        task_id = "20260101-120000-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id)

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0
        payload = json.loads(r.stdout)  # raises on invalid JSON
        assert "summary" in payload and "tasks" in payload
        assert "state_dir" in payload

    def test_text_format_renders_header_or_empty_message(
        self, script_runner, env_with_home, state_dir
    ):
        """--format text default — header line printed when tasks exist."""
        task_id = "20260101-120000-0"
        td = state_dir / "tasks" / task_id
        td.mkdir(parents=True)
        _write_register(td, task_id=task_id)

        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            env=env_with_home,
        )
        assert r.returncode == 0
        # Header includes TASK ID column header
        assert "TASK ID" in r.stdout or "STATUS" in r.stdout

    def test_unreadable_state_dir_exits_3(
        self, script_runner, env_with_home
    ):
        """state-dir that doesn't exist → exit 3."""
        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", "/nonexistent/path/agent-crew",
            env=env_with_home,
        )
        assert r.returncode == 3


# --------------------------------------------------------------------------- #
# AAR debrief mode (--debrief)                                                #
# --------------------------------------------------------------------------- #
#
# Contract (issue #129, Big Five Closed-Loop Communication / AAR learning loop):
#   --debrief --task-id <id> distills a single task's post-run signals into an
#   After-Action Review memo. It reuses aggregate_task() — no new schema/state
#   file. Output carries a deterministic `meaningful` flag, a `recall_hint`, and
#   the distilled signal fields, in both --format text and --format json.


def _seed_task(state_dir: Path, task_id: str, *, retry_rows: list[dict],
               blockers: list[str], stages: int = 2) -> Path:
    """Create a task dir with register + pipeline + a progress buffer whose
    STARTED/STAGE/RETRY/COMPLETED rows model the post-run signals."""
    td = state_dir / "tasks" / task_id
    (td / "context").mkdir(parents=True)
    _write_register(td, task_id=task_id, current_phase="completed")

    pipeline = {
        "schema_version": 1,
        "task": "aar debrief test",
        "stages": ["backend", "reviewer"],
        "completed_stages": stages,
    }
    if blockers:
        # A blocked register surfaces blockers in aggregate_task()'s row.
        reg = json.loads((td / "register.json").read_text())
        reg["current_phase"] = "blocked"
        reg["blocked_by"] = blockers
        (td / "register.json").write_text(json.dumps(reg))
    (td / "pipeline.json").write_text(json.dumps(pipeline))

    rows = [
        {"ts": "2026-01-01T12:00:00Z", "trace_id": "x",
         "task_id": task_id, "event": "STARTED"},
        {"ts": "2026-01-01T12:00:30Z", "trace_id": "x",
         "task_id": task_id, "event": "STAGE", "stage": 1},
    ]
    rows.extend(retry_rows)
    terminal = "BLOCKED" if blockers else "COMPLETED"
    rows.append({"ts": "2026-01-01T12:05:00Z", "trace_id": "x",
                 "task_id": task_id, "event": terminal})
    _write_progress_jsonl(td, rows)
    return td


def _retry_row(task_id: str, ts: str, detail: str) -> dict:
    return {"ts": ts, "trace_id": "x", "task_id": task_id,
            "event": "RETRY", "detail": detail}


class TestAarDebrief:
    def test_debrief_requires_task_id(
        self, script_runner, env_with_home, state_dir
    ):
        """--debrief without --task-id → exit 3 (invalid args)."""
        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--debrief",
            env=env_with_home,
        )
        assert r.returncode == 3
        assert "task-id" in r.stderr.lower()

    def test_debrief_meaningful_on_retries_text(
        self, script_runner, env_with_home, state_dir
    ):
        """A task with retries → exit 0, meaningful, recall_hint present (text)."""
        task_id = "20260101-130000-0"
        _seed_task(
            state_dir, task_id,
            retry_rows=[_retry_row(task_id, "2026-01-01T12:01:00Z",
                                   "attempt 2 — crash")],
            blockers=[],
        )
        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--debrief",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        assert "AAR Debrief" in r.stdout
        assert "meaningful  : yes" in r.stdout
        # recall_hint line is present and non-empty for a meaningful debrief.
        hint_line = next(
            (ln for ln in r.stdout.splitlines() if ln.strip().startswith("recall_hint")),
            "",
        )
        assert hint_line and "(none" not in hint_line

    def test_debrief_meaningful_json_shape(
        self, script_runner, env_with_home, state_dir
    ):
        """--format json emits a parseable object with the required fields."""
        task_id = "20260101-130001-0"
        _seed_task(
            state_dir, task_id,
            retry_rows=[
                _retry_row(task_id, "2026-01-01T12:01:00Z",
                           "attempt 2 — reviewer_rejected reason=review_needs_changes"),
            ],
            blockers=[],
        )
        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--debrief", "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        memo = json.loads(r.stdout)
        assert memo["meaningful"] is True
        assert isinstance(memo["recall_hint"], str) and memo["recall_hint"]
        # Distilled signal fields are present.
        assert memo["retries"] == 1
        assert memo["loop_backs"] == 1
        assert memo["blockers"] == []

    def test_debrief_loop_back_detected_from_needs_changes_detail(
        self, script_runner, env_with_home, state_dir
    ):
        """A RETRY whose detail mentions NEEDS_CHANGES counts as a loop-back."""
        task_id = "20260101-130002-0"
        _seed_task(
            state_dir, task_id,
            retry_rows=[
                _retry_row(task_id, "2026-01-01T12:01:00Z",
                           "attempt 2 — reviewer NEEDS_CHANGES"),
                _retry_row(task_id, "2026-01-01T12:02:00Z",
                           "attempt 3 — reviewer_rejected reason=tests_failed"),
            ],
            blockers=[],
        )
        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--debrief", "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        memo = json.loads(r.stdout)
        assert memo["loop_backs"] == 2

    def test_debrief_meaningful_on_blockers_only(
        self, script_runner, env_with_home, state_dir
    ):
        """Blockers with zero retries still makes the run meaningful."""
        task_id = "20260101-130003-0"
        _seed_task(
            state_dir, task_id,
            retry_rows=[],
            blockers=["crash_budget_exceeded"],
        )
        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--debrief", "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        memo = json.loads(r.stdout)
        assert memo["meaningful"] is True
        assert memo["retries"] == 0
        assert "crash_budget_exceeded" in memo["blockers"]

    def test_debrief_clean_run_not_meaningful(
        self, script_runner, env_with_home, state_dir
    ):
        """A clean run (no retries, no loop-backs, no blockers) → meaningful=false,
        empty recall_hint, exit 0 (Guardrail-1 polarity)."""
        task_id = "20260101-130004-0"
        _seed_task(state_dir, task_id, retry_rows=[], blockers=[])
        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--debrief", "--format", "json",
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        memo = json.loads(r.stdout)
        assert memo["meaningful"] is False
        assert memo["recall_hint"] == ""
        assert memo["retries"] == 0
        assert memo["loop_backs"] == 0
        assert memo["blockers"] == []

    def test_debrief_missing_task_exits_3(
        self, script_runner, env_with_home, state_dir
    ):
        """--debrief on a non-existent task id → exit 3 (not a crash)."""
        r = script_runner(
            "telemetry-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", "20260101-999999-0",
            "--debrief",
            env=env_with_home,
        )
        assert r.returncode == 3

    def test_debrief_is_deterministic(
        self, script_runner, env_with_home, state_dir
    ):
        """Running --debrief twice on the same task yields identical output —
        the memo body must be a pure function of task data (no now())."""
        task_id = "20260101-130005-0"
        _seed_task(
            state_dir, task_id,
            retry_rows=[_retry_row(task_id, "2026-01-01T12:01:00Z",
                                   "attempt 2 — reviewer_rejected reason=review_needs_changes")],
            blockers=[],
        )
        args = ("telemetry-aggregate.py", "--state-dir", str(state_dir),
                "--task-id", task_id, "--debrief", "--format", "json")
        r1 = script_runner(*args, env=env_with_home)
        r2 = script_runner(*args, env=env_with_home)
        assert r1.returncode == 0 and r2.returncode == 0
        assert r1.stdout == r2.stdout

    def test_debrief_direct_build_aar_memo_polarities(self):
        """Direct unit test of build_aar_memo's meaningful gate, both polarities."""
        clean_row = {"task_id": "t", "retries": 0, "blockers": [],
                     "stages_total": 2}
        memo = telemetry.build_aar_memo(clean_row, [])
        assert memo["meaningful"] is False
        assert memo["recall_hint"] == ""

        noisy_row = {"task_id": "t", "retries": 2, "blockers": [],
                     "stages_total": 2}
        events = [{"event": "RETRY", "detail": "attempt 2 — reviewer_rejected"}]
        memo2 = telemetry.build_aar_memo(noisy_row, events)
        assert memo2["meaningful"] is True
        assert memo2["loop_backs"] == 1
        assert memo2["recall_hint"]
