"""Tests for core/scripts/check-plaintext-approval.py.

Exit code contract:
  0 — no violation (or payload not applicable)
  2 — forbidden phrase detected
  3 — invalid args
"""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "check-plaintext-approval.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


approval_check = _load_module(SCRIPT, "check_plaintext_approval")


class TestEnglishViolations:
    def test_modal_whitespace_variants_remain_violations(self):
        for text in (
            "Should    I merge now?",
            "Should\nI push now?",
            "Shall\tI deploy now?",
        ):
            assert approval_check.find_violation(text) is not None, text

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
    def test_large_agent_response_is_scanned_with_bounded_latency(self):
        text = "x" * 1_000_000

        started = time.perf_counter()
        result = approval_check.find_violation(text)
        elapsed = time.perf_counter() - started

        assert result is None
        assert elapsed < 0.5, f"large safe response took {elapsed:.3f}s"

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

    def test_non_dict_payload_exits_0(self, script_runner):
        r = script_runner("check-plaintext-approval.py", input_text=json.dumps(["not", "a", "dict"]))
        assert r.returncode == 0
        assert approval_check.extract_text(["not", "a", "dict"]) == ""

    def test_content_block_list_is_joined_before_scanning(self, script_runner):
        payload = json.dumps({
            "tool_name": "Agent",
            "tool_response": {
                "content": [
                    {"text": "Safe first block."},
                    {"content": "Should I push now?"},
                    "ignored raw block",
                ]
            },
        })

        r = script_runner("check-plaintext-approval.py", input_text=payload)

        assert r.returncode == 2
        assert "Should I push" in r.stderr

    def test_invalid_json_stdin_is_scanned_as_raw_text(self, script_runner):
        r = script_runner("check-plaintext-approval.py", input_text="May I deploy now?")

        assert r.returncode == 2
        assert "May I deploy" in r.stderr

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
