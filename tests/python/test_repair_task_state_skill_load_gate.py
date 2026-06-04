"""Tests for skill-load evidence on manual Codex fallback repair."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"


def _write_task(
    state_dir: Path,
    task_id: str = "20260604-000000-0",
    task: str = "Implement a small TDD change",
    selected_skill: str = "tdd",
) -> Path:
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "context").mkdir()
    (task_dir / "register.json").write_text(
        json.dumps(
            {
                "task": task,
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
        f"selected_skill: {selected_skill}\n"
        "selection_reason: implementation task\n"
        "execution_mode: current_session_required fallback\n",
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
            "unit test bypasses quality-loop evidence to isolate skill-load gate",
            *extra,
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def test_mutating_current_session_repair_blocks_without_skill_load_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    _write_task(state_dir, task_id)

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_skill_load_evidence" in result.stderr
    assert "context/skill-load.md" in result.stderr


def test_tdd_specialist_requires_loaded_tdd_skill_path(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- core/rules/code-quality.md\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_required_skill_load_evidence" in result.stderr
    assert "tdd.md" in result.stderr


def test_repair_accepts_skill_load_evidence_for_tdd_specialist(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- ~/.agent-crew/system/agents/skills/tdd.md\n"
        "- core/rules/code-quality.md\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-use.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "core/rules/code-quality.md",
                        "applied_rules": ["KISS", "YAGNI", "DRY"],
                        "evidence_refs": ["tests/python/test_repair_task_state_skill_load_gate.py"],
                        "output_files": ["tests/python/test_repair_task_state_skill_load_gate.py"],
                        "verification": ["python3 -m pytest tests/python/test_repair_task_state_skill_load_gate.py -q"],
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
    assert repair["skill_load_gate"]["passed"] is True
    assert repair["skill_load_gate"]["matched_paths"] == ["context/skill-load.md"]
    assert repair["skill_load_gate"]["required_skills"] == ["tdd.md"]
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "SKILL_LOAD: passed" in result_text
    assert "SKILL_LOAD_EVIDENCE: context/skill-load.md" in result_text
    assert "REQUIRED_SKILL: tdd.md" in result_text


def test_general_evidence_does_not_satisfy_skill_load_gate(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Implement a small backend change",
        selected_skill="backend-python",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED\nApplied rule: reviewer checklist complete.\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id, "--evidence", "context/review.md")

    assert result.returncode != 0
    assert "BLOCKER: missing_skill_load_evidence" in result.stderr


def test_skill_load_bypass_is_explicitly_recorded(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)

    result = _repair(
        state_dir,
        task_id,
        "--skill-load-bypass-reason",
        "legacy manual repair predates skill-load artifacts",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["skill_load_gate"]["bypassed"] is True
    assert repair["skill_load_gate"]["bypass_reason"] == "legacy manual repair predates skill-load artifacts"
    assert "SKILL_LOAD: bypassed" in (task_dir / "result.md").read_text(encoding="utf-8")
