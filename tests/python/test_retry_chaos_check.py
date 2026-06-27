"""Tests for deterministic retry chaos replay fixtures."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "retry-chaos-check.py"
FIXTURE = REPO_ROOT / "core" / "evaluations" / "retry-chaos.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


retry_chaos = _load_module(SCRIPT, "retry_chaos_check")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--format", "json", *args],
        text=True,
        capture_output=True,
    )


def test_retry_chaos_check_passes_current_fixture():
    result = _run()

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"] == {"cases": 8, "passed": 8, "failed": 0}
    contract_case = next(
        case for case in payload["cases"]
        if case["id"] == "reviewer_contract_invalid_retries_reviewer_only"
    )
    assert contract_case["observed"]["validation_retries"] == 0
    assert contract_case["observed"]["reviewer_contract_retries"] == 1
    exhausted_case = next(
        case for case in payload["cases"]
        if case["id"] == "reviewer_contract_loop_exhaustion_blocks"
    )
    assert exhausted_case["observed"]["blocked_by"] == ["review_contract_loop_exhausted"]


def test_retry_chaos_blocks_repeated_reviewer_contract_retries(tmp_path: Path):
    fixture = {
        "schema_version": 1,
        "budgets": {
            "max_crash_retries": 5,
            "max_validation_retries": 3,
            "max_reviewer_contract_retries": 2,
            "max_token_truncation_resumes": 1,
        },
        "cases": [
            {
                "id": "reviewer-contract-loop",
                "events": [
                    {
                        "kind": "reviewer_result",
                        "review_mode": "verify-prior-must-only",
                        "response": (
                            "REVIEW_MODE: verify-prior-must-only\n"
                            "REVIEW: NEEDS_CHANGES\n"
                            "ISSUES: 1\n"
                            "New findings in this review:\n"
                            "- [IMPORTANT] Missing thing in src/Wallet.kt:42\n"
                        ),
                    },
                    {
                        "kind": "reviewer_result",
                        "review_mode": "verify-prior-must-only",
                        "response": (
                            "REVIEW_MODE: verify-prior-must-only\n"
                            "REVIEW: NEEDS_CHANGES\n"
                            "ISSUES: 1\n"
                            "New findings in this review:\n"
                            "- [IMPORTANT] Missing thing in src/Wallet.kt:42\n"
                        ),
                    },
                    {
                        "kind": "reviewer_result",
                        "review_mode": "verify-prior-must-only",
                        "response": (
                            "REVIEW_MODE: verify-prior-must-only\n"
                            "REVIEW: NEEDS_CHANGES\n"
                            "ISSUES: 1\n"
                            "New findings in this review:\n"
                            "- [IMPORTANT] Missing thing in src/Wallet.kt:42\n"
                        ),
                    },
                ],
                "expected": {
                    "final_status": "blocked",
                    "blocked_by": ["review_contract_loop_exhausted"],
                    "invocations": 3,
                    "validation_retries": 0,
                    "reviewer_contract_retries": 3,
                    "retry_reasons": [
                        "review_contract_invalid",
                        "review_contract_invalid",
                        "review_contract_invalid",
                    ],
                },
            }
        ],
    }
    fixture_path = tmp_path / "retry-chaos.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--fixture",
            str(fixture_path),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["cases"][0]["observed"]["blocked_by"] == ["review_contract_loop_exhausted"]


def test_retry_chaos_check_detects_retry_budget_regression(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["cases"][1]["expected"]["final_status"] = "completed"
    path = tmp_path / "retry-chaos.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    first_failure = payload["failures"][0]
    assert first_failure["id"] == "crash_budget_exhaustion_blocks"
    assert any("final_status" in item for item in first_failure["failures"])


def test_retry_chaos_check_detects_token_resume_regression(tmp_path: Path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["budgets"]["max_token_truncation_resumes"] = 0
    path = tmp_path / "retry-chaos.json"
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    first_failure = payload["failures"][0]
    assert first_failure["id"] == "token_truncation_resume_then_success"
    assert any("token_resumes" in item for item in first_failure["failures"])


def test_retry_chaos_check_rejects_invalid_fixture(tmp_path: Path):
    path = tmp_path / "retry-chaos.json"
    path.write_text('{"schema_version": 1, "cases": []}\n', encoding="utf-8")

    result = _run("--fixture", str(path))

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error_type"] == "invalid_fixture"


def test_retry_chaos_helpers_cover_invalid_json_and_status_edges(tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert retry_chaos.load_json(invalid)[0] is None
    assert retry_chaos.evaluate(REPO_ROOT, invalid)["error_type"] == "invalid_fixture"

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert retry_chaos.load_json(array) == (None, "fixture root must be an object")

    assert retry_chaos.status_line("STATUS: plan_ready\n") == "plan_ready"
    assert retry_chaos.status_line("STATUS: BLOCKED\n") == "blocked"


def test_retry_chaos_simulation_covers_event_errors_and_terminal_statuses(monkeypatch):
    empty = retry_chaos.simulate_case({"id": "empty", "events": []}, {}, REPO_ROOT)
    assert empty["failures"] == ["events must be a non-empty array"]

    malformed = retry_chaos.simulate_case(
        {
            "id": "malformed",
            "events": [
                "bad-event",
                {"kind": "unknown"},
            ],
        },
        {},
        REPO_ROOT,
    )
    assert "event_not_object:0" in malformed["failures"]
    assert "unknown_event_kind:'unknown'" in malformed["failures"]

    monkeypatch.setattr(
        retry_chaos,
        "reviewer_decision",
        lambda _root, _response, _review_mode=None: (None, "reviewer_decision_failed:9:boom"),
    )
    failed_review = retry_chaos.simulate_case(
        {"id": "review-fail", "events": [{"kind": "reviewer_result", "response": "bad"}]},
        {},
        REPO_ROOT,
    )
    assert "reviewer_decision_failed:9:boom" in failed_review["failures"]
    assert failed_review["observed"]["blocked_by"] == ["reviewer_decision_failed"]

    monkeypatch.setattr(
        retry_chaos,
        "reviewer_decision",
        lambda _root, _response, _review_mode=None: (
            {"action": "retry", "reason": "tests_failed", "directive": "fix"},
            None,
        ),
    )
    retry_then_complete = retry_chaos.simulate_case(
        {
            "id": "retry",
            "events": [
                {"kind": "reviewer_result", "response": "REVIEW: NEEDS_CHANGES"},
                {"kind": "agent_result", "response": "STATUS: completed"},
            ],
            "expected": {
                "final_status": "completed",
                "blocked_by": [],
                "invocations": 2,
                "crash_failures": 0,
                "token_resumes": 0,
                "validation_retries": 1,
                "retry_reasons": ["tests_failed"],
            },
        },
        {"max_validation_retries": 2},
        REPO_ROOT,
    )
    assert retry_then_complete["passed"] is True
    assert retry_then_complete["observed"]["directives"] == ["fix"]

    monkeypatch.setattr(
        retry_chaos,
        "reviewer_decision",
        lambda _root, _response, _review_mode=None: ({"action": "observe"}, None),
    )
    plan_ready = retry_chaos.simulate_case(
        {
            "id": "plan",
            "events": [
                {"kind": "reviewer_result", "response": "noop"},
                {"kind": "agent_result", "response": "STATUS: plan_ready"},
            ],
            "expected": {
                "final_status": "plan_ready",
                "blocked_by": [],
                "invocations": 2,
                "crash_failures": 0,
                "token_resumes": 0,
                "validation_retries": 0,
                "retry_reasons": [],
            },
        },
        {},
        REPO_ROOT,
    )
    assert plan_ready["passed"] is True

    blocked = retry_chaos.simulate_case(
        {
            "id": "blocked",
            "events": [{"kind": "agent_result", "response": "STATUS: BLOCKED"}],
            "expected": {
                "final_status": "blocked",
                "blocked_by": ["agent_blocked"],
                "invocations": 1,
                "crash_failures": 0,
                "token_resumes": 0,
                "validation_retries": 0,
                "retry_reasons": [],
            },
        },
        {},
        REPO_ROOT,
    )
    assert blocked["passed"] is True


def test_retry_chaos_reviewer_decision_covers_parse_and_returncode_errors(monkeypatch):
    class Proc:
        def __init__(self, stdout: str, stderr: str, returncode: int):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    monkeypatch.setattr(
        retry_chaos.subprocess,
        "run",
        lambda *_args, **_kwargs: Proc("not json", "", 0),
    )
    payload, error = retry_chaos.reviewer_decision(REPO_ROOT, "response")
    assert payload is None
    assert error and error.startswith("reviewer_decision_parse_failed:")

    monkeypatch.setattr(
        retry_chaos.subprocess,
        "run",
        lambda *_args, **_kwargs: Proc("{}", "boom", 2),
    )
    payload, error = retry_chaos.reviewer_decision(REPO_ROOT, "response")
    assert payload is None
    assert error == "reviewer_decision_failed:2:boom"


def test_retry_chaos_reviewer_retry_and_unknown_actions_continue(monkeypatch):
    retry_decisions = iter([
        ({"action": "retry", "reason": "tests_failed"}, None),
        ({"action": "approve"}, None),
    ])
    monkeypatch.setattr(
        retry_chaos,
        "reviewer_decision",
        lambda _root, _response, _review_mode=None: next(retry_decisions),
    )
    retry_result = retry_chaos.simulate_case(
        {
            "id": "retry-continue",
            "events": [
                {"kind": "reviewer_result", "response": "retry"},
                {"kind": "reviewer_result", "response": "approve"},
            ],
            "expected": {
                "final_status": "completed",
                "blocked_by": [],
                "invocations": 2,
                "crash_failures": 0,
                "token_resumes": 0,
                "validation_retries": 1,
                "retry_reasons": ["tests_failed"],
            },
        },
        {"max_validation_retries": 2},
        REPO_ROOT,
    )
    assert retry_result["passed"] is True

    observe_decisions = iter([
        ({"action": "observe"}, None),
        ({"action": "approve"}, None),
    ])
    monkeypatch.setattr(
        retry_chaos,
        "reviewer_decision",
        lambda _root, _response, _review_mode=None: next(observe_decisions),
    )
    observe_result = retry_chaos.simulate_case(
        {
            "id": "observe-continue",
            "events": [
                {"kind": "reviewer_result", "response": "observe"},
                {"kind": "reviewer_result", "response": "approve"},
            ],
            "expected": {
                "final_status": "completed",
                "blocked_by": [],
                "invocations": 2,
                "crash_failures": 0,
                "token_resumes": 0,
                "validation_retries": 0,
                "retry_reasons": [],
            },
        },
        {},
        REPO_ROOT,
    )
    assert observe_result["passed"] is True


def test_retry_chaos_rejects_non_object_cases_and_text_output(tmp_path: Path):
    fixture = tmp_path / "retry-chaos.json"
    fixture.write_text(
        json.dumps({"schema_version": 1, "budgets": {}, "cases": ["bad-case"]}),
        encoding="utf-8",
    )

    payload = retry_chaos.evaluate(REPO_ROOT, fixture)

    assert payload["error_type"] == "invalid_fixture"
    assert payload["failures"] == ["fixture cases must be objects"]

    result = subprocess.run(
        ["python3", str(SCRIPT), "--fixture", str(fixture)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "FAIL: retry chaos check" in result.stdout
    assert "cases=0 passed=0 failed=1" in result.stdout
