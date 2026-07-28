"""Regression tests for explicit Codex agent-crew wrapper invocations."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = REPO_ROOT / "core" / "hooks" / "auto-route.sh"


def _run_hook(prompt: str, *, bridge_configured: bool = True) -> dict:
    env = os.environ.copy()
    if bridge_configured:
        env["AGENT_CREW_HOST_BRIDGE_COMMAND"] = "true"
    else:
        env.pop("AGENT_CREW_HOST_BRIDGE_COMMAND", None)
        env["AGENT_CREW_HOST_BRIDGE_DISABLE_DEFAULT"] = "1"

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


def test_success_case_leading_crew_run_wrapper_invocation_is_command():
    """success-case(command-boundary) - leading $crew:run passes trailing text as task args."""
    # given
    prompt = "$crew:run 코드리뷰"

    # when
    ctx = _context(prompt)

    # then
    assert "[agent-crew] COMMAND" in ctx
    assert "explicit $crew:run invocation detected" in ctx
    assert "Execute the workflow defined in ~/.agent-crew/commands/run.md" in ctx
    assert "Command arguments detected: 코드리뷰" in ctx
    assert "ROUTE_LOCK: crew:agent" not in ctx


def test_success_case_other_leading_crew_wrappers_are_commands():
    """success-case(command-boundary) - leading $crew:* wrappers use command routing."""
    # given
    scenarios = {
        "$crew:agent analyst \"what changed?\"": "agent.md",
        "$crew:status": "status.md",
        "$crew:update": "update.md",
        "$crew:smm": "smm.md",
        "$crew:agent-maker routing specialist": "agent-maker.md",
    }

    for prompt, command_file in scenarios.items():
        # when
        ctx = _context(prompt)

        # then
        assert "[agent-crew] COMMAND" in ctx, prompt
        assert f"Execute the workflow defined in ~/.agent-crew/commands/{command_file}" in ctx
        assert "ROUTE_LOCK: crew:agent" not in ctx
        assert "ROUTE_LOCK: crew:run" not in ctx


def test_success_case_backticked_crew_run_skill_review_emits_no_hidden_route():
    """success-case(intent-boundary) - non-command natural language is not routed by the hook."""
    # given
    prompt = "`$crew:run` 스킬을 코드리뷰해"

    # when
    out = _run_hook(prompt)

    # then
    assert out == {}
