"""Tests for core/scripts/evolution-analyzer.py.

Exit code contract:
  0 - report generated
  3 - invalid args / missing task directory
"""
from __future__ import annotations

import json
from pathlib import Path


def _write_register(task_dir: Path, *, task_id: str,
                    task: str = "implement evolution report",
                    modified_files: list[str] | None = None) -> None:
    session_id = task_id.rsplit("-", 1)[0]
    payload = {
        "schema_version": 1,
        "task_id": task_id,
        "session_id": session_id,
        "task": task,
        "branch": "crew/evolution-report-analyzer",
        "project_root": "/tmp/project",
        "task_dir": str(task_dir),
        "execution_mode": "single",
        "current_phase": "completed",
        "approval_status": "not_required",
        "verification_status": "passed",
    }
    if modified_files is not None:
        payload["modified_files"] = modified_files
    (task_dir / "register.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_pipeline(task_dir: Path) -> None:
    payload = {
        "schema_version": 1,
        "task": "implement evolution report",
        "stages": [{"agents": ["backend"], "skills": ["tdd"]}, "reviewer"],
        "completed_stages": 2,
    }
    (task_dir / "pipeline.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_progress(task_dir: Path, rows: list[dict]) -> None:
    with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _base_progress(task_id: str) -> list[dict]:
    session_id = task_id.rsplit("-", 1)[0]
    return [
        {
            "ts": "2026-01-01T12:00:00Z",
            "trace_id": f"{session_id}.{task_id}.0.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STARTED",
            "detail": "implement evolution report",
        },
        {
            "ts": "2026-01-01T12:01:00Z",
            "trace_id": f"{session_id}.{task_id}.3.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "COMPLETED",
            "detail": "branch=crew/evolution-report-analyzer commits=1",
        },
    ]


def _seed_task(state_dir: Path, task_id: str = "20260101-120000-0") -> Path:
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True)
    _write_register(task_dir, task_id=task_id)
    _write_pipeline(task_dir)
    _write_progress(task_dir, _base_progress(task_id))
    (task_dir / "result.md").write_text(
        "Status: completed\n"
        "Task: implement evolution report\n"
        "Branch: crew/evolution-report-analyzer\n",
        encoding="utf-8",
    )
    return task_dir


def test_clean_task_writes_report_only_json_and_markdown(
    script_runner, env_with_home, state_dir
):
    task_dir = _seed_task(state_dir)
    json_output = task_dir / "context" / "evolution-report.json"
    markdown_output = task_dir / "context" / "evolution-report.md"

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(json_output),
        "--markdown-output", str(markdown_output),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["task_id"] == task_dir.name
    assert payload["generation_mode"] == "report_only"
    assert payload["meaningful"] is False
    assert payload["asset_candidates"] == []
    assert payload["guardrails"] == {
        "asset_writes": "disabled",
        "generator_invoked": False,
        "verification_bypass": False,
    }
    assert "Learning Report" in markdown_output.read_text(encoding="utf-8")
    assert "No reusable asset candidate" in payload["learning_summary"]

    schema = script_runner(
        "validate-state-schema.py",
        "--state-dir", str(state_dir),
        "--task-dir", str(task_dir),
        env=env_with_home,
    )
    assert schema.returncode == 0, schema.stdout + schema.stderr


def test_register_modified_files_are_reported(script_runner, env_with_home, state_dir):
    task_dir = _seed_task(state_dir)
    _write_register(
        task_dir,
        task_id=task_dir.name,
        modified_files=[
            "core/scripts/evolution-analyzer.py",
            "tests/python/test_evolution_analyzer.py",
        ],
    )

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["signals"]["changed_files"] == [
        "core/scripts/evolution-analyzer.py",
        "tests/python/test_evolution_analyzer.py",
    ]


def test_output_paths_must_stay_inside_task_dir(script_runner, env_with_home, state_dir, tmp_path: Path):
    task_dir = _seed_task(state_dir)

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(tmp_path / "generated-skill.json"),
        env=env_with_home,
    )

    assert result.returncode == 3
    assert "output path must be inside the task directory" in result.stderr


def test_retry_and_reviewer_loopback_are_observed_without_generation(
    script_runner, env_with_home, state_dir
):
    task_dir = _seed_task(state_dir)
    task_id = task_dir.name
    rows = _base_progress(task_id)
    rows.insert(
        1,
        {
            "ts": "2026-01-01T12:00:30Z",
            "trace_id": f"20260101-120000.{task_id}.2.1",
            "task_id": task_id,
            "session_id": "20260101-120000",
            "event": "RETRY",
            "agent": "backend",
            "detail": "reviewer_rejected: missing test coverage",
        },
    )
    _write_progress(task_dir, rows)

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["meaningful"] is True
    assert payload["signals"]["retries"] == 1
    assert payload["signals"]["reviewer_loop_backs"] == 1
    assert payload["asset_candidates"] == []
    assert payload["rejected_candidates"][0]["rejection_reason"] == "insufficient_repeated_evidence"
    assert any(pattern["kind"] == "review_loop_back" for pattern in payload["observed_patterns"])
    assert payload["guardrails"]["generator_invoked"] is False


def test_blocker_signal_is_reported_as_meaningful(script_runner, env_with_home, state_dir):
    task_dir = _seed_task(state_dir)
    register = json.loads((task_dir / "register.json").read_text(encoding="utf-8"))
    register["current_phase"] = "blocked"
    register["blocked_by"] = ["missing approval"]
    (task_dir / "register.json").write_text(json.dumps(register), encoding="utf-8")
    (task_dir / "result.md").write_text(
        "Status: blocked\n"
        "Task: implement evolution report\n"
        "Blocker: missing approval\n",
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["meaningful"] is True
    assert payload["signals"]["blockers"] == ["missing approval"]
    assert any(pattern["kind"] == "blocker" for pattern in payload["observed_patterns"])


def test_output_is_deterministic(script_runner, env_with_home, state_dir):
    task_dir = _seed_task(state_dir)

    first = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )
    second = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert first.stdout == second.stdout


def test_missing_task_dir_exits_3(script_runner, env_with_home, tmp_path: Path):
    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(tmp_path / "missing-task"),
        env=env_with_home,
    )

    assert result.returncode == 3
    assert "task directory not found" in result.stderr
