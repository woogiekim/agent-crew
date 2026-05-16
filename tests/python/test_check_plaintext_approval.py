"""Tests for core/scripts/check-plaintext-approval.py.

Exit code contract:
  0 — no violation (or payload not applicable)
  2 — forbidden phrase detected
  3 — invalid args
"""
from __future__ import annotations

import json


class TestEnglishViolations:
    def test_shall_i_merge_is_violation(self, script_runner):
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "Shall I merge the PR now?",
        )
        assert r.returncode == 2, r.stderr
        assert "Shall I merge" in r.stderr or "Shall" in r.stderr

    def test_should_i_push_is_violation(self, script_runner):
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "Should I push the changes?",
        )
        assert r.returncode == 2, r.stderr

    def test_do_you_want_me_to_deploy_is_violation(self, script_runner):
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "Do you want me to deploy now?",
        )
        assert r.returncode == 2, r.stderr

    def test_would_you_like_me_to_is_violation(self, script_runner):
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "Would you like me to revert that commit?",
        )
        assert r.returncode == 2, r.stderr

    def test_may_i_proceed_is_violation(self, script_runner):
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "May I proceed with the merge?",
        )
        assert r.returncode == 2, r.stderr


class TestKoreanViolations:
    def test_jinhaeng_halkkayo_is_violation(self, script_runner):
        # "진행할까요?" — explicit Korean approval prompt
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "병합을 진행할까요?",
        )
        assert r.returncode == 2, (
            f"expected 2 for Korean 진행할까요, got {r.returncode}\n"
            f"stderr:\n{r.stderr}"
        )

    def test_haedrilkayo_is_violation(self, script_runner):
        # "해드릴까요?" — Korean polite offer-prompt
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "지금 배포 해드릴까요?",
        )
        assert r.returncode == 2, (
            f"expected 2 for Korean 해드릴까요, got {r.returncode}\n"
            f"stderr:\n{r.stderr}"
        )

    def test_haldo_doelkkayo_is_violation(self, script_runner):
        # "해도 될까요?" — Korean permission-seeking prompt
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "지금 머지 해도 될까요?",
        )
        assert r.returncode == 2, (
            f"expected 2 for Korean 해도 될까요, got {r.returncode}\n"
            f"stderr:\n{r.stderr}"
        )


class TestNonViolations:
    def test_can_i_help_you_is_not_violation(self, script_runner):
        """The 'Can I help' greeting-style pattern is explicitly excluded."""
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "Can I help you with anything else today?",
        )
        assert r.returncode == 0, (
            f"'Can I help' must be excluded; got {r.returncode}\n"
            f"stderr:\n{r.stderr}"
        )

    def test_plain_prose_no_modal_no_question_clean(self, script_runner):
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "The deployment completed successfully.",
        )
        assert r.returncode == 0

    def test_quoted_example_in_documentation_matches(self, script_runner):
        """Documented false-positive: prose quoting the forbidden phrase
        DOES trigger the regex (accepted per script's design)."""
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "The rule forbids 'Shall I merge?'-style prompts.",
        )
        # Per the docstring: "accepted false positive"
        assert r.returncode == 2

    def test_empty_text_exits_0(self, script_runner):
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "",
        )
        assert r.returncode == 0

    def test_question_without_modal_clean(self, script_runner):
        r = script_runner(
            "check-plaintext-approval.py",
            "--text", "What time is the meeting?",
        )
        assert r.returncode == 0


class TestStdinPayload:
    def test_non_agent_tool_call_silently_exits_0(self, script_runner):
        """When tool_name != Agent, the script exits 0 without scanning."""
        payload = json.dumps({
            "tool_name": "Bash",
            "tool_response": {"content": "Shall I merge?"},
        })
        r = script_runner("check-plaintext-approval.py", input_text=payload)
        assert r.returncode == 0, (
            f"non-Agent tool should be ignored, got {r.returncode}\n"
            f"stderr:\n{r.stderr}"
        )

    def test_agent_tool_call_with_violation_exits_2(self, script_runner):
        payload = json.dumps({
            "tool_name": "Agent",
            "tool_response": {"content": "Shall I merge the PR?"},
        })
        r = script_runner("check-plaintext-approval.py", input_text=payload)
        assert r.returncode == 2, (
            f"Agent payload with violation should exit 2, got {r.returncode}\n"
            f"stderr:\n{r.stderr}"
        )

    def test_empty_stdin_exits_0(self, script_runner):
        r = script_runner("check-plaintext-approval.py", input_text="")
        assert r.returncode == 0

    def test_unknown_payload_shape_exits_0(self, script_runner):
        payload = json.dumps({"tool_name": "Agent", "unknown_field": 42})
        r = script_runner("check-plaintext-approval.py", input_text=payload)
        assert r.returncode == 0

    def test_wildcard_tool_filter_matches_anything(self, script_runner):
        payload = json.dumps({
            "tool_name": "SomethingElse",
            "tool_response": "Shall I deploy?",
        })
        r = script_runner(
            "check-plaintext-approval.py", "--tool", "*",
            input_text=payload,
        )
        assert r.returncode == 2
