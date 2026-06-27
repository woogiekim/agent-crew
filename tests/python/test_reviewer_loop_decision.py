"""Tests for reviewer response loop-back classification."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "reviewer-loop-decision.py"
SUPERVISOR_RETRY = REPO_ROOT / "core" / "agents" / "supervisor-retry.md"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision = _load_module(SCRIPT, "reviewer_loop_decision")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_decision(text: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--format", "json", *extra],
        input=text,
        text=True,
        capture_output=True,
    )


def run_decision_with_task_dir(text: str, task_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--format", "json", "--task-dir", str(task_dir)],
        input=text,
        text=True,
        capture_output=True,
    )


def test_status_rejected_triggers_retry_with_reason():
    result = run_decision(
        "STATUS: REJECTED\n"
        "REASON: tests_failed\n"
        "DETAIL: pytest failed\n"
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry"
    assert payload["reason"] == "tests_failed"
    assert "failing tests" in payload["directive"]


def test_review_needs_changes_triggers_retry():
    result = run_decision(
        "REVIEW: NEEDS_CHANGES\n"
        "REPORT: context/review.md\n"
        "ISSUES: 2\n"
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry"
    assert payload["trigger"] == "REVIEW: NEEDS_CHANGES"
    assert payload["reason"] == "review_needs_changes"
    assert payload["issues"] == 2
    assert "re-run reviewer" in payload["directive"]
    assert "REVIEW_MODE: verify-prior-must-only" in payload["directive"]
    assert "NEW_MUST_CLASSIFICATION" in payload["directive"]


def test_review_needs_changes_preserves_spec_incomplete_reason():
    result = run_decision(
        "REVIEW: NEEDS_CHANGES\n"
        "REASON: spec_incomplete\n"
        "REPORT: context/review.md\n"
        "ISSUES: 1\n"
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "spec_incomplete"
    assert "PRD acceptance criteria" in payload["directive"]


def test_review_needs_changes_preserves_code_quality_reason():
    result = run_decision(
        "REVIEW: NEEDS_CHANGES\n"
        "REASON: code_quality\n"
        "REPORT: context/review.md\n"
        "ISSUES: 1\n"
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "code_quality"
    assert "code-quality" in payload["directive"]


def test_supervisor_retry_classifier_invocation_passes_review_mode():
    text = read(SUPERVISOR_RETRY)

    assert "reviewer-loop-decision.py" in text
    assert "--review-mode" in text
    assert '"${REVIEW_MODE:-full-rescan}"' in text


def test_supervisor_retry_handles_reviewer_contract_retry_without_implementer_loopback():
    text = read(SUPERVISOR_RETRY)

    assert 'decision.retry_target == "reviewer"' in text
    assert "reviewer_contract_retries += 1" in text
    assert "review_contract_loop_exhausted" in text
    assert "continue  # re-run reviewer" in text


def test_verify_prior_must_mode_rejects_unclassified_new_must_as_reviewer_retry():
    result = run_decision(
        "REVIEW_MODE: verify-prior-must-only\n"
        "REVIEW: NEEDS_CHANGES\n"
        "REPORT: context/review.md\n"
        "ISSUES: 1\n"
        "New findings in this review:\n"
        "- [IMPORTANT] Missing balance validation in src/main/kotlin/Wallet.kt:42\n",
        "--review-mode",
        "verify-prior-must-only",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry"
    assert payload["reason"] == "review_contract_invalid"
    assert payload["retry_target"] == "reviewer"
    assert payload["review_mode"] == "verify-prior-must-only"
    assert "new_must_classification_missing" in payload["review_contract_violations"]
    assert "do not return to implementer" in payload["directive"]


def test_verify_prior_must_mode_rejects_generic_must_section_without_classification():
    result = run_decision(
        "REVIEW_MODE: verify-prior-must-only\n"
        "REVIEW: NEEDS_CHANGES\n"
        "REPORT: context/review.md\n"
        "ISSUES: 1\n"
        "\n"
        "### Must Fix\n"
        "- [IMPORTANT] Missing balance validation in src/main/kotlin/Wallet.kt:42\n",
        "--review-mode",
        "verify-prior-must-only",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "review_contract_invalid"
    assert payload["retry_target"] == "reviewer"
    assert payload["review_contract_valid"] is False
    assert "new_must_classification_missing" in payload["review_contract_violations"]
    assert payload["new_must_lines"] == [
        "- [IMPORTANT] Missing balance validation in src/main/kotlin/Wallet.kt:42"
    ]


def test_verify_prior_must_mode_allows_prior_must_verification_without_new_classification():
    result = run_decision(
        "REVIEW_MODE: verify-prior-must-only\n"
        "REVIEW: NEEDS_CHANGES\n"
        "REPORT: context/review.md\n"
        "ISSUES: 1\n"
        "\n"
        "## Existing unresolved findings\n"
        "- [IMPORTANT] Prior Must still failing in src/main/kotlin/Wallet.kt:42\n",
        "--review-mode",
        "verify-prior-must-only",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "review_needs_changes"
    assert payload["retry_target"] == "implementer"
    assert payload["review_contract_valid"] is True
    assert payload["new_must_lines"] == []


def test_verify_prior_must_mode_accepts_classified_new_must_with_first_party_evidence():
    result = run_decision(
        "REVIEW_MODE: verify-prior-must-only\n"
        "REVIEW: NEEDS_CHANGES\n"
        "REPORT: context/review.md\n"
        "ISSUES: 1\n"
        "New findings in this review:\n"
        "- [IMPORTANT] Missing reviewer evidence validation in core/scripts/reviewer-loop-decision.py:226\n"
        "NEW_MUST_CLASSIFICATION: missed_existing\n"
        "NEW_MUST_EVIDENCE: core/scripts/reviewer-loop-decision.py:226 and tests/python/test_reviewer_loop_decision.py:193\n",
        "--review-mode",
        "verify-prior-must-only",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "review_needs_changes"
    assert payload["retry_target"] == "implementer"
    assert payload["review_contract_valid"] is True
    assert payload["new_must_classification"] == "missed_existing"


def test_verify_prior_must_mode_ignores_missing_must_none_summary():
    result = run_decision(
        "REVIEW_MODE: verify-prior-must-only\n"
        "REVIEW: NEEDS_CHANGES\n"
        "REPORT: context/review.md\n"
        "ISSUES: 1\n"
        "## Test Case Checklist\n"
        "- Checklist: context/test-checklist.md\n"
        "- Missing MUST: none\n"
        "- Result: passed\n",
        "--review-mode",
        "verify-prior-must-only",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "review_needs_changes"
    assert payload["retry_target"] == "implementer"
    assert payload["review_contract_valid"] is True
    assert payload["new_must_lines"] == []


def test_verify_prior_must_mode_rejects_nonexistent_first_party_evidence_path():
    result = run_decision(
        "REVIEW_MODE: verify-prior-must-only\n"
        "REVIEW: NEEDS_CHANGES\n"
        "REPORT: context/review.md\n"
        "ISSUES: 1\n"
        "New findings in this review:\n"
        "- [IMPORTANT] Missing balance validation in src/main/kotlin/Wallet.kt:42\n"
        "NEW_MUST_CLASSIFICATION: missed_existing\n"
        "NEW_MUST_EVIDENCE: src/main/kotlin/Wallet.kt:42 and tests/WalletTest.kt:18\n",
        "--review-mode",
        "verify-prior-must-only",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "review_contract_invalid"
    assert payload["retry_target"] == "reviewer"
    assert payload["review_contract_valid"] is False
    assert "new_must_first_party_evidence_missing" in payload["review_contract_violations"]


def test_invalid_review_mode_falls_back_to_verify_prior_contract():
    result = run_decision(
        "REVIEW_MODE: typo-mode\n"
        "REVIEW: NEEDS_CHANGES\n"
        "ISSUES: 1\n"
        "New findings in this review:\n"
        "- [IMPORTANT] Missing reviewer evidence validation in core/scripts/reviewer-loop-decision.py:226\n",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["review_mode"] == "verify-prior-must-only"
    assert payload["reason"] == "review_contract_invalid"


def test_verify_prior_must_mode_does_not_reject_new_minor_items():
    result = run_decision(
        "REVIEW_MODE: verify-prior-must-only\n"
        "REVIEW: NEEDS_CHANGES\n"
        "REPORT: context/review.md\n"
        "ISSUES: 1\n"
        "New findings in this review:\n"
        "- [MINOR] Rename a helper for clarity in src/main/kotlin/Wallet.kt:42\n",
        "--review-mode",
        "verify-prior-must-only",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "review_needs_changes"
    assert payload["retry_target"] == "implementer"
    assert payload["review_contract_valid"] is True


def test_review_approved_does_not_retry():
    result = run_decision(
        "REVIEW: APPROVED\n"
        "REPORT: context/review.md\n"
        "ISSUES: 0\n"
        "QUALITY_METRICS: context/quality-metrics.json\n"
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "approve"
    assert payload["quality_metrics"] == "context/quality-metrics.json"


def test_review_approved_without_quality_metrics_retries_reviewer():
    result = run_decision(
        "REVIEW: APPROVED\n"
        "REPORT: context/review.md\n"
        "ISSUES: 0\n"
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry"
    assert payload["reason"] == "quality_metrics_missing"
    assert "QUALITY_METRICS" in payload["directive"]


def test_review_approved_missing_quality_metrics_file_retries(tmp_path: Path):
    result = run_decision_with_task_dir(
        "REVIEW: APPROVED\n"
        "REPORT: context/review.md\n"
        "ISSUES: 0\n"
        "QUALITY_METRICS: context/quality-metrics.json\n",
        tmp_path,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry"
    assert payload["reason"] == "quality_metrics_file_missing"


def test_review_approved_existing_quality_metrics_file_approves(tmp_path: Path):
    (tmp_path / "context").mkdir()
    (tmp_path / "context" / "quality-metrics.json").write_text("{}", encoding="utf-8")

    result = run_decision_with_task_dir(
        "REVIEW: APPROVED\n"
        "REPORT: context/review.md\n"
        "ISSUES: 0\n"
        "QUALITY_METRICS: context/quality-metrics.json\n",
        tmp_path,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["action"] == "approve"


def test_response_file_and_relative_quality_metrics_path_are_supported(tmp_path: Path):
    (tmp_path / "quality-metrics.json").write_text("{}", encoding="utf-8")
    response = tmp_path / "review.md"
    response.write_text(
        "REVIEW: APPROVED\n"
        "QUALITY_METRICS: quality-metrics.json\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--response",
            str(response),
            "--task-dir",
            str(tmp_path),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "approve"


def test_unreadable_response_file_exits_two(tmp_path: Path):
    result = subprocess.run(
        ["python3", str(SCRIPT), "--response", str(tmp_path / "missing.md")],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "cannot read response" in result.stderr


def test_text_output_prints_retry_directive():
    result = subprocess.run(
        ["python3", str(SCRIPT)],
        input="REVIEW: NEEDS_CHANGES\nISSUES: 1\n",
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "ACTION: retry" in result.stdout
    assert "REASON: review_needs_changes" in result.stdout
    assert "DIRECTIVE:" in result.stdout


def test_no_verdict_and_quality_metrics_path_resolution(tmp_path: Path):
    assert decision.classify("No structured verdict here.") == {
        "action": "none",
        "trigger": "",
        "reason": "no_review_verdict",
        "directive": "",
    }
    absolute = tmp_path / "quality-metrics.json"
    assert decision.resolve_quality_metrics_path(str(absolute), None) == absolute
    assert decision.resolve_quality_metrics_path("", str(tmp_path)) is None


def test_supervisor_docs_treat_needs_changes_as_loop_trigger():
    retry_doc = (REPO_ROOT / "core" / "agents" / "supervisor-retry.md").read_text(encoding="utf-8")
    quality_doc = (REPO_ROOT / "core" / "rules" / "quality-loop.md").read_text(encoding="utf-8")
    reviewer_doc = (REPO_ROOT / "core" / "agents" / "reviewer.md").read_text(encoding="utf-8")

    assert "REVIEW: NEEDS_CHANGES` return (a soft advisory" not in retry_doc
    assert "does\n-NOT trigger" not in retry_doc
    assert "`REVIEW: NEEDS_CHANGES`" in retry_doc
    assert "action=retry" in retry_doc
    assert "REVIEW: NEEDS_CHANGES` | Static or streaming review" in quality_doc
    assert "`REVIEW: NEEDS_CHANGES` is a loop-triggering rejection" in reviewer_doc


def test_reviewer_docs_define_re_review_modes_and_new_must_policy():
    reviewer_doc = (REPO_ROOT / "core" / "agents" / "reviewer.md").read_text(encoding="utf-8")
    skill_doc = (REPO_ROOT / "core" / "agents" / "skills" / "code-review.md").read_text(encoding="utf-8")
    retry_doc = (REPO_ROOT / "core" / "agents" / "supervisor-retry.md").read_text(encoding="utf-8")

    for text in (reviewer_doc, skill_doc, retry_doc):
        assert "verify-prior-must-only" in text
        assert "full-rescan" in text
        assert "regression" in text
        assert "missed_existing" in text
        assert "severity_escalation" in text
        assert "unclear_requirement" in text

    assert "Weakly evidenced" in skill_doc
    assert "NEW_MUST_CLASSIFICATION" in reviewer_doc
