"""Tests for core/scripts/evolution-analyzer.py.

Exit code contract:
  0 - report generated
  3 - invalid args / missing task directory
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_RETRY = REPO_ROOT / "core" / "agents" / "supervisor-retry.md"
EVOLUTION_ANALYZER = REPO_ROOT / "core" / "scripts" / "evolution-analyzer.py"


def _load_evolution_analyzer():
    spec = importlib.util.spec_from_file_location(
        "evolution_analyzer_under_test",
        EVOLUTION_ANALYZER,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evolution_analyzer = _load_evolution_analyzer()


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


def test_output_paths_must_match_canonical_report_artifacts(
    script_runner, env_with_home, state_dir, tmp_path: Path
):
    """failure-case(regression) - TC-006 rejects non-report task-state writes."""
    rejected_outputs = (
        ("--json-output", "register.json"),
        ("--json-output", "pipeline.json"),
        ("--json-output", "context/other.json"),
        ("--json-output", "context/evolution-report.md"),
        ("--markdown-output", "context/evolution-report.json"),
    )

    for index, (flag, relative_path) in enumerate(rejected_outputs):
        task_dir = _seed_task(state_dir, f"20260101-12000{index}-0")
        result = script_runner(
            "evolution-analyzer.py",
            "--task-dir", str(task_dir),
            flag, str(task_dir / relative_path),
            env=env_with_home,
        )

        assert result.returncode == 3
        assert "output path must be the canonical" in result.stderr

    task_dir = _seed_task(state_dir, "20260101-120010-0")
    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(tmp_path / "generated-skill.json"),
        env=env_with_home,
    )

    assert result.returncode == 3
    assert "output path must be the canonical" in result.stderr


def test_output_path_rejects_canonical_filename_symlink_escape(
    script_runner, env_with_home, state_dir, tmp_path: Path
):
    """failure-case(security) - TC-007 rejects a report symlink outside task state."""
    # given
    task_dir = _seed_task(state_dir)
    outside = tmp_path / "outside.json"
    outside.write_text("sentinel\n", encoding="utf-8")
    json_output = task_dir / "context" / "evolution-report.json"
    json_output.symlink_to(outside)

    # when
    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(json_output),
        env=env_with_home,
    )

    # then
    assert result.returncode == 3
    assert "output path must be the canonical" in result.stderr
    assert outside.read_text(encoding="utf-8") == "sentinel\n"


def test_output_path_rejects_canonical_filename_symlink_loop(
    script_runner, env_with_home, state_dir
):
    """failure-case(security) - invalid report symlink loops return the CLI error contract."""
    # given
    task_dir = _seed_task(state_dir)
    json_output = task_dir / "context" / "evolution-report.json"
    json_output.symlink_to(json_output.name)

    # when
    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(json_output),
        env=env_with_home,
    )

    # then
    assert result.returncode == 3
    assert "output path must be the canonical" in result.stderr


def test_report_write_rejects_symlink_inserted_after_validation(
    monkeypatch, state_dir, tmp_path: Path
):
    """failure-case(security) - descriptor-relative creation closes the TOCTOU gap."""
    task_dir = _seed_task(state_dir)
    json_output = task_dir / "context" / "evolution-report.json"
    outside = tmp_path / "outside.json"
    outside.write_text("sentinel\n", encoding="utf-8")
    args = argparse.Namespace(
        json_output=str(json_output),
        markdown_output=None,
    )
    original_open = evolution_analyzer.os.open
    injected = False

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal injected
        if (
            not injected
            and path == json_output.name
            and dir_fd is not None
            and flags & os.O_CREAT
        ):
            json_output.symlink_to(outside)
            injected = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(evolution_analyzer.os, "open", racing_open)

    with pytest.raises(OSError):
        evolution_analyzer.write_report_outputs({}, args, task_dir)

    assert injected is True
    assert outside.read_text(encoding="utf-8") == "sentinel\n"


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


def test_skill_content_depth_maps_to_relevant_rejected_candidate(
    script_runner, env_with_home, state_dir
):
    """success-case(regression) - maps skill depth to a lightweight skill patch suggestion."""
    task_dir = _seed_task(state_dir)
    (task_dir / "context" / "skill-content-audit.json").write_text(
        json.dumps({
            "shallow_findings": [{"skill": "example", "reason": "too shallow"}],
            "effective_followups": [],
        }),
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
    assert [item["kind"] for item in payload["observed_patterns"]] == [
        "skill_content_depth"
    ]
    assert payload["rejected_candidates"] == [{
        "asset_type": "skill",
        "name": "existing-skill-patch-suggestion",
        "reason": "A single task produced a reusable-work signal; prefer a small patch to an existing skill over creating a new asset.",
        "rejection_reason": "insufficient_repeated_evidence",
        "required_evidence": "Collect repeated occurrences before suggesting a minimal patch to the closest existing skill.",
    }]


def _evolution_closeout_block() -> str:
    document = SUPERVISOR_RETRY.read_text(encoding="utf-8")
    section = document.split(
        "#### 2d. Evolution report — report-only reusable asset analysis",
        1,
    )[1]
    return section.split("```bash\n", 1)[1].split("\n```", 1)[0]


def _write_evolution_stub(agent_crew_home: Path) -> None:
    script = agent_crew_home / "scripts" / "evolution-analyzer.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path


def argument(name: str) -> Path:
    return Path(sys.argv[sys.argv.index(name) + 1])


mode = os.environ["EVOLUTION_STUB_MODE"]
task_dir = argument("--task-dir")
if (task_dir / "context").is_symlink():
    raise SystemExit(3)
for flag in ("--json-output", "--markdown-output"):
    argument(flag).unlink(missing_ok=True)
if mode in {"partial-nonzero", "partial-zero", "success"}:
    argument("--json-output").write_text("fresh-json\\n", encoding="utf-8")
if mode == "success":
    argument("--markdown-output").write_text("fresh-markdown\\n", encoding="utf-8")
if mode != "success":
    for flag in ("--json-output", "--markdown-output"):
        argument(flag).unlink(missing_ok=True)
raise SystemExit(1 if mode in {"fail", "partial-nonzero"} else 0)
""",
        encoding="utf-8",
    )


