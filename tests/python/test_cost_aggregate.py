"""Tests for core/scripts/cost-aggregate.py.

Exit code contract:
  0 — success / ok
  1 — warn (--check-breaker only)
  2 — exceeded (--check-breaker only)
  3 — invalid args
"""
from __future__ import annotations

import json
from pathlib import Path


def _write_cost_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _record(task_id: str, **kwargs) -> dict:
    base = {
        "ts": "2026-01-01T12:00:00Z",
        "task_id": task_id,
        "session_id": task_id.rsplit("-", 1)[0],
        "agent": "backend",
        "stage": 1,
        "model": "claude-sonnet-4-6",
        "tier": "balanced",
        "input_tokens": 1000,
        "output_tokens": 500,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
    }
    base.update(kwargs)
    return base


class TestCostAggregate:
    def test_empty_cost_dir_summary_mode_zero_total(
        self, script_runner, env_with_home, state_dir
    ):
        """No cost files → summary mode with task_count=0 total_tokens=0."""
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["mode"] == "summary"
        assert payload["task_count"] == 0
        assert payload["total_tokens"] == 0
        assert payload["telemetry_source"] == "unavailable"
        assert "no measured token records" in payload["unavailable_reason"]

    def test_single_task_aggregated_total_matches(
        self, script_runner, env_with_home, state_dir
    ):
        """Single cost file: total = sum of input+output tokens."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id), _record(task_id, input_tokens=2000, output_tokens=800)],
        )
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        # 1000+500 + 2000+800 = 4300
        assert payload["task"]["total_tokens"] == 4300
        assert payload["task"]["calls"] == 2
        assert payload["task"]["telemetry_source"] == "measured"
        assert payload["task"]["routing_audit"][0]["tier"] == "balanced"
        assert payload["task"]["task_complexity_estimate"]["level"] == "unavailable"

    def test_per_tier_breakdown(
        self, script_runner, env_with_home, state_dir
    ):
        """Records across multiple tiers populate by_tier correctly."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [
                _record(task_id, tier="deep",     input_tokens=100, output_tokens=50),
                _record(task_id, tier="balanced", input_tokens=200, output_tokens=100),
                _record(task_id, tier="light",    input_tokens=300, output_tokens=150),
            ],
        )
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            env=env_with_home,
        )
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        by_tier = payload["task"]["by_tier"]
        assert by_tier["deep"]["in"] == 100
        assert by_tier["deep"]["out"] == 50
        assert by_tier["balanced"]["in"] == 200
        assert by_tier["light"]["in"] == 300
        # Each tier got 1 call
        assert by_tier["deep"]["calls"] == 1
        assert by_tier["balanced"]["calls"] == 1
        assert by_tier["light"]["calls"] == 1

    def test_multiple_task_files_summary(
        self, script_runner, env_with_home, state_dir
    ):
        """Two task files → summary aggregates both."""
        _write_cost_jsonl(
            state_dir / "cost" / "20260101-120000-0.jsonl",
            [_record("20260101-120000-0", input_tokens=1000, output_tokens=500)],
        )
        _write_cost_jsonl(
            state_dir / "cost" / "20260101-130000-0.jsonl",
            [_record("20260101-130000-0", input_tokens=2000, output_tokens=1000)],
        )

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            env=env_with_home,
        )
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert payload["task_count"] == 2
        # 1500 + 3000 = 4500
        assert payload["total_tokens"] == 4500

    def test_check_breaker_ok(
        self, script_runner, env_with_home, state_dir
    ):
        """--check-breaker with usage well below budget → 'ok' + exit 0."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id, input_tokens=100, output_tokens=50)],
        )
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--budget", "100000",
            "--check-breaker",
            env=env_with_home,
        )
        assert r.returncode == 0
        assert r.stdout.strip() == "ok"

    def test_check_breaker_warn(
        self, script_runner, env_with_home, state_dir
    ):
        """--check-breaker at >= 50% → 'warn' + exit 1."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id, input_tokens=600, output_tokens=0)],
        )
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--budget", "1000",
            "--check-breaker",
            env=env_with_home,
        )
        assert r.returncode == 1
        assert r.stdout.strip() == "warn"

    def test_check_breaker_exceeded(
        self, script_runner, env_with_home, state_dir
    ):
        """--check-breaker at >= 100% → 'exceeded' + exit 2."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id, input_tokens=1500, output_tokens=0)],
        )
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--budget", "1000",
            "--check-breaker",
            env=env_with_home,
        )
        assert r.returncode == 2
        assert r.stdout.strip() == "exceeded"

    def test_check_breaker_requires_task_id(
        self, script_runner, env_with_home, state_dir
    ):
        """--check-breaker without --task-id → exit 3."""
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--budget", "1000",
            "--check-breaker",
            env=env_with_home,
        )
        assert r.returncode == 3

    def test_table_format_renders(
        self, script_runner, env_with_home, state_dir
    ):
        """--format table renders human-readable output."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id)],
        )
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--format", "table",
            env=env_with_home,
        )
        assert r.returncode == 0
        # Table for mode=task starts with "Task:"
        assert "Task:" in r.stdout
        assert "tokens=" in r.stdout

    def test_missing_task_cost_uses_proxy_metrics_when_progress_exists(
        self, script_runner, env_with_home, state_dir
    ):
        """No measured token file: task mode reports proxy telemetry explicitly."""
        task_id = "20260101-120000-0"
        task_dir = state_dir / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (task_dir / "progress.buffer.jsonl").write_text('{"event":"STARTED"}\n')
        (task_dir / "tool-events.jsonl").write_text('{"tool":"bash"}\n')

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["task"]["telemetry_source"] == "proxy"
        assert payload["task"]["proxy_metrics"]["progress_events"] == 1
        assert payload["task"]["proxy_metrics"]["tool_events"] == 1
        assert payload["task"]["task_complexity_estimate"]["level"] == "low"

    def test_missing_task_cost_without_proxy_reports_unavailable_reason(
        self, script_runner, env_with_home, state_dir
    ):
        """No measured or proxy telemetry does not imply zero measured usage."""
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", "20260101-120000-0",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["task"]["telemetry_source"] == "unavailable"
        assert "no measured token records" in payload["task"]["unavailable_reason"]

    def test_summary_mode_reports_proxy_metrics_without_expanding_all_task_dirs(
        self, script_runner, env_with_home, state_dir
    ):
        """Default summary reports proxy availability without noisy task expansion."""
        task_id = "20260101-120000-0"
        task_dir = state_dir / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (task_dir / "progress.buffer.jsonl").write_text('{"event":"STARTED"}\n')

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["task_count"] == 0
        assert payload["tasks"] == {}
        assert payload["telemetry_source"] == "proxy"
        assert payload["proxy_metrics"]["tasks_with_proxy_events"] == 1

    def test_recent_mode_uses_proxy_task_dirs_when_cost_files_are_absent(
        self, script_runner, env_with_home, state_dir
    ):
        """Recent cost output still reports proxy telemetry without token JSONL."""
        task_id = "20260101-120000-0"
        task_dir = state_dir / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (task_dir / "progress.buffer.jsonl").write_text('{"event":"STARTED"}\n')

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--recent", "3",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["tasks"][task_id]["telemetry_source"] == "proxy"
        assert payload["tasks"][task_id]["proxy_metrics"]["progress_events"] == 1

    def test_recent_mode_without_cost_or_proxy_reports_unavailable_reason(
        self, script_runner, env_with_home, state_dir
    ):
        """Recent mode with no telemetry does not silently imply zero usage."""
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--recent", "3",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["telemetry_source"] == "unavailable"
        assert "no measured token records" in payload["unavailable_reason"]

    def test_malformed_jsonl_line_skipped(
        self, script_runner, env_with_home, state_dir
    ):
        """Malformed JSONL line is skipped with stderr warning."""
        task_id = "20260101-120000-0"
        path = state_dir / "cost" / f"{task_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            f.write("{this is not json\n")
            f.write(json.dumps(_record(task_id)) + "\n")

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            env=env_with_home,
        )
        # Bad line skipped, good line counted → exit 0, calls=1
        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert payload["task"]["calls"] == 1
        # Skip warning appears on stderr
        assert "skip malformed" in r.stderr.lower() or \
               "skip" in r.stderr.lower()
