"""Tests for reviewer response loop-back classification."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "reviewer-loop-decision.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decision = _load_module(SCRIPT, "reviewer_loop_decision")


def run_decision(text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--format", "json"],
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
