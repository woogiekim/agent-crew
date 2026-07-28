"""Boundary tests for question-shaped natural language in auto-route."""
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
        check=True,
    )
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "prompt",
    [
        "어떻게 동작하나요?",
        "what just ran?",
        "explain how crew:agent works",
        "read-only review this file",
        "fix this bug?",
    ],
)
def test_question_shaped_natural_language_emits_no_hidden_route(prompt: str):
    assert _run_hook(prompt) is None


@pytest.mark.parametrize(
    "prompt",
    [
        "$crew:agent analyst 어떻게 동작하나요?",
        "crew:agent historian what just ran?",
    ],
)
def test_explicit_question_commands_emit_command_context(prompt: str):
    out = _run_hook(prompt)
    assert out is not None
    ctx = out["hookSpecificOutput"]["additionalContext"]

    assert "[agent-crew] COMMAND" in ctx
    assert "~/.agent-crew/commands/agent.md" in ctx
