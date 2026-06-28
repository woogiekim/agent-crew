"""Tests for host-bridge-token-usage.py."""
from __future__ import annotations

import json
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_extracts_claude_model_usage_to_cost_jsonl(
    script_runner, env_with_home, state_dir, tmp_path
):
    task_id = "20260101-120000-0"
    payload = {
        "type": "result",
        "subtype": "success",
        "modelUsage": {
            "claude-haiku-4-5": {
                "inputTokens": 120,
                "outputTokens": 34,
                "cacheCreationInputTokens": 56,
                "cacheReadInputTokens": 78,
                "costUSD": 0.0123,
            }
        },
    }
    source = tmp_path / "claude.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = script_runner(
        "host-bridge-token-usage.py",
        "--task-id",
        task_id,
        "--task-dir",
        str(state_dir / "tasks" / task_id),
        "--provider",
        "claude",
        "--agent",
        "host-bridge",
        "--tier",
        "light",
        "--source",
        str(source),
        "--format",
        "claude-json",
        "--timestamp",
        "2026-01-01T12:00:00Z",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stderr
    rows = _read_jsonl(state_dir / "cost" / f"{task_id}.jsonl")
    assert rows == [
        {
            "schema_version": 1,
            "ts": "2026-01-01T12:00:00Z",
            "task_id": task_id,
            "session_id": "20260101-120000",
            "agent": "host-bridge",
            "stage": "host_bridge",
            "provider": "claude",
            "source": str(source),
            "model": "claude-haiku-4-5",
            "tier": "light",
            "input_tokens": 120,
            "output_tokens": 34,
            "cache_creation_tokens": 56,
            "cache_read_tokens": 78,
            "cost_usd": 0.0123,
        }
    ]


def test_extracts_codex_total_tokens_to_cost_jsonl(
    script_runner, env_with_home, state_dir, tmp_path
):
    task_id = "20260101-120000-0"
    source = tmp_path / "codex.log"
    source.write_text(
        "status: ok\n"
        "tokens used\n"
        "28,904\n",
        encoding="utf-8",
    )

    result = script_runner(
        "host-bridge-token-usage.py",
        "--task-id",
        task_id,
        "--task-dir",
        str(state_dir / "tasks" / task_id),
        "--provider",
        "codex",
        "--agent",
        "host-bridge",
        "--model",
        "gpt-5.5",
        "--tier",
        "balanced",
        "--source",
        str(source),
        "--format",
        "codex-text",
        "--timestamp",
        "2026-01-01T12:00:00Z",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stderr
    rows = _read_jsonl(state_dir / "cost" / f"{task_id}.jsonl")
    assert rows[0]["provider"] == "codex"
    assert rows[0]["model"] == "gpt-5.5"
    assert rows[0]["total_tokens"] == 28904
    assert rows[0]["input_tokens"] == 0
    assert rows[0]["output_tokens"] == 0
    assert rows[0]["usage_granularity"] == "total_only"
