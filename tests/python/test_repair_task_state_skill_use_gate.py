"""Tests for advisory skill-use coverage on manual Codex fallback repair."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"


def _write_task(state_dir: Path, task_id: str = "20260604-000000-0") -> Path:
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "context").mkdir()
    (task_dir / "register.json").write_text(
        json.dumps(
            {
                "task": "Implement a small TDD change",
                "current_phase": "handoff_ready",
                "host_bridge_status": "current_session_required",
                "blocked_by": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps({"stages": ["supervisor"], "completed_stages": 0}) + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "selected_agent: backend\n"
        "selected_skill: tdd\n"
        "selection_reason: implementation task\n"
        "execution_mode: current_session_required fallback\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- ~/.agent-crew/system/agents/skills/tdd.md\n"
        "- core/rules/code-quality.md\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: refactor complete; post-refactor pytest passed.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: handoff_ready\n", encoding="utf-8")
    return task_dir


def _repair(state_dir: Path, task_id: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--status",
            "completed",
            "--quality-bypass-reason",
            "unit test bypasses pipeline quality-loop events to isolate skill-use gate",
            *extra,
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def _write_skill_plan(task_dir: Path) -> None:
    (task_dir / "context" / "skill-plan.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "core/rules/code-quality.md",
                        "rules": [
                            {
                                "rule_id": "KISS",
                                "task_interpretation": "Keep repair-state gate coverage focused.",
                                "planned_application": "Add only evidence fields needed by this repair path.",
                            }
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_mutating_current_session_repair_reports_missing_skill_use_as_advisory(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["skill_use_gate"]["advisory"] is True
    assert repair["skill_use_gate"]["passed"] is False
    assert repair["skill_use_gate"]["missing_skills"] == ["code-quality.md"]
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "SKILL_USE: advisory" in result_text
    assert "MISSING_SKILL_USE: code-quality.md" in result_text


def test_non_tdd_skill_use_incomplete_fields_are_advisory(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "skill-use.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "core/rules/code-quality.md",
                        "applied_rules": ["KISS"],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["skill_use_gate"]["advisory"] is True
    assert repair["skill_use_gate"]["incomplete_skills"]["code-quality.md"] == [
        "evidence_refs",
        "output_files",
        "verification",
    ]
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "SKILL_USE: advisory" in result_text
    assert "INCOMPLETE_SKILL_USE: code-quality.md: evidence_refs, output_files, verification" in result_text


def test_skill_use_reports_every_loaded_non_tdd_skill_gap(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- ~/.agent-crew/system/agents/skills/tdd.md\n"
        "- core/rules/code-quality.md\n"
        "- ~/.agent-crew/system/agents/skills/code-review.md\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-use.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "core/rules/code-quality.md",
                        "applied_rules": ["KISS"],
                        "evidence_refs": ["core/scripts/repair-task-state.py"],
                        "output_files": ["core/scripts/repair-task-state.py"],
                        "verification": ["python3 -m pytest tests/python/test_repair_task_state_skill_use_gate.py -q"],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["skill_use_gate"]["advisory"] is True
    assert repair["skill_use_gate"]["missing_skills"] == ["code-review.md"]
    assert repair["skill_use_gate"]["complete_skills"] == ["code-quality.md"]
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "SKILL_USE: advisory" in result_text
    assert "MISSING_SKILL_USE: code-review.md" in result_text
    assert "USED_SKILL: code-quality.md" in result_text


def test_repair_accepts_skill_use_evidence_for_loaded_non_tdd_skill(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    _write_skill_plan(task_dir)
    (task_dir / "context" / "skill-use.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "core/rules/code-quality.md",
                        "applied_rules": ["KISS", "YAGNI", "DRY"],
                        "evidence_refs": [
                            "core/scripts/repair-task-state.py",
                            "tests/python/test_repair_task_state_skill_use_gate.py",
                        ],
                        "output_files": [
                            "core/scripts/repair-task-state.py",
                            "tests/python/test_repair_task_state_skill_use_gate.py",
                        ],
                        "verification": [
                            "python3 -m pytest tests/python/test_repair_task_state_skill_use_gate.py -q"
                        ],
                        "rule_evidence": [
                            {
                                "rule_id": "KISS",
                                "artifact_refs": ["core/scripts/repair-task-state.py"],
                                "diff_refs": ["core/scripts/repair-task-state.py"],
                                "verification": [
                                    "python3 -m pytest tests/python/test_repair_task_state_skill_use_gate.py -q"
                                ],
                                "adversarial_checks": ["verified no unrelated repair behavior changed"],
                                "reviewer_status": "approved",
                            }
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["skill_use_gate"]["passed"] is True
    assert repair["skill_use_gate"]["advisory"] is False
    assert repair["skill_use_gate"]["required_skills"] == ["code-quality.md"]
    assert repair["skill_use_gate"]["matched_paths"] == ["context/skill-use.json"]
    assert repair["skill_understanding_gate"]["passed"] is True
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "SKILL_USE: passed" in result_text
    assert "SKILL_USE_EVIDENCE: context/skill-use.json" in result_text
    assert "USED_SKILL: code-quality.md" in result_text
    assert "SKILL_UNDERSTANDING: passed" in result_text


def test_skill_use_bypass_is_explicitly_recorded(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)

    result = _repair(
        state_dir,
        task_id,
        "--skill-use-bypass-reason",
        "legacy manual repair predates skill-use artifacts",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["skill_use_gate"]["bypassed"] is True
    assert repair["skill_use_gate"]["bypass_reason"] == "legacy manual repair predates skill-use artifacts"
    assert "SKILL_USE: bypassed" in (task_dir / "result.md").read_text(encoding="utf-8")
