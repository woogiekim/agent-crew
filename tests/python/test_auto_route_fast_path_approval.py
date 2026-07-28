"""Tests for explicit operational command handling in auto-route."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = REPO_ROOT / "core" / "hooks" / "auto-route.sh"


def _run_hook(prompt: str) -> dict | None:
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=json.dumps({"prompt": prompt}),
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "prompt",
    [
        "git status",
        "status",
        "git commit",
        "push",
        "ENRTC-273 상태 변경",
        "set ENRTC-273 status to Done",
    ],
)
def test_operational_natural_language_emits_no_hidden_route(prompt: str):
    assert _run_hook(prompt) is None


@pytest.mark.parametrize(
    "prompt",
    [
        "$crew:run git status",
        "crew:run git status",
        "$crew:agent historian git status",
        "crew:agent historian git status",
    ],
)
def test_explicit_operational_commands_emit_command_context(prompt: str):
    out = _run_hook(prompt)
    assert out is not None
    ctx = out["hookSpecificOutput"]["additionalContext"]

    assert "[agent-crew] COMMAND" in ctx
    assert "[agent-crew] STOP" not in ctx
    assert "[agent-crew] ROUTE" not in ctx
