"""Tests for the fast-path approval-gate fix in core/hooks/auto-route.sh.

Issue #25: the fast-path hook incorrectly appended "Show approval gate first."
to ALL trivial intents, including read-only ones like `status`.

The fix gates the approval suffix on DESTRUCTIVE_INTENTS only.  These tests
verify:

1. Read-only intents (status, commit) do NOT receive the approval suffix.
2. Destructive intents (push, merge, deploy, tag, rollback, merge+push,
   push+merge) DO receive the approval suffix.
3. The FAST-PATH directive is still emitted for all matched intents.

Test strategy: invoke the actual auto-route.sh subprocess with a crafted
JSON payload and inspect the `additionalContext` field in the response.
This is an integration-style test — it exercises the live hook file without
copying any logic.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = REPO_ROOT / "core" / "hooks" / "auto-route.sh"

APPROVAL_SUFFIX = "Show approval gate first."


def _run_hook(prompt: str) -> dict | None:
    """Feed *prompt* to auto-route.sh and return parsed JSON output, or None."""
    payload = json.dumps({"prompt": prompt})
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _get_context(prompt: str) -> str | None:
    """Return the additionalContext string for *prompt*, or None if no output."""
    out = _run_hook(prompt)
    if out is None:
        return None
    return (
        out.get("hookSpecificOutput", {}).get("additionalContext", "")
    )


# ---------------------------------------------------------------------------
# Helper predicates
# ---------------------------------------------------------------------------

def is_fast_path(ctx: str | None) -> bool:
    return ctx is not None and "[agent-crew] FAST-PATH" in ctx


def has_approval_suffix(ctx: str | None) -> bool:
    return ctx is not None and APPROVAL_SUFFIX in ctx


# ===========================================================================
# Read-only intents — must NOT receive approval suffix (issue #25 fix)
# ===========================================================================

class TestReadOnlyIntentsNoApproval:
    """Read-only intents must emit FAST-PATH but must NOT include the approval suffix."""

    @pytest.mark.parametrize("prompt", [
        "git status",
        "status",
        "상태 확인",
        "상태",
    ])
    def test_status_no_approval_suffix(self, prompt: str):
        ctx = _get_context(prompt)
        assert is_fast_path(ctx), (
            f"Expected FAST-PATH directive for {prompt!r}, got: {ctx!r}"
        )
        assert not has_approval_suffix(ctx), (
            f"status intent {prompt!r} must NOT include approval suffix, got: {ctx!r}"
        )

    @pytest.mark.parametrize("prompt", [
        "git commit",
        "commit",
        "커밋",
    ])
    def test_commit_no_approval_suffix(self, prompt: str):
        ctx = _get_context(prompt)
        assert is_fast_path(ctx), (
            f"Expected FAST-PATH directive for {prompt!r}, got: {ctx!r}"
        )
        assert not has_approval_suffix(ctx), (
            f"commit intent {prompt!r} must NOT include approval suffix, got: {ctx!r}"
        )


# ===========================================================================
# Destructive intents — MUST receive approval suffix
# ===========================================================================

class TestDestructiveIntentsHaveApproval:
    """Destructive intents must emit FAST-PATH AND include the approval suffix."""

    @pytest.mark.parametrize("prompt", [
        "git push",
        "push",
        "푸시",
    ])
    def test_push_has_approval_suffix(self, prompt: str):
        ctx = _get_context(prompt)
        assert is_fast_path(ctx), (
            f"Expected FAST-PATH directive for {prompt!r}, got: {ctx!r}"
        )
        assert has_approval_suffix(ctx), (
            f"push intent {prompt!r} MUST include approval suffix, got: {ctx!r}"
        )

    @pytest.mark.parametrize("prompt", [
        "git merge",
        "merge",
        "머지",
        "병합",
    ])
    def test_merge_has_approval_suffix(self, prompt: str):
        ctx = _get_context(prompt)
        assert is_fast_path(ctx), (
            f"Expected FAST-PATH directive for {prompt!r}, got: {ctx!r}"
        )
        assert has_approval_suffix(ctx), (
            f"merge intent {prompt!r} MUST include approval suffix, got: {ctx!r}"
        )

    @pytest.mark.parametrize("prompt", [
        "git tag",
        "태그",
    ])
    def test_tag_has_approval_suffix(self, prompt: str):
        ctx = _get_context(prompt)
        assert is_fast_path(ctx), (
            f"Expected FAST-PATH directive for {prompt!r}, got: {ctx!r}"
        )
        assert has_approval_suffix(ctx), (
            f"tag intent {prompt!r} MUST include approval suffix, got: {ctx!r}"
        )

    @pytest.mark.parametrize("prompt", [
        "rollback",
        "revert",
        "롤백",
        "되돌리기",
    ])
    def test_rollback_has_approval_suffix(self, prompt: str):
        ctx = _get_context(prompt)
        assert is_fast_path(ctx), (
            f"Expected FAST-PATH directive for {prompt!r}, got: {ctx!r}"
        )
        assert has_approval_suffix(ctx), (
            f"rollback intent {prompt!r} MUST include approval suffix, got: {ctx!r}"
        )

    @pytest.mark.parametrize("prompt", [
        "merge and push",
        "머지 하고 푸시",
    ])
    def test_merge_and_push_has_approval_suffix(self, prompt: str):
        ctx = _get_context(prompt)
        assert is_fast_path(ctx), (
            f"Expected FAST-PATH directive for {prompt!r}, got: {ctx!r}"
        )
        assert has_approval_suffix(ctx), (
            f"merge+push intent {prompt!r} MUST include approval suffix, got: {ctx!r}"
        )

    @pytest.mark.parametrize("prompt", [
        "push and merge",
        "푸시 하고 머지",
    ])
    def test_push_and_merge_has_approval_suffix(self, prompt: str):
        ctx = _get_context(prompt)
        assert is_fast_path(ctx), (
            f"Expected FAST-PATH directive for {prompt!r}, got: {ctx!r}"
        )
        assert has_approval_suffix(ctx), (
            f"push+merge intent {prompt!r} MUST include approval suffix, got: {ctx!r}"
        )


# ===========================================================================
# Regression: exact phrase from issue #25
# ===========================================================================

class TestIssue25RegressionCases:
    """Exact reproduction steps from issue #25 must behave correctly."""

    def test_git_status_no_approval(self):
        """Exact phrase from issue #25 reproduction step 1."""
        ctx = _get_context("git status")
        assert is_fast_path(ctx), "git status must produce FAST-PATH directive"
        assert not has_approval_suffix(ctx), (
            "git status (read-only) must NOT ask for approval gate — issue #25"
        )

    def test_korean_status_no_approval(self):
        """Korean status phrase from issue #25 reproduction."""
        ctx = _get_context("상태 확인")
        assert is_fast_path(ctx), "상태 확인 must produce FAST-PATH directive"
        assert not has_approval_suffix(ctx), (
            "상태 확인 (read-only) must NOT ask for approval gate — issue #25"
        )

    def test_fast_path_directive_format_status(self):
        """FAST-PATH directive for status must end cleanly without trailing suffix."""
        ctx = _get_context("git status")
        assert ctx is not None
        # The directive should end with the command template and a period,
        # not with "Show approval gate first."
        assert ctx.rstrip().endswith("git status."), (
            f"Directive for 'git status' should end with 'git status.' but got: {ctx!r}"
        )

    def test_issue_status_transition_does_not_use_git_status_fast_path(self):
        """Issue lifecycle commands that mention status must route to issuer."""
        ctx = _get_context("set ENRTC-273 status to Done")
        assert ctx is not None
        assert "[agent-crew] FAST-PATH" not in ctx, (
            f"Issue status transition must not be treated as git status: {ctx!r}"
        )
        assert "issue lifecycle" in ctx
        assert 'crew:run "issuer task"' in ctx

    def test_korean_issue_status_transition_does_not_use_git_status_fast_path(self):
        """Korean issue status changes must not be treated as git status."""
        ctx = _get_context("ENRTC-273 상태 변경")
        assert ctx is not None
        assert "[agent-crew] FAST-PATH" not in ctx, (
            f"Korean issue status transition must not be treated as git status: {ctx!r}"
        )
        assert "issue lifecycle" in ctx
        assert 'crew:run "issuer task"' in ctx
