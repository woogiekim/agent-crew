"""Regression tests for explicit workflow execution routing."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = REPO_ROOT / "core" / "hooks" / "auto-route.sh"


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


def _context(prompt: str) -> str:
    output = _run_hook(prompt)
    assert output, f"Expected routing directive for {prompt!r}"
    return output["hookSpecificOutput"]["additionalContext"]


def _directive_type(prompt: str) -> str:
    output = _run_hook(prompt)
    if not output:
        return "EMPTY"
    ctx = output["hookSpecificOutput"]["additionalContext"]
    if "[agent-crew] COMMAND" in ctx:
        return "COMMAND"
    if "[agent-crew] STOP" in ctx:
        return "STOP"
    if "[agent-crew] ROUTE" in ctx:
        return "ROUTE"
    return "OTHER"


def test_list_item_crew_run_wrapper_invocation_is_command():
    """success-case(command-boundary) - list-item $crew:run stays a workflow origin."""
    # given
    prompt = "- $crew:run 코드리뷰"

    # when
    ctx = _context(prompt)

    # then
    assert "[agent-crew] COMMAND" in ctx
    assert "explicit $crew:run invocation detected" in ctx
    assert "Command arguments detected: 코드리뷰" in ctx
    assert "ROUTE_LOCK: crew:agent" not in ctx


def test_mixed_review_and_crew_run_parallel_prompt_emits_no_hidden_route():
    """non-leading natural language/list content is not classified by the hook."""
    # given
    prompt = "- $review\n- $crew:run 코드리뷰\n\n병렬실행"

    # when
    out = _run_hook(prompt)

    # then
    assert out == {}


@pytest.mark.parametrize(
    "prompt",
    [
        "코드리뷰 병렬실행",
        "코드리뷰 병렬 실행",
        "코드리뷰 병렬로 실행",
    ],
)
def test_korean_parallel_review_execution_emits_no_hidden_route(prompt: str):
    """Korean natural-language execution phrasing is not auto-classified."""
    # given / when
    route = _directive_type(prompt)

    # then
    assert route == "EMPTY"


@pytest.mark.parametrize(
    "prompt",
    [
        "코드리뷰만 해줘, 수정하지 마",
        "read-only review this file",
        "이 코드가 어떻게 동작해?",
        "$review",
    ],
)
def test_read_only_review_and_questions_emit_no_hidden_route(prompt: str):
    """Natural-language read-only phrasing is not auto-classified."""
    # given / when
    route = _directive_type(prompt)

    # then
    assert route == "EMPTY"


@pytest.mark.parametrize(
    "prompt",
    [
        "crew:task demo",
        "$crew:task demo",
        "ac:task demo",
        "crew:crew demo",
        "$crew:crew demo",
        "ac:crew demo",
    ],
)
def test_removed_task_alias_emits_no_command_context(prompt: str):
    assert _run_hook(prompt) == {}
