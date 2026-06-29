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
    ctx = _context(prompt)
    if "[agent-crew] COMMAND" in ctx:
        return "COMMAND"
    if "[agent-crew] STOP" in ctx:
        return "STOP"
    if "[agent-crew] ROUTE" in ctx:
        return "ROUTE"
    return "OTHER"


def test_list_item_crew_run_wrapper_invocation_is_command():
    """success-case(command-boundary) - list-item $crew-run stays a workflow origin."""
    # given
    prompt = "- $crew-run 코드리뷰"

    # when
    ctx = _context(prompt)

    # then
    assert "[agent-crew] COMMAND" in ctx
    assert "explicit $crew-run invocation detected" in ctx
    assert "Command arguments detected: 코드리뷰" in ctx
    assert "ROUTE_LOCK: crew-agent" not in ctx


def test_mixed_review_and_crew_run_parallel_prompt_routes_to_crew_run():
    """success-case(precedence) - explicit workflow execution beats read-only review fallback."""
    # given
    prompt = "- $review\n- $crew-run 코드리뷰\n\n병렬실행"

    # when
    ctx = _context(prompt)

    # then
    assert "[agent-crew] STOP" in ctx
    assert "ROUTE_LOCK: crew-run" in ctx
    assert "ROUTE_LOCK: crew-agent" not in ctx
    assert "Scope: read-only analysis" not in ctx


@pytest.mark.parametrize(
    "prompt",
    [
        "코드리뷰 병렬실행",
        "코드리뷰 병렬 실행",
        "코드리뷰 병렬로 실행",
    ],
)
def test_korean_parallel_review_execution_routes_to_crew_run(prompt: str):
    """success-case(korean-execution) - Korean parallel review execution routes to crew-run."""
    # given / when
    route = _directive_type(prompt)

    # then
    assert route == "STOP"


@pytest.mark.parametrize(
    "prompt",
    [
        "코드리뷰만 해줘, 수정하지 마",
        "read-only review this file",
        "이 코드가 어떻게 동작해?",
        "$review",
    ],
)
def test_read_only_review_and_questions_still_route_to_crew_agent(prompt: str):
    """success-case(read-only-boundary) - read-only review and questions stay on crew-agent."""
    # given / when
    route = _directive_type(prompt)

    # then
    assert route == "ROUTE"
