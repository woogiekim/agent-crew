"""Tests for operational prompt routing in core/hooks/auto-route.sh.

Issue #126: top-level operational prompts must not be handled by an inline
FAST-PATH. Read-only status requests route to crew:agent/historian, and
mutating git requests route to crew:run.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = REPO_ROOT / "core" / "hooks" / "auto-route.sh"


def _run_hook(prompt: str) -> dict | None:
    """Feed *prompt* to auto-route.sh and return parsed JSON output, or None."""
    payload = json.dumps({"prompt": prompt})
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    if not result.stdout.strip():
        return None
    return json.loads(result.stdout)


def _get_context(prompt: str) -> str:
    out = _run_hook(prompt)
    assert out is not None, f"Expected route directive for {prompt!r}"
    return out.get("hookSpecificOutput", {}).get("additionalContext", "")


def assert_not_fast_path(ctx: str) -> None:
    assert "[agent-crew] FAST-PATH" not in ctx
    assert "Execute directly" not in ctx
    assert "Show approval gate first" not in ctx


class TestReadOnlyOperationalIntentsRouteToAgent:
    @pytest.mark.parametrize("prompt", [
        "git status",
        "status",
        "상태 확인",
        "상태",
    ])
    def test_status_routes_to_historian(self, prompt: str):
        ctx = _get_context(prompt)
        assert_not_fast_path(ctx)
        assert "[agent-crew] ROUTE" in ctx
        assert "ROUTE_LOCK: crew-agent" in ctx
        assert "TARGET_AGENT: historian" in ctx
        assert 'crew:agent "historian"' in ctx


class TestMutatingOperationalIntentsRouteToCrewRun:
    @pytest.mark.parametrize("prompt", [
        "git commit",
        "commit",
        "커밋",
        "git push",
        "push",
        "푸시",
        "git merge",
        "merge",
        "머지",
        "병합",
        "git tag",
        "태그",
        "rollback",
        "revert",
        "롤백",
        "되돌리기",
        "merge and push",
        "머지 하고 푸시",
        "push and merge",
        "푸시 하고 머지",
    ])
    def test_mutating_git_intents_route_to_crew_run(self, prompt: str):
        ctx = _get_context(prompt)
        assert_not_fast_path(ctx)
        assert "[agent-crew] STOP" in ctx
        assert "ROUTE_LOCK: crew-run" in ctx
        assert "FIRST_ACTION_ONLY:" in ctx
        assert "crew:run" in ctx


class TestIssueStatusLifecycleStillWins:
    def test_issue_status_transition_routes_to_issuer(self):
        ctx = _get_context("set ENRTC-273 status to Done")
        assert_not_fast_path(ctx)
        assert "issue lifecycle" in ctx
        assert 'crew:run "issuer task"' in ctx

    def test_korean_issue_status_transition_routes_to_issuer(self):
        ctx = _get_context("ENRTC-273 상태 변경")
        assert_not_fast_path(ctx)
        assert "issue lifecycle" in ctx
        assert 'crew:run "issuer task"' in ctx
