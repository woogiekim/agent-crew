"""Tests for explicit command boundary in auto-route.

The UserPromptSubmit hook must not decide whether ordinary natural language
should become crew:agent or crew:run. It only adapts explicit agent-crew command
syntax into command context.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = REPO_ROOT / "core" / "hooks" / "auto-route.sh"
ROUTING_RULES_PATH = REPO_ROOT / "core" / "rules" / "agent-routing.md"


def _run_hook(prompt: str) -> dict:
    env = os.environ.copy()
    env["AGENT_CREW_HOST_BRIDGE_COMMAND"] = "true"

    result = subprocess.run(
        [str(HOOK_PATH)],
        input=json.dumps({"prompt": prompt}),
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    output = result.stdout.strip()
    if not output:
        return {}
    return json.loads(output)


def _directive_type(prompt: str) -> str:
    out = _run_hook(prompt)
    if not out:
        return "EMPTY"
    ctx = out["hookSpecificOutput"]["additionalContext"]
    if "[agent-crew] COMMAND" in ctx:
        return "COMMAND"
    if "[agent-crew] ROUTE" in ctx:
        return "ROUTE"
    if "[agent-crew] STOP" in ctx:
        return "STOP"
    return "OTHER"


@pytest.mark.parametrize(
    "prompt",
    [
        "explain how the supervisor works",
        "what just ran in this session",
        "fix the bug in auto-route",
        "add a new test for routing",
        "update README.md to mention X",
        "commit the staged changes",
        "push",
        "merge to main",
        "로그인이 안돼",
        "버그를 수정해주세요",
        "the docs feel inconsistent",
    ],
)
def test_natural_language_prompts_emit_no_route_or_stop(prompt: str):
    assert _directive_type(prompt) == "EMPTY"


@pytest.mark.parametrize(
    ("prompt", "command_file"),
    [
        ("$crew:run 코드리뷰", "run.md"),
        ("$crew:agent analyst 코드 구조 설명", "agent.md"),
        ("crew:run 코드리뷰", "run.md"),
        ("crew:agent analyst 코드 구조 설명", "agent.md"),
        ("crew:update", "update.md"),
    ],
)
def test_explicit_agent_crew_commands_still_emit_command_context(prompt: str, command_file: str):
    out = _run_hook(prompt)
    ctx = out["hookSpecificOutput"]["additionalContext"]

    assert "[agent-crew] COMMAND" in ctx
    assert f"~/.agent-crew/commands/{command_file}" in ctx
    assert "ROUTE_LOCK: crew:agent" not in ctx
    assert "ROUTE_LOCK: crew:run" not in ctx


@pytest.mark.parametrize("prompt", ["$crew-run 코드리뷰", "$crew-agent analyst 코드 구조 설명"])
def test_legacy_crew_dash_wrappers_are_not_command_context(prompt: str):
    assert _directive_type(prompt) == "EMPTY"


def test_agent_routing_rules_document_explicit_command_boundary():
    text = ROUTING_RULES_PATH.read_text(encoding="utf-8")

    assert "Explicit command boundary" in text
    assert "must not choose `crew:agent` vs `crew:run`" in text
    assert "ordinary natural-language prompt passes" in text
