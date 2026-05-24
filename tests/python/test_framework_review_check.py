"""Tests for framework operational readiness review checks."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRAMEWORK_REVIEW = REPO_ROOT / "core" / "scripts" / "framework-review-check.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


framework_review = _load_module(FRAMEWORK_REVIEW, "framework_review_check")


def test_framework_review_passes_current_repository():
    result = subprocess.run(
        ["python3", str(FRAMEWORK_REVIEW), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["controls"] >= 28


def test_framework_review_covers_operational_categories():
    payload = framework_review.evaluate_repo(REPO_ROOT)
    categories = set(payload["summary"]["categories"])
    controls = {item["name"] for item in payload["controls"]}

    assert {
        "architecture",
        "performance",
        "quality",
        "reliability",
        "memory_governance",
        "security",
        "observability",
        "cost_efficiency",
        "developer_experience",
        "long_term_scalability",
    }.issubset(categories)
    assert {
        "automatic_issue_reporting_surface",
        "automatic_issue_reporting_governance",
        "automatic_issue_reporting_regression_tests",
        "runtime_governance_contract",
        "context_compression_pageout",
        "structured_output_traceability",
        "tool_sandboxing_contract",
        "retrieval_scoring_contract",
        "explicit_state_transition_replay_contract",
        "prompt_injection_runtime_boundary",
        "automatic_issue_reporting_runtime_issue_contract",
        "claude_performance_budget_probe",
    }.issubset(controls)


def test_framework_review_round_10_priorities_are_enforced():
    payload = framework_review.evaluate_repo(REPO_ROOT)
    controls = {item["name"]: item for item in payload["controls"]}
    required = [
        "runtime_governance_contract",
        "tool_sandboxing_contract",
        "context_compression_pageout",
        "structured_output_traceability",
        "explicit_state_transition_replay_contract",
        "retrieval_scoring_contract",
        "deterministic_workflow_replay",
        "telemetry_and_trace",
        "cost_aware_role_tiers",
        "prompt_injection_runtime_boundary",
        "automatic_issue_reporting_runtime_issue_contract",
    ]

    missing = [name for name in required if name not in controls]
    failed = [name for name in required if name in controls and not controls[name]["passed"]]

    assert missing == []
    assert failed == []


def test_framework_review_fails_when_security_policy_missing(tmp_path: Path):
    (tmp_path / "core" / "hooks").mkdir(parents=True)
    (tmp_path / "core" / "hooks" / "guard-dangerous-commands.sh").write_text(
        "DANGEROUS_PATTERNS = []\n",
        encoding="utf-8",
    )

    payload = framework_review.evaluate_repo(tmp_path)
    failed_names = {failure["name"] for failure in payload["failures"]}

    assert payload["passed"] is False
    assert "forbidden_tool_policy" in failed_names


def test_framework_review_fails_when_agent_capability_manifest_missing(tmp_path: Path):
    payload = framework_review.evaluate_repo(tmp_path)
    failed_names = {failure["name"] for failure in payload["failures"]}

    assert payload["passed"] is False
    assert "agent_capability_manifest" in failed_names
