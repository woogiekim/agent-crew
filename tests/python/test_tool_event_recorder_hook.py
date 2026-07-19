"""PostToolUse tool-event-recorder hook tests (F7 / AC-006).

Spec: context/prd.md § F7 + AC-006 + NFR security; checklist
context/test-checklist.md (TC-048..TC-051). The hook
``core/hooks/tool-event-recorder.sh`` is exercised as a black box (stdin
PostToolUse payload + env task resolution, mirroring cost-tracker.sh); its
source is NOT read (the parallel implementer authors it).

RED state is expected: the hook does not exist yet, so append/redaction
assertions fail until F7 lands. TC-050 (downstream-consumer schema
compatibility) is hook-independent — it writes a schema-v1 row directly and
runs the existing consumers.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _trace_gate_fixtures as fx  # noqa: E402

HOOK = fx.REPO_ROOT / "core" / "hooks" / "tool-event-recorder.sh"
SCRIPTS = fx.SCRIPTS_DIR
CODEX_SETUP = fx.REPO_ROOT / "adapters" / "codex" / "setup.sh"
CLAUDE_SETUP = fx.REPO_ROOT / "adapters" / "claude" / "setup.sh"

APPEND_TOOL_EVENT_KEYS = {
    "schema_version",
    "trace_id",
    "tool_name",
    "action_summary",
    "started_at",
    "ended_at",
    "status",
    "exit_code",
    "token_usage_ref",
    "failure_class",
}


def _mark_active(state_dir: Path, task_id: str) -> None:
    """Drop the runtime active-task marker used by hook task resolution."""
    marker = state_dir / "tasks" / f"active.{task_id}"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")


def run_hook(state_dir: Path, task_id: str, payload: dict, *, extra_env: dict | None = None):
    _mark_active(state_dir, task_id)
    env = os.environ.copy()
    env["AGENT_CREW_STATE_DIR"] = str(state_dir)
    env["AGENT_CREW_TASK_ID"] = task_id
    env["AGENT_CREW_PROJECT"] = state_dir.name
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
    )


def _bash_payload(command: str, *, exit_code: int = 0) -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "session_id": "20260715-000000",
        "cwd": str(fx.REPO_ROOT),
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {
            "exit_code": exit_code,
            "returncode": exit_code,
            "stdout": "ok",
            "stderr": "",
            "interrupted": False,
        },
    }


def _rows(task_dir: Path) -> list[dict]:
    path = task_dir / "tool-events.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_boundary_case_hook_appends_schema_v1_row_for_bash(tmp_path):
    # TC-048: Bash tool result while a crew task is active -> one schema-v1 row.
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path)

    result = run_hook(state_dir, task_id, _bash_payload("pytest tests/", exit_code=0))

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
    rows = _rows(task_dir)
    assert len(rows) == 1
    row = rows[0]
    assert APPEND_TOOL_EVENT_KEYS.issubset(row.keys())
    assert row["schema_version"] == 1
    assert row["tool_name"] == "Bash"
    assert isinstance(row["exit_code"], int)
    assert isinstance(row["action_summary"], str) and row["action_summary"]


def test_boundary_case_hook_noop_without_active_task(tmp_path):
    # TC-049: no active crew task -> no row appended.
    state_dir = tmp_path / "state" / "project"
    (state_dir / "tasks").mkdir(parents=True)
    env = {"AGENT_CREW_TASK_ID": ""}
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(_bash_payload("pytest tests/")),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "AGENT_CREW_STATE_DIR": str(state_dir),
            "AGENT_CREW_PROJECT": "project",
            **env,
        },
    )

    assert result.returncode == 0
    # No task dir -> nowhere to append; the hook must be a silent no-op.
    assert not list((state_dir / "tasks").glob("*/tool-events.jsonl"))


def test_boundary_case_hook_noop_for_non_bash_tool(tmp_path):
    # TC-049 (second guard): a non-Bash tool call appends nothing.
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path)

    result = run_hook(
        state_dir,
        task_id,
        {"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}, "tool_response": {}},
    )

    assert result.returncode == 0
    assert _rows(task_dir) == []


def test_boundary_case_hook_accepts_valid_json_whitespace_before_colon(tmp_path):
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path)
    _mark_active(state_dir, task_id)
    payload = json.dumps(_bash_payload("pytest tests/"), indent=2).replace(
        '"tool_name": "Bash"',
        '"tool_name" : "Bash"',
    )

    result = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "AGENT_CREW_STATE_DIR": str(state_dir),
            "AGENT_CREW_TASK_ID": task_id,
            "AGENT_CREW_PROJECT": state_dir.name,
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_rows(task_dir)) == 1


def test_security_case_hook_redacts_secret_like_tokens(tmp_path):
    # TC-051: command text with a secret-like token is redacted in the row.
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path)
    secret = "sk-livesecret1234567890"

    result = run_hook(state_dir, task_id, _bash_payload(f"deploy --key {secret}", exit_code=0))

    assert result.returncode == 0, result.stdout + result.stderr
    rows = _rows(task_dir)
    assert len(rows) == 1
    assert secret not in rows[0]["action_summary"]


def test_external_dependency_case_downstream_consumers_read_hook_rows(tmp_path):
    # TC-050: consumers count schema-v1 rows without error.
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path)
    fx.write_tool_events(
        task_dir,
        [
            fx.tool_event_row(
                tool_name="Bash",
                action_summary="pytest tests/",
                started_at="2026-07-15T00:00:01Z",
                ended_at="2026-07-15T00:00:02Z",
                status="completed",
                exit_code=0,
            )
        ],
    )

    for script, args in (
        ("telemetry-aggregate.py", ["--state-dir", str(state_dir), "--task-id", task_id]),
        ("cost-aggregate.py", ["--state-dir", str(state_dir), "--task-id", task_id]),
    ):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args], text=True, capture_output=True
        )
        assert proc.returncode == 0, f"{script}: {proc.stdout}\n{proc.stderr}"


def test_regression_case_supported_host_setups_register_tool_event_recorder():
    # TC-055: setup/update must wire the hook into supported host configs;
    # otherwise trace-first repair gates have no new Bash execution rows to read.
    codex_setup = CODEX_SETUP.read_text(encoding="utf-8")
    claude_setup = CLAUDE_SETUP.read_text(encoding="utf-8")

    assert "tool-event-recorder.sh" in codex_setup
    assert "tool-event-recorder.sh" in claude_setup
    assert '"matcher": "Bash"' in codex_setup
    assert '"PostToolUse"' in codex_setup
    assert '"Bash"' in claude_setup
    assert '"PostToolUse"' in claude_setup
