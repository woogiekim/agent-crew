"""Regression coverage for semantic completion artifact references."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "check-completion-artifact.py"
COMPLETION_RULE = REPO_ROOT / "core" / "rules" / "completion-report.md"
SUPERVISOR_RETRY = REPO_ROOT / "core" / "agents" / "supervisor-retry.md"
SUPERVISOR_BOOTSTRAP = REPO_ROOT / "core" / "agents" / "supervisor-bootstrap.md"
REQUIREMENTS_AGENT = REPO_ROOT / "core" / "agents" / "requirements.md"
REVIEWER_AGENT = REPO_ROOT / "core" / "agents" / "reviewer.md"
SCRIPTS_README = REPO_ROOT / "core" / "scripts" / "README.md"


def run_check(
    *, agent: str, task_dir: Path, response: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--agent",
            agent,
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        input=response,
        text=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    ("agent", "fields"),
    [
        ("analyst", ("HANDOFF", "PRD")),
        ("planner", ("HANDOFF", "PRD")),
        ("reviewer", ("REPORT",)),
    ],
)
def test_success_case_contract_accepts_task_local_semantic_artifacts(
    tmp_path: Path, agent: str, fields: tuple[str, ...]
) -> None:
    """success-case(contract) - accepts required task-local regular files."""
    # given
    context = tmp_path / "context"
    context.mkdir()
    paths = {
        "HANDOFF": tmp_path / "handoff.md",
        "PRD": context / "prd.md",
        "REPORT": context / "review.md",
    }
    for path in paths.values():
        path.write_text("semantic content\n", encoding="utf-8")
    response = "\n".join(f"{field}: {paths[field]}" for field in fields)

    # when
    result = run_check(agent=agent, task_dir=tmp_path, response=response)

    # then
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "accept"
    assert payload["reason"] == ""


@pytest.mark.parametrize("agent", ["analyst", "planner", "reviewer"])
def test_failure_case_contract_rejects_summary_only_semantic_completion(
    tmp_path: Path, agent: str
) -> None:
    """failure-case(contract) - rejects lossy summary-only completion."""
    # given
    response = "SUMMARY: Implement the feature and verify it.\nMETRICS: 7\n"

    # when
    result = run_check(agent=agent, task_dir=tmp_path, response=response)

    # then
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry_validation"
    assert payload["reason"] == "completion_artifact_missing"


@pytest.mark.parametrize(
    ("artifact_factory", "expected_reason"),
    [
        (lambda task_dir: task_dir / "missing.md", "completion_artifact_missing"),
        (lambda task_dir: task_dir / "context", "completion_artifact_not_file"),
        (
            lambda task_dir: task_dir.parent / "outside.md",
            "completion_artifact_outside_task",
        ),
    ],
)
def test_failure_case_validation_rejects_invalid_artifact_targets(
    tmp_path: Path, artifact_factory, expected_reason: str
) -> None:
    """failure-case(validation) - rejects missing, directory, and outside targets."""
    # given
    context = tmp_path / "context"
    context.mkdir()
    target = artifact_factory(tmp_path)
    if expected_reason == "completion_artifact_outside_task":
        target.write_text("outside\n", encoding="utf-8")
    response = f"REPORT: {target}\n"

    # when
    result = run_check(agent="reviewer", task_dir=tmp_path, response=response)

    # then
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry_validation"
    assert payload["reason"] == expected_reason


def test_boundary_case_security_rejects_symlink_escape(tmp_path: Path) -> None:
    """boundary-case(security) - rejects task-local symlinks escaping the task."""
    # given
    outside = tmp_path.parent / "outside-review.md"
    outside.write_text("outside\n", encoding="utf-8")
    linked = tmp_path / "review.md"
    linked.symlink_to(outside)

    # when
    result = run_check(
        agent="reviewer", task_dir=tmp_path, response=f"REPORT: {linked}\n"
    )

    # then
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "completion_artifact_outside_task"


def test_boundary_case_validation_rejects_symlink_loop_without_crashing(
    tmp_path: Path,
) -> None:
    """boundary-case(validation) - converts path resolution failures to retry."""
    # given
    linked = tmp_path / "review.md"
    linked.symlink_to(linked)

    # when
    result = run_check(
        agent="reviewer", task_dir=tmp_path, response=f"REPORT: {linked}\n"
    )

    # then
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry_validation"
    assert payload["reason"] == "completion_artifact_unreadable"


def test_boundary_case_validation_rejects_unknown_tilde_user_without_crashing(
    tmp_path: Path,
) -> None:
    """boundary-case(validation) - converts expanduser failures to retry."""
    # given
    response = "REPORT: ~agent_crew_user_that_does_not_exist/review.md\n"

    # when
    result = run_check(agent="reviewer", task_dir=tmp_path, response=response)

    # then
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["action"] == "retry_validation"
    assert payload["reason"] == "completion_artifact_unreadable"


@pytest.mark.parametrize("content", ["", "   \n\t"])
def test_failure_case_contract_rejects_empty_semantic_artifact(
    tmp_path: Path, content: str
) -> None:
    """failure-case(contract) - rejects artifacts without semantic content."""
    # given
    report = tmp_path / "review.md"
    report.write_text(content, encoding="utf-8")

    # when
    result = run_check(
        agent="reviewer", task_dir=tmp_path, response=f"REPORT: {report}\n"
    )

    # then
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["reason"] == "completion_artifact_empty"


def test_success_case_validation_stops_after_first_non_whitespace_chunk(
    tmp_path: Path,
) -> None:
    """success-case(performance) - later bytes are not read after content is found."""
    # given
    report = tmp_path / "review.md"
    report.write_bytes(b"review\n" + (b" " * 8192) + b"\xff")

    # when
    result = run_check(
        agent="reviewer", task_dir=tmp_path, response=f"REPORT: {report}\n"
    )

    # then
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "accept"


@pytest.mark.parametrize("agent", ["backend", "frontend", "test-writer"])
def test_success_case_regression_preserves_implementer_completion_formats(
    tmp_path: Path, agent: str
) -> None:
    """success-case(regression) - leaves implementer return blocks unchanged."""
    # given
    response = (
        "STATUS: completed\n"
        "FILES: src/example.py tests/test_example.py\n"
        "VERIFIED: tests=2/2 cmd=pytest exit=0\n"
    )

    # when
    result = run_check(agent=agent, task_dir=tmp_path, response=response)

    # then
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "not_applicable"


def test_success_case_contract_documents_path_only_semantic_completion() -> None:
    """success-case(contract) - semantic summaries cannot replace artifacts."""
    # given
    text = COMPLETION_RULE.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    # when
    semantic_contract = "A one-line summary cannot replace this"

    # then
    assert semantic_contract in text
    assert "artifact path." in text
    assert "task-local regular file" in normalized


def test_success_case_contract_preserves_inline_requirements_return() -> None:
    """success-case(contract) - requirements keep their dedicated inline shape."""
    # given
    completion_rule = COMPLETION_RULE.read_text(encoding="utf-8")
    requirements_contract = REQUIREMENTS_AGENT.read_text(encoding="utf-8")

    # when
    semantic_scope = "analysis, judgment, review, or planning output"

    # then
    assert semantic_scope in completion_rule
    assert "review, requirements, or planning output" not in completion_rule
    assert "Return the REQUIREMENTS block inline" in requirements_contract


def test_success_case_regression_removes_dead_generic_semantic_retry() -> None:
    """success-case(regression) - actual lifecycle owners handle semantic retry."""
    # given
    text = SUPERVISOR_RETRY.read_text(encoding="utf-8")

    # when
    dead_counter = "validation_attempts"

    # then
    assert dead_counter not in text


def test_success_case_contract_handles_blocked_analyst_before_artifact_validation() -> None:
    """success-case(contract) - blocked readiness preserves its real blocker."""
    # given
    text = SUPERVISOR_BOOTSTRAP.read_text(encoding="utf-8")

    # when
    delegate_index = text.index("Delegate to the **analyst agent**")
    extract_index = text.index("Extract the `ANALYSIS` block", delegate_index)
    blocked_index = text.index("readiness: BLOCKED", extract_index)
    binding_index = text.index(
        "Bind the exact returned text to `ANALYST_RESPONSE`", delegate_index
    )
    validator_index = text.index("check-completion-artifact.py", delegate_index)
    pipeline_index = text.index("After completion, read only `pipeline.json`")

    # then
    assert delegate_index < binding_index < extract_index
    assert extract_index < blocked_index < validator_index < pipeline_index
    assert "Validate only a `readiness: READY` response" in text
    assert '--agent "analyst"' in text[validator_index:pipeline_index]
    assert "completion_artifact_validation_exhausted" in text


def test_success_case_documentation_describes_minimal_content_inspection() -> None:
    """success-case(documentation) - docs match empty-artifact validation."""
    # given
    readme = SCRIPTS_README.read_text(encoding="utf-8")
    helper = SCRIPT.read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.split())
    normalized_helper = " ".join(helper.split())

    # then
    assert "reads no artifact content" not in readme
    assert "without reading or duplicating artifact content" not in helper
    assert "empty or whitespace-only" in normalized_readme
    assert "empty or whitespace-only" in normalized_helper


def test_success_case_reviewer_persists_early_rejection_report_before_return() -> None:
    """success-case(contract) - early rejections remain implementer directives."""
    # given
    reviewer = REVIEWER_AGENT.read_text(encoding="utf-8")

    # when
    contract_index = reviewer.index("Early-Rejection Report Contract")
    contract_end = reviewer.index("### Phase 1.6 —", contract_index)
    first_early_report = reviewer.index(
        "REPORT: ${TASK_DIR}/context/review.md", contract_end
    )

    # then
    assert contract_index < contract_end < first_early_report
    contract = " ".join(reviewer[contract_index:contract_end].split())
    assert "must write `${TASK_DIR}/context/review.md` before returning" in contract
    assert "REASON" in contract
