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
        "model": "claude-sonnet-5",
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

    def test_total_only_records_count_toward_task_total(
        self, script_runner, env_with_home, state_dir
    ):
        """Total-only bridge records count without fabricating in/out breakdown."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [
                _record(
                    task_id,
                    model="gpt-5.5",
                    tier="balanced",
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=28904,
                    usage_granularity="total_only",
                )
            ],
        )

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["task"]["input_tokens"] == 0
        assert payload["task"]["output_tokens"] == 0
        assert payload["task"]["total_tokens"] == 28904
        assert payload["task"]["by_agent"]["backend"]["total"] == 28904

    def test_per_tier_breakdown(
        self, script_runner, env_with_home, state_dir
    ):
        """Records across multiple tiers populate by_tier correctly."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [
                _record(task_id, tier="xhigh",    input_tokens=50, output_tokens=25),
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
        assert by_tier["xhigh"]["in"] == 50
        assert by_tier["xhigh"]["out"] == 25
        assert by_tier["deep"]["in"] == 100
        assert by_tier["deep"]["out"] == 50
        assert by_tier["balanced"]["in"] == 200
        assert by_tier["light"]["in"] == 300
        # Each tier got 1 call
        assert by_tier["xhigh"]["calls"] == 1
        assert by_tier["deep"]["calls"] == 1
        assert by_tier["balanced"]["calls"] == 1
        assert by_tier["light"]["calls"] == 1

    def test_unknown_tier_falls_back_to_xhigh_for_opus(
        self, script_runner, env_with_home, state_dir
    ):
        """Unknown tier with the strongest Claude model maps to xhigh."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id, tier="unknown", model="claude-fable-5")],
        )
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            env=env_with_home,
        )
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["task"]["routing_audit"][0]["tier"] == "xhigh"

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

    def test_state_dir_resolves_from_env_without_argument(
        self, script_runner, env_with_home, state_dir
    ):
        """AGENT_CREW_STATE_DIR is used when --state-dir is omitted."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id, input_tokens=20, output_tokens=5)],
        )

        r = script_runner("cost-aggregate.py", env=env_with_home)

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["task_count"] == 1
        assert payload["total_tokens"] == 25

    def test_state_dir_resolves_from_home_and_project_env(
        self, script_runner, env_with_home, agent_crew_home
    ):
        """AGENT_CREW_HOME and AGENT_CREW_PROJECT form the default state dir."""
        env = env_with_home.copy()
        env.pop("AGENT_CREW_STATE_DIR", None)
        env["AGENT_CREW_PROJECT"] = "project-from-env"
        task_id = "20260101-120000-0"
        custom_state = agent_crew_home / "state" / "project-from-env"
        _write_cost_jsonl(
            custom_state / "cost" / f"{task_id}.jsonl",
            [_record(task_id, input_tokens=30, output_tokens=7)],
        )

        r = script_runner("cost-aggregate.py", env=env)

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["task_count"] == 1
        assert payload["total_tokens"] == 37

    def test_budget_env_override_and_invalid_warning(
        self, script_runner, env_with_home, state_dir
    ):
        """Tier budgets can be overridden; invalid overrides warn and fall back."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id, tier="light", input_tokens=100, output_tokens=0)],
        )
        env = env_with_home.copy()
        env["AGENT_CREW_BUDGET_LIGHT"] = "2000"

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            env=env,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["task"]["task_budget"] == 2000

        env["AGENT_CREW_BUDGET_LIGHT"] = "not-an-int"
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            env=env,
        )

        assert r.returncode == 0
        payload = json.loads(r.stdout)
        assert payload["task"]["task_budget"] == 100000
        assert "invalid AGENT_CREW_BUDGET_LIGHT" in r.stderr

    def test_blank_and_malformed_proxy_lines_are_ignored(
        self, script_runner, env_with_home, state_dir
    ):
        """Blank JSONL lines and malformed proxy records are ignored."""
        task_id = "20260101-120000-0"
        cost_file = state_dir / "cost" / f"{task_id}.jsonl"
        cost_file.parent.mkdir(parents=True, exist_ok=True)
        cost_file.write_text("\n" + json.dumps(_record(task_id)) + "\n")
        task_dir = state_dir / "tasks" / task_id
        task_dir.mkdir(parents=True)
        (task_dir / "progress.buffer.jsonl").write_text("\n{bad json\n{}\n")

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["task"]["calls"] == 1
        assert payload["task"]["proxy_metrics"]["progress_events"] == 1

    def test_task_complexity_estimate_medium_and_high(
        self, script_runner, env_with_home, state_dir
    ):
        """Proxy event scores classify medium and high task complexity."""
        medium_id = "20260101-120000-0"
        medium_dir = state_dir / "tasks" / medium_id
        medium_dir.mkdir(parents=True)
        (medium_dir / "tool-events.jsonl").write_text("{}\n{}\n{}\n{}\n")

        high_id = "20260101-130000-0"
        high_dir = state_dir / "tasks" / high_id
        high_dir.mkdir(parents=True)
        (high_dir / "delegation.jsonl").write_text("\n".join("{}" for _ in range(9)))

        medium = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", medium_id,
            env=env_with_home,
        )
        high = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", high_id,
            env=env_with_home,
        )

        assert medium.returncode == 0, medium.stderr
        assert high.returncode == 0, high.stderr
        assert json.loads(medium.stdout)["task"]["task_complexity_estimate"]["level"] == "medium"
        assert json.loads(high.stdout)["task"]["task_complexity_estimate"]["level"] == "high"

    def test_summary_handles_missing_tasks_dir(
        self, script_runner, env_with_home, tmp_path
    ):
        """A state dir without tasks/ still reports unavailable telemetry cleanly."""
        state_dir = tmp_path / "state-without-tasks"
        state_dir.mkdir()

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["telemetry_source"] == "unavailable"
        assert payload["proxy_metrics"]["tasks_with_proxy_events"] == 0

    def test_recent_mode_includes_cost_file_candidates(
        self, script_runner, env_with_home, state_dir
    ):
        """Recent mode considers measured cost files as candidates."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id, input_tokens=40, output_tokens=2)],
        )

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--recent", "1",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["tasks"][task_id]["telemetry_source"] == "measured"
        assert payload["tasks"][task_id]["total_tokens"] == 42

    def test_session_mode_includes_measured_and_session_json_tasks(
        self, script_runner, env_with_home, state_dir
    ):
        """Session mode joins matching measured rows and session.json task ids."""
        session_id = "20260101-120000"
        measured_id = "20260101-120000-0"
        skipped_id = "20260101-130000-0"
        proxy_id = "20260101-120000-1"
        _write_cost_jsonl(
            state_dir / "cost" / f"{measured_id}.jsonl",
            [_record(measured_id, session_id=session_id, input_tokens=60, output_tokens=4)],
        )
        _write_cost_jsonl(
            state_dir / "cost" / f"{skipped_id}.jsonl",
            [_record(skipped_id, session_id="other-session")],
        )
        proxy_dir = state_dir / "tasks" / proxy_id
        proxy_dir.mkdir(parents=True)
        (proxy_dir / "progress.buffer.jsonl").write_text("{}\n")
        (state_dir / "session.json").write_text(json.dumps({
            "session_id": session_id,
            "tasks": [
                {"task_id": proxy_id},
                {"missing_task_id": "ignored"},
                "ignored",
            ],
        }))

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--session-id", session_id,
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["tasks"][measured_id]["telemetry_source"] == "measured"
        assert payload["tasks"][measured_id]["total_tokens"] == 64
        assert payload["tasks"][proxy_id]["telemetry_source"] == "proxy"
        assert skipped_id not in payload["tasks"]

    def test_session_mode_invalid_session_file_reports_unavailable(
        self, script_runner, env_with_home, state_dir
    ):
        """Bad session.json is ignored; no matching tasks reports unavailable."""
        (state_dir / "session.json").write_text("{bad json")

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--session-id", "missing-session",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["mode"] == "session"
        assert payload["tasks"] == {}
        assert payload["telemetry_source"] == "unavailable"

    def test_task_table_proxy_and_unavailable_branches(
        self, script_runner, env_with_home, state_dir
    ):
        """Task table output renders proxy metrics and unavailable reasons."""
        proxy_id = "20260101-120000-0"
        proxy_dir = state_dir / "tasks" / proxy_id
        proxy_dir.mkdir(parents=True)
        (proxy_dir / "progress.buffer.jsonl").write_text("{}\n")

        proxy = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", proxy_id,
            "--format", "table",
            env=env_with_home,
        )
        unavailable = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", "20260101-130000-0",
            "--format", "table",
            env=env_with_home,
        )

        assert proxy.returncode == 0, proxy.stderr
        assert unavailable.returncode == 0, unavailable.stderr
        assert "proxy_metrics=progress_events=1" in proxy.stdout
        assert "unavailable_reason=" in unavailable.stdout

    def test_summary_table_proxy_and_unavailable_branches(
        self, script_runner, env_with_home, state_dir, tmp_path
    ):
        """Summary table output renders proxy and unavailable metadata."""
        proxy_dir = state_dir / "tasks" / "20260101-120000-0"
        proxy_dir.mkdir(parents=True)
        (proxy_dir / "tool-events.jsonl").write_text("{}\n")

        proxy = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--format", "table",
            env=env_with_home,
        )

        empty_state = tmp_path / "empty-state"
        empty_state.mkdir()
        unavailable = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(empty_state),
            "--format", "table",
            env=env_with_home,
        )

        assert proxy.returncode == 0, proxy.stderr
        assert unavailable.returncode == 0, unavailable.stderr
        assert "telemetry_source=proxy" in proxy.stdout
        assert "proxy_metrics=tasks_with_proxy_events=1" in proxy.stdout
        assert "telemetry_source=unavailable" in unavailable.stdout
        assert "unavailable_reason=" in unavailable.stdout

    def test_session_table_renders_session_header_and_tasks(
        self, script_runner, env_with_home, state_dir
    ):
        """Session table output renders the session header and task rows."""
        session_id = "20260101-120000"
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id, session_id=session_id)],
        )

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--session-id", session_id,
            "--format", "table",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        assert f"Session: {session_id}" in r.stdout
        assert f"  {task_id}  tokens=" in r.stdout

    def test_recent_table_renders_proxy_and_unavailable_task_rows(
        self, script_runner, env_with_home, state_dir
    ):
        """Recent table output renders per-task proxy and unavailable details."""
        proxy_id = "20260101-120000-0"
        unavailable_id = "20260101-130000-0"
        proxy_dir = state_dir / "tasks" / proxy_id
        unavailable_dir = state_dir / "tasks" / unavailable_id
        proxy_dir.mkdir(parents=True)
        unavailable_dir.mkdir(parents=True)
        (proxy_dir / "progress.buffer.jsonl").write_text("{}\n")

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--recent", "2",
            "--format", "table",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        assert "Recent 2 tasks:" in r.stdout
        assert "proxy_metrics=progress_events=1" in r.stdout
        assert "unavailable_reason=" in r.stdout

    def test_check_breaker_non_positive_budget_is_ok(
        self, script_runner, env_with_home, state_dir
    ):
        """A non-positive explicit breaker budget exits ok without division."""
        task_id = "20260101-120000-0"
        _write_cost_jsonl(
            state_dir / "cost" / f"{task_id}.jsonl",
            [_record(task_id, input_tokens=100, output_tokens=0)],
        )

        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", task_id,
            "--budget", "-1",
            "--check-breaker",
            env=env_with_home,
        )

        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "ok"

    def test_mode_arguments_are_mutually_exclusive(
        self, script_runner, env_with_home, state_dir
    ):
        """Only one of --task-id, --session-id, and --recent may be selected."""
        r = script_runner(
            "cost-aggregate.py",
            "--state-dir", str(state_dir),
            "--task-id", "20260101-120000-0",
            "--recent", "1",
            env=env_with_home,
        )

        assert r.returncode == 3
        assert "mutually exclusive" in r.stderr
