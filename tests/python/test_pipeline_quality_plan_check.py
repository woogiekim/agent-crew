"""Tests for planning-time TDD/reviewer quality-loop enforcement."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECKER = REPO_ROOT / "core" / "scripts" / "pipeline-quality-plan-check.py"


def write_pipeline(tmp_path: Path, pipeline: dict) -> Path:
    path = tmp_path / "pipeline.json"
    path.write_text(json.dumps(pipeline), encoding="utf-8")
    return path


def run_checker(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(CHECKER), "--pipeline", str(path), "--format", "json"],
        text=True,
        capture_output=True,
    )


def test_plan_checker_blocks_bare_implementation_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement production quality behavior",
            "stages": ["backend", "reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "implementation_stage_without_tdd_parallel" in payload["failures"]


def test_plan_checker_reports_missing_pipeline_path(tmp_path: Path):
    result = subprocess.run(
        ["python3", str(CHECKER), "--pipeline", str(tmp_path / "missing.json")],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "pipeline not found" in result.stderr


def test_plan_checker_text_output_lists_failures(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement production quality behavior",
            "stages": ["backend", "reviewer"],
            "completed_stages": 0,
        },
    )

    result = subprocess.run(
        ["python3", str(CHECKER), "--pipeline", str(path)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: pipeline quality plan" in result.stdout
    assert "- implementation_stage_without_tdd_parallel" in result.stdout


def test_plan_checker_blocks_mixed_bare_implementation_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a full-stack feature",
            "stages": [["designer", "backend"], ["frontend"], "reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "implementation_stage_without_tdd_parallel" in payload["failures"]


def test_plan_checker_blocks_multi_agent_tdd_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a full-stack feature",
            "stages": [
                {"agents": ["backend", "frontend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "implementation_stage_without_tdd_parallel" in payload["failures"]
    assert "multi_agent_implementation_stage_must_split_for_tdd" in payload["failures"]
    assert payload["implementation_stages"][0]["implementers"] == ["backend", "frontend"]


def test_plan_checker_accepts_split_tdd_implementation_stages(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a full-stack feature",
            "stages": [
                "designer",
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
                {"agents": ["frontend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["required"] is True


def test_plan_checker_accepts_qa_verify_between_implementation_and_reviewer(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a user-facing backend feature with QA validation",
            "stages": [
                {"agents": ["qa-owner"], "qa_mode": "plan"},
                {"agents": ["backend"], "tdd_parallel": True},
                {
                    "agents": ["qa-owner"],
                    "qa_mode": "verify",
                    "qa_loop_target": "previous_implementation",
                },
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["required"] is True
    assert payload["pipeline_shape"]["qa_verify_indexes"] == [2]
    assert payload["pipeline_shape"]["has_quality_gate_after_each_implementer"] is True


def test_plan_checker_blocks_qa_verify_without_following_reviewer(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a user-facing backend feature with QA validation",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                {
                    "agents": ["qa-owner"],
                    "qa_mode": "verify",
                    "qa_loop_target": "previous_implementation",
                },
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_pipeline_reviewer_after_qa_verify" in payload["failures"]
    assert payload["pipeline_shape"]["qa_verify_indexes_without_following_reviewer"] == [1]


def test_plan_checker_blocks_implementation_stage_without_immediate_reviewer(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement a full-stack feature",
            "stages": [
                "designer",
                {"agents": ["backend"], "tdd_parallel": True},
                {"agents": ["frontend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_pipeline_reviewer_after_each_implementer" in payload["failures"]
    assert payload["pipeline_shape"]["implementer_indexes_without_immediate_reviewer"] == [1]


def test_plan_checker_accepts_feature_deploy_after_code_review(tmp_path: Path):
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


def test_plan_checker_blocks_missing_reviewer_after_tdd_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Fix runtime quality loop",
            "stages": [{"agents": ["backend"], "tdd_parallel": True}],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_pipeline_reviewer_stage" in payload["failures"]
    assert "missing_pipeline_reviewer_after_implementer" in payload["failures"]


def test_plan_checker_blocks_code_task_without_implementation_stage(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Implement runtime quality pipeline behavior",
            "stages": ["reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["code_task"] is True
    assert "missing_pipeline_implementation_stage" in payload["failures"]


def test_plan_checker_ignores_design_only_pipeline(tmp_path: Path):
    path = write_pipeline(
        tmp_path,
        {
            "schema_version": 1,
            "task": "Create a UI design specification",
            "stages": ["designer", "reviewer"],
            "completed_stages": 0,
        },
    )

    result = run_checker(path)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["required"] is False
