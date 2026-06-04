"""Tests for specialist-dispatch evidence on manual Codex fallback repair."""

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
                "task": "Implement a small change",
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
            "unit test bypasses quality-loop evidence to isolate specialist dispatch gate",
            *extra,
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def test_repair_blocks_mutating_current_session_without_specialist_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    _write_task(state_dir, task_id)

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_specialist_dispatch_evidence" in result.stderr
    assert "specialist agent and agent-skill selection" in result.stderr


def test_repair_accepts_specialist_dispatch_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "\n".join(
            [
                "selected_agent: frontend",
                "selected_skill: frontend-typescript-react",
                "selection_reason: UI implementation task",
                "execution_mode: current_session_required fallback",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- ~/.agent-crew/user/skills/frontend-typescript-react.md\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-plan.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "~/.agent-crew/user/skills/frontend-typescript-react.md",
                        "rules": [
                            {
                                "rule_id": "component-contract",
                                "task_interpretation": "Preserve the UI specialist contract in repair evidence.",
                                "planned_application": "Record frontend skill understanding for the pass fixture.",
                            }
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "skill-use.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "~/.agent-crew/user/skills/frontend-typescript-react.md",
                        "applied_rules": ["component contract applied"],
                        "evidence_refs": ["tests/python/test_repair_task_state_specialist_gate.py"],
                        "output_files": ["tests/python/test_repair_task_state_specialist_gate.py"],
                        "verification": ["python3 -m pytest tests/python/test_repair_task_state_specialist_gate.py -q"],
                        "rule_evidence": [
                            {
                                "rule_id": "component-contract",
                                "artifact_refs": ["tests/python/test_repair_task_state_specialist_gate.py"],
                                "diff_refs": ["tests/python/test_repair_task_state_specialist_gate.py"],
                                "verification": [
                                    "python3 -m pytest tests/python/test_repair_task_state_specialist_gate.py -q"
                                ],
                                "adversarial_checks": ["confirmed dispatch evidence still drives specialist gate"],
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

    assert result.returncode == 0
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["specialist_dispatch_gate"]["passed"] is True
    assert repair["specialist_dispatch_gate"]["matched_paths"] == ["context/specialist-dispatch.md"]
    assert repair["skill_load_gate"]["passed"] is True
