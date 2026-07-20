"""Regression coverage for the Claude PostToolUse cost-tracker hook."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _trace_gate_fixtures as fx  # noqa: E402


HOOK = fx.REPO_ROOT / "core" / "hooks" / "cost-tracker.sh"


def _mark_active(state_dir: Path, task_id: str) -> None:
    marker = state_dir / "tasks" / f"active.{task_id}"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")


def _usage_payload() -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "session_id": "20260721-000000",
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/python/test_cost_tracker_hook.py"},
        "tool_response": {"stdout": "ok", "returncode": 0},
        "model": "claude-sonnet-5",
        "usage": {
            "input_tokens": 11,
            "output_tokens": 7,
            "cache_creation_input_tokens": 3,
            "cache_read_input_tokens": 5,
        },
    }


def test_cost_tracker_reads_post_tool_payload_and_records_active_task_cost(tmp_path):
    state_dir, task_id, _task_dir = fx.make_state_task(tmp_path)
    _mark_active(state_dir, task_id)

    result = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(_usage_payload()),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "AGENT_CREW_STATE_DIR": str(state_dir),
            "AGENT_CREW_TASK_ID": task_id,
            "AGENT_CREW_PROJECT": state_dir.name,
            "AGENT_CREW_SESSION_ID": "session-1",
            "AGENT_CREW_AGENT_NAME": "backend",
            "AGENT_CREW_STAGE_INDEX": "2",
            "AGENT_CREW_TIER": "deep",
        },
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
    rows = [
        json.loads(line)
        for line in (state_dir / "cost" / f"{task_id}.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["input_tokens"] == 11
    assert rows[0]["output_tokens"] == 7
    assert rows[0]["cache_creation_tokens"] == 3
    assert rows[0]["cache_read_tokens"] == 5
    assert rows[0]["session_id"] == "session-1"
    assert rows[0]["agent"] == "backend"
    assert rows[0]["stage"] == 2
    assert rows[0]["tier"] == "deep"


def test_cost_tracker_noops_for_payload_without_usage(tmp_path):
    state_dir, task_id, _task_dir = fx.make_state_task(tmp_path)
    _mark_active(state_dir, task_id)
    payload = _usage_payload()
    payload["usage"] = {}

    result = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "AGENT_CREW_STATE_DIR": str(state_dir),
            "AGENT_CREW_TASK_ID": task_id,
        },
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
    assert not (state_dir / "cost" / f"{task_id}.jsonl").exists()
