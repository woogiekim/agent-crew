"""Behavioral contracts for optional Brainstorm state artifacts."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / "core" / "scripts" / "validate-state-schema.py"
REGISTER_SCHEMA = REPO_ROOT / "core" / "schemas" / "register.schema.json"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("brainstorm_state_validator", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_register(current_phase: str = "phase_0") -> dict:
    return {
        "schema_version": 1,
        "task_id": "20260920-120000-0",
        "session_id": "20260920-120000",
        "task": "Define a durable Brainstorm state contract",
        "branch": "feat/brainstorm-state",
        "project_root": "/tmp/project",
        "task_dir": "/tmp/state/tasks/20260920-120000-0",
        "execution_mode": "single",
        "current_phase": current_phase,
        "approval_status": "not_required",
        "verification_status": "not_started",
    }


def classification_fixture(preliminary: str = "Bounded") -> dict:
    return {
        "schema_version": 1,
        "task_id": "20260920-120000-0",
        "raw_input_hash": "a" * 64,
        "preliminary": preliminary,
        "classifier_version": 1,
        "status": "preliminary",
    }


def dialogue_fixture() -> dict:
    return {
        "schema_version": 1,
        "task_id": "20260920-120000-0",
        "classification": "Architectural",
        "status": "not_started",
        "questions": [
            {
                "question_id": "q-1",
                "header": "Scope",
                "prompt": "Which boundary should the design preserve?",
                "options": [
                    {
                        "option_id": "preserve",
                        "label": "Preserve boundary",
                        "description": "Keep the current ownership boundary.",
                    },
                    {
                        "option_id": "change",
                        "label": "Change boundary",
                        "description": "Move ownership into a new component.",
                    },
                ],
                "why_it_matters": "The ownership decision affects the approval boundary.",
                "status": "pending",
            }
        ],
        "section_acknowledgements": [],
    }


def approval_fixture(status: str = "pending") -> dict:
    decision = {
        "decision_id": "decision-1",
        "approval_kind": "architectural_design",
        "status": status,
        "design_hash": "b" * 64,
        "bound_fields": {
            "classification": "Architectural",
            "goals": ["Keep approval deterministic"],
        },
        "created_at": "2026-09-20T12:00:00Z",
    }
    if status != "pending":
        decision["decision_at"] = "2026-09-20T12:01:00Z"
    return {
        "schema_version": 1,
        "task_id": "20260920-120000-0",
        "decisions": [decision],
    }


def make_valid_task(tmp_path: Path) -> Path:
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260920-120000-0"
    (task_dir / "context").mkdir(parents=True)
    (state_dir / "session.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": "20260920-120000",
                "status": "running",
                "tasks": [],
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "capabilities.json").write_text(
        json.dumps({"schema_version": 1, "host": "test"}), encoding="utf-8"
    )
    (task_dir / "register.json").write_text(
        json.dumps(valid_register()), encoding="utf-8"
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps({"schema_version": 1, "task": "test task", "stages": [], "completed_stages": 0}),
        encoding="utf-8",
    )
    (task_dir / "progress.buffer.jsonl").write_text("", encoding="utf-8")
    return task_dir


def run_validator(task_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENT_CREW_HOME"] = str(task_dir / "isolated-home")
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--state-dir",
            str(task_dir.parent.parent),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        env=env,
    )


def write_artifact(task_dir: Path, name: str, payload: dict) -> None:
    (task_dir / "context" / name).write_text(json.dumps(payload), encoding="utf-8")


def validate_register(register: dict) -> list[dict]:
    module = _load_validator_module()
    findings = module.Findings()
    schema = json.loads(REGISTER_SCHEMA.read_text(encoding="utf-8"))
    module.validate(register, schema, findings, REGISTER_SCHEMA)
    return findings.errors


def test_brainstorm_optional_artifacts_validate_when_present(tmp_path: Path) -> None:
    task_dir = make_valid_task(tmp_path)
    write_artifact(
        task_dir,
        "brainstorm-classification.json",
        classification_fixture(preliminary="Architectural"),
    )
    dialogue = dialogue_fixture()
    dialogue["status"] = "waiting_for_input"
    dialogue["active_question_id"] = "q-1"
    write_artifact(task_dir, "brainstorm-dialogue.json", dialogue)
    write_artifact(task_dir, "brainstorm-approval.json", approval_fixture(status="approved"))

    result = run_validator(task_dir)

    assert result.returncode == 0, result.stdout + result.stderr


def test_dialogue_rejects_plural_active_question_field(tmp_path: Path) -> None:
    task_dir = make_valid_task(tmp_path)
    dialogue = dialogue_fixture()
    dialogue["active_question_ids"] = ["q-1", "q-2"]
    write_artifact(task_dir, "brainstorm-dialogue.json", dialogue)

    result = run_validator(task_dir)

    assert result.returncode == 2
    assert "active_question_ids" in result.stdout


def test_approval_requires_decision_at_after_pending(tmp_path: Path) -> None:
    task_dir = make_valid_task(tmp_path)
    approval = approval_fixture(status="approved")
    del approval["decisions"][0]["decision_at"]
    write_artifact(task_dir, "brainstorm-approval.json", approval)

    result = run_validator(task_dir)

    assert result.returncode == 2


def test_register_accepts_brainstorm_phases_and_pointers() -> None:
    register = valid_register(current_phase="phase_1b_brainstorm")
    register.update(
        {
            "brainstorm_classification_path": "/tmp/task/context/brainstorm-classification.json",
            "brainstorm_dialogue_path": "/tmp/task/context/brainstorm-dialogue.json",
            "brainstorm_design_path": "/tmp/task/context/brainstorm-design.md",
            "brainstorm_approval_path": "/tmp/task/context/brainstorm-approval.json",
        }
    )

    assert validate_register(register) == []
    assert validate_register(valid_register(current_phase="phase_1c_plan")) == []
