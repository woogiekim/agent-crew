"""Tests for runtime pipeline capability preflight validation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO_ROOT / "core" / "scripts" / "pipeline-capability-check.py"


def write_pipeline(tmp_path: Path, pipeline: dict) -> Path:
    path = tmp_path / "pipeline.json"
    path.write_text(json.dumps(pipeline), encoding="utf-8")
    return path


def run_checker(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(CHECKER), "--pipeline", str(path), "--format", "json", *extra],
        text=True,
        capture_output=True,
    )


def failure_codes(payload: dict) -> set[str]:
    return {failure["code"] for failure in payload["failures"]}


def test_pipeline_capability_check_accepts_core_tdd_review_devops_flow(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement and deploy a backend feature",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
                "devops",
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True


def test_pipeline_capability_check_blocks_delegating_agent_in_runtime_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement workflow",
            "stages": ["planner", "reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "delegating_agent_in_runtime_stage" in failure_codes(payload)


def test_pipeline_capability_check_blocks_reviewer_mixed_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement workflow",
            "stages": [["backend", "reviewer"]],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "reviewer_stage_must_be_solo" in failure_codes(payload)


def test_pipeline_capability_check_blocks_devops_without_followup_reviewer(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Deploy workflow",
            "stages": ["devops"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "devops_stage_requires_followup_reviewer" in failure_codes(payload)


def test_pipeline_capability_check_accepts_planned_dynamic_worker(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement specialized workflow",
            "stages": [
                {"agents": ["domain-worker"], "tdd_parallel": True},
                "reviewer",
            ],
            "needs_creation": [
                {
                    "name": "domain-worker",
                    "role": "worker",
                    "reason": "specialized bounded-context implementation",
                }
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["summary"]["custom_agents"] == 1


def test_pipeline_capability_check_blocks_unknown_agent_without_creation_plan(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement specialized workflow",
            "stages": [
                {"agents": ["mystery-worker"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "unknown_agent_without_policy_or_creation_plan" in failure_codes(payload)


def test_pipeline_capability_check_accepts_existing_custom_agent_dir(tmp_path: Path):
    custom_dir = tmp_path / "user-agents"
    custom_dir.mkdir()
    (custom_dir / "billing-worker.md").write_text("# Agent: billing-worker\n", encoding="utf-8")
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement billing workflow",
            "stages": [
                {"agents": ["billing-worker"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path, "--agent-dir", str(custom_dir))

    assert result.returncode == 0, result.stdout + result.stderr


def test_pipeline_capability_check_blocks_destructive_custom_agent_name(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement release workflow",
            "stages": [
                {"agents": ["release-worker"], "tdd_parallel": True},
                "reviewer",
            ],
            "needs_creation": [
                {
                    "name": "release-worker",
                    "role": "worker",
                    "reason": "release workflow automation",
                }
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "custom_agent_name_implies_destructive_authority" in failure_codes(payload)


def test_pipeline_capability_check_accepts_explicit_custom_devops_profile(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Release workflow",
            "stages": [
                "release-worker",
                "reviewer",
            ],
            "needs_creation": [
                {
                    "name": "release-worker",
                    "role": "devops",
                    "capability_profile": "custom-devops-approved",
                    "reason": "approval-gated release operations",
                }
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True


def test_pipeline_capability_check_blocks_unknown_custom_profile(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement specialized workflow",
            "stages": [
                {"agents": ["domain-worker"], "tdd_parallel": True},
                "reviewer",
            ],
            "needs_creation": [
                {
                    "name": "domain-worker",
                    "role": "worker",
                    "capability_profile": "unknown-profile",
                    "reason": "specialized implementation",
                }
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "unknown_custom_capability_profile" in failure_codes(payload)


def test_pipeline_capability_check_reads_custom_agent_frontmatter_profile(tmp_path: Path):
    custom_dir = tmp_path / "user-agents"
    custom_dir.mkdir()
    (custom_dir / "release-worker.md").write_text(
        "---\ncapability_profile: custom-devops-approved\n---\n# Agent: release-worker\n",
        encoding="utf-8",
    )
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Release workflow",
            "stages": ["release-worker"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path, "--agent-dir", str(custom_dir))

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "devops_stage_requires_followup_reviewer" in failure_codes(payload)


def test_pipeline_capability_check_reads_codex_toml_custom_agent_profile(tmp_path: Path):
    custom_dir = tmp_path / "codex-agents"
    custom_dir.mkdir()
    (custom_dir / "release-worker.toml").write_text(
        'name = "release-worker"\ncapability_profile = "custom-devops-approved"\n',
        encoding="utf-8",
    )
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Release workflow",
            "stages": ["release-worker", "reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path, "--agent-dir", str(custom_dir))

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