def test_supervisor_closeout_logs_success_only_for_fresh_complete_reports(tmp_path: Path):
    """boundary-case(audit) - accepts only fresh, complete analyzer reports."""
    agent_crew_home = tmp_path / "home"
    state_dir = tmp_path / "state"
    _write_evolution_stub(agent_crew_home)
    block = _evolution_closeout_block()
    harness = "log_progress() { printf '%s|%s\\n' \"$1\" \"$2\"; }\n" + block

    for mode in ("fail", "partial-nonzero", "partial-zero", "success"):
        task_dir = state_dir / "tasks" / mode
        context_dir = task_dir / "context"
        context_dir.mkdir(parents=True)
        json_output = context_dir / "evolution-report.json"
        markdown_output = context_dir / "evolution-report.md"
        json_output.write_text("stale-json\n", encoding="utf-8")
        markdown_output.write_text("stale-markdown\n", encoding="utf-8")

        result = subprocess.run(
            ["bash", "-c", harness],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "AGENT_CREW_HOME": str(agent_crew_home),
                "AGENT_CREW_EVOLUTION_MODE": "report",
                "EVOLUTION_STUB_MODE": mode,
                "STATE_DIR": str(state_dir),
                "TASK_DIR": str(task_dir),
            },
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        events = [line.split("|", 1)[0] for line in result.stdout.splitlines()]
        if mode == "success":
            assert events == ["EVOLUTION_ANALYZER"]
            assert json_output.read_text(encoding="utf-8") == "fresh-json\n"
            assert markdown_output.read_text(encoding="utf-8") == "fresh-markdown\n"
        else:
            assert events == ["EVOLUTION_ANALYZER_FAILED"]
            assert not json_output.exists()
            assert not markdown_output.exists()


def test_supervisor_closeout_rejects_symlinked_context_before_file_operations(
    tmp_path: Path,
):
    """failure-case(security) - a context symlink cannot redirect closeout writes."""
    agent_crew_home = tmp_path / "home"
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "symlink-context"
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    task_dir.mkdir(parents=True)
    (task_dir / "context").symlink_to(outside, target_is_directory=True)
    _write_evolution_stub(agent_crew_home)

    json_output = outside / "evolution-report.json"
    markdown_output = outside / "evolution-report.md"
    stderr_output = outside / "evolution-report.stderr.txt"
    json_output.write_text("outside-json\n", encoding="utf-8")
    markdown_output.write_text("outside-markdown\n", encoding="utf-8")
    stderr_output.write_text("outside-stderr\n", encoding="utf-8")

    block = _evolution_closeout_block()
    harness = "log_progress() { printf '%s|%s\\n' \"$1\" \"$2\"; }\n" + block
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "AGENT_CREW_HOME": str(agent_crew_home),
            "AGENT_CREW_EVOLUTION_MODE": "report",
            "EVOLUTION_STUB_MODE": "success",
            "STATE_DIR": str(state_dir),
            "TASK_DIR": str(task_dir),
        },
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "EVOLUTION_ANALYZER_FAILED|non_blocking=true reason=analyzer_or_artifact_prep_failed"
    ]
    assert json_output.read_text(encoding="utf-8") == "outside-json\n"
    assert markdown_output.read_text(encoding="utf-8") == "outside-markdown\n"
    assert stderr_output.read_text(encoding="utf-8") == "outside-stderr\n"


def test_supervisor_closeout_does_not_use_symlinked_stderr_artifact(
    tmp_path: Path,
):
    """failure-case(security) - stderr redirection cannot truncate a symlink target."""
    agent_crew_home = tmp_path / "home"
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "symlink-stderr"
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True)
    _write_evolution_stub(agent_crew_home)

    outside_stderr = tmp_path / "outside-stderr.txt"
    outside_stderr.write_text("outside-stderr\n", encoding="utf-8")
    (context_dir / "evolution-report.stderr.txt").symlink_to(outside_stderr)

    block = _evolution_closeout_block()
    harness = "log_progress() { printf '%s|%s\\n' \"$1\" \"$2\"; }\n" + block
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "AGENT_CREW_HOME": str(agent_crew_home),
            "AGENT_CREW_EVOLUTION_MODE": "report",
            "EVOLUTION_STUB_MODE": "success",
            "STATE_DIR": str(state_dir),
            "TASK_DIR": str(task_dir),
        },
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "EVOLUTION_ANALYZER|mode=report artifacts=context/evolution-report.json,context/evolution-report.md"
    ]
    assert outside_stderr.read_text(encoding="utf-8") == "outside-stderr\n"
    assert (context_dir / "evolution-report.json").is_file()
    assert (context_dir / "evolution-report.md").is_file()


def test_supervisor_closeout_delegates_artifact_lifecycle_to_analyzer():
    block = _evolution_closeout_block()

    assert "EVOLUTION_STDERR_OUTPUT" not in block
    assert "rm -f" not in block


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
