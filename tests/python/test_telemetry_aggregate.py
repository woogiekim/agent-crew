"""Tests for core/scripts/telemetry-aggregate.py.

Exit code contract:
  0 — success
  3 — invalid args / unreadable state dir
"""
from __future__ import annotations

import json
import os
from pathlib import Path


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
        assert payload["summary"]["tasks_completed"] == 1
        assert payload["summary"]["tasks_running"] == 0

    def test_cancelled_result_md_counts_as_blocked(
        self, script_runner, env_with_home, state_dir
    ):
        """Plan-cancelled tasks are terminal, not long-running."""
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
        assert task["status"] == "blocked"
        assert task["current_phase"] == "blocked"
        assert task["blockers"] == ["cancelled"]
        assert payload["summary"]["tasks_blocked"] == 1

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
