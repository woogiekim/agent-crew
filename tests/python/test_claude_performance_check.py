"""Tests for Claude adapter performance budget checks."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "claude-performance-check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("claude_performance_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load_module()


def test_load_json_returns_empty_for_invalid_or_non_object_json(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert module.load_json(invalid) == {}

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert module.load_json(array) == {}


def test_iter_hook_entries_ignores_malformed_hook_shapes():
    settings = {
        "hooks": {
            "UserPromptSubmit": [
                "not a block",
                {"matcher": "*", "hooks": ["not a hook"]},
                {"matcher": "*", "hooks": [{"command": "echo unrelated", "timeout": 5}]},
                {"matcher": "*", "hooks": [{"command": "bash ~/.agent-crew/hooks/auto-route.sh", "timeout": "slow"}]},
            ],
            "PostToolUse": "not a list",
        }
    }

    entries = module.iter_hook_entries(settings)

    assert entries == [
        {
            "event": "UserPromptSubmit",
            "matcher": "*",
            "command": "bash ~/.agent-crew/hooks/auto-route.sh",
            "timeout_seconds": 0,
        }
    ]
    assert module.iter_hook_entries({"hooks": []}) == []


def test_claude_performance_text_reports_warning_details(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    (claude_dir / "agent-crew").mkdir(parents=True)
    (claude_dir / "agent-crew" / "large.txt").write_text("x" * 2048, encoding="utf-8")
    (claude_dir / "agents").mkdir()
    (claude_dir / "agents" / "large.md").write_text("x" * 2048, encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--claude-dir",
            str(claude_dir),
            "--agent-crew-kb",
            "0",
            "--agents-kb",
            "0",
            "--file-count",
            "0",
            "--largest-agent-kb",
            "0",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "WARN: claude performance budgets" in result.stdout
    assert "- agent_crew_size:" in result.stdout
    assert "- agents_size:" in result.stdout
