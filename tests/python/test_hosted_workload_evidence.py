"""Tests for hosted workload readiness evidence generation."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "hosted-workload-evidence.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


workload_evidence = _load_module(SCRIPT, "hosted_workload_evidence")


def _write_task(root: Path, task_id: str, register: dict, result: str, progress: list[dict] | None = None) -> Path:
    task_dir = root / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "register.json").write_text(json.dumps(register), encoding="utf-8")
    (task_dir / "result.md").write_text(result, encoding="utf-8")
    if progress:
        (task_dir / "progress.buffer.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in progress),
            encoding="utf-8",
        )
    return task_dir


def _write_agent_request(root: Path, request_id: str, request: dict, result: str | None = None) -> Path:
    request_dir = root / "agent-requests" / request_id
    (request_dir / "context").mkdir(parents=True)
    (request_dir / "request.json").write_text(json.dumps(request), encoding="utf-8")
    if result is not None:
        (request_dir / "result.md").write_text(result, encoding="utf-8")
    return request_dir


def test_hosted_workload_evidence_builds_readiness_totals(tmp_path: Path):
    state_dir = tmp_path / "state"
    (state_dir / "tasks").mkdir(parents=True)
    _write_task(
        state_dir,
        "20260101-120000-0",
        {"current_phase": "completed", "host_bridge_status": "auto_completed"},
        "STATUS: completed\n",
        [{"event": "RETRY", "stage": 1, "attempt": 2, "status": "retry"}],
    )
    repaired = _write_task(
        state_dir,
        "20260101-120100-0",
        {"current_phase": "completed", "host_bridge_status": "manual_fallback_completed"},
        "STATUS: completed\n",
    )
    (repaired / "context" / "manual-fallback-repair.json").write_text("{}", encoding="utf-8")
    _write_task(
        state_dir,
        "20260101-120200-0",
        {"current_phase": "handoff_ready", "host_bridge_status": "internal_handoff_ready"},
        "STATUS: handoff_ready\n",
    )

    payload = workload_evidence.build_evidence(state_dir)

    assert payload["tasks"] == 3
    assert payload["successes"] == 2
    assert payload["host_bridge_completed"] == 1
    assert payload["manual_repairs"] == 1
    assert payload["human_interventions"] == 1
    assert payload["retries"] == 1
    assert payload["handoff_ready_tasks"] == 1


def test_hosted_workload_evidence_can_include_direct_agent_requests(tmp_path: Path):
    state_dir = tmp_path / "state"
    (state_dir / "tasks").mkdir(parents=True)
    _write_task(
        state_dir,
        "20260101-120000-0",
        {"current_phase": "completed", "host_bridge_status": "auto_completed"},
        "STATUS: completed\n",
    )
    _write_agent_request(
        state_dir,
        "agent-20260101-120100-0",
        {
            "status": "auto_completed",
            "agent": "analyst",
            "host_bridge_status": "auto_completed",
        },
        "STATUS: completed\n",
    )
    _write_agent_request(
        state_dir,
        "agent-20260101-120200-0",
        {
            "status": "handoff_ready",
            "agent": "historian",
            "host_bridge_status": "failed",
        },
    )

    payload = workload_evidence.build_evidence(state_dir, include_agent_requests=True)

    assert payload["tasks"] == 3
    assert payload["workflow_tasks"] == 1
    assert payload["agent_requests"] == 2
    assert payload["successes"] == 2
    assert payload["host_bridge_completed"] == 2
    assert payload["human_interventions"] == 1
    assert payload["agent_request_successes"] == 1
    assert payload["agent_request_handoff_ready"] == 1


def test_hosted_workload_evidence_cli_writes_json(tmp_path: Path):
    state_dir = tmp_path / "state"
    output = tmp_path / "evidence.json"
    (state_dir / "tasks").mkdir(parents=True)
    _write_task(
        state_dir,
        "20260101-120000-0",
        {"current_phase": "completed", "host_bridge_status": "auto_completed"},
        "STATUS: completed\n",
    )

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--output",
            str(output),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["tasks"] == 1
    assert payload["host_bridge_completed"] == 1


def test_hosted_workload_evidence_helpers_cover_invalid_and_missing_state(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert workload_evidence.read_json(invalid) == {}
    assert workload_evidence.result_status("", {"current_phase": "BLOCKED"}) == "blocked"
    assert workload_evidence.task_dirs(tmp_path / "missing-state", 0) == []
    assert workload_evidence.agent_request_dirs(tmp_path / "missing-state", 0) == []

    try:
        workload_evidence.build_evidence(tmp_path / "missing-state")
    except ValueError as exc:
        assert "state directory not found" in str(exc)
    else:
        raise AssertionError("missing state directory should fail")


def test_hosted_workload_evidence_ignores_malformed_progress_rows(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = _write_task(
        state_dir,
        "20260101-120000-0",
        {"current_phase": "completed"},
        "STATUS: completed\n",
    )
    (task_dir / "progress.buffer.jsonl").write_text(
        "not json\n"
        + json.dumps({"event": "STAGE_DONE", "stage": "x", "attempt": "y"}) + "\n",
        encoding="utf-8",
    )

    assert workload_evidence.progress_retry_count(task_dir) == 0


def test_hosted_workload_evidence_agent_request_auto_completed_without_result(tmp_path: Path):
    state_dir = tmp_path / "state"
    request_dir = _write_agent_request(
        state_dir,
        "agent-20260101-120000-0",
        {"status": "auto_completed", "agent": "analyst", "host_bridge_status": "auto_completed"},
    )

    record = workload_evidence.agent_request_record(request_dir)

    assert record["status"] == "completed"
    assert record["task_success"] is True


def test_hosted_workload_evidence_cli_reports_missing_state_and_text_summary(tmp_path: Path):
    missing = subprocess.run(
        ["python3", str(SCRIPT), "--state-dir", str(tmp_path / "missing")],
        text=True,
        capture_output=True,
    )
    assert missing.returncode == 2
    assert "state directory not found" in missing.stderr

    state_dir = tmp_path / "state"
    (state_dir / "tasks").mkdir(parents=True)
    _write_task(
        state_dir,
        "20260101-120000-0",
        {"current_phase": "completed", "host_bridge_status": "auto_completed"},
        "STATUS: completed\n",
    )
    text = subprocess.run(
        ["python3", str(SCRIPT), "--state-dir", str(state_dir)],
        text=True,
        capture_output=True,
    )

    assert text.returncode == 0, text.stdout + text.stderr
    assert "PASS: hosted workload evidence" in text.stdout
    assert "tasks=1 successes=1" in text.stdout
