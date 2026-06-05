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


def test_repair_blocks_incomplete_specialist_dispatch_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "selected_skill: frontend-typescript-react\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--skill-load-bypass-reason",
        "isolate specialist dispatch shape",
    )

    assert result.returncode != 0
    assert "BLOCKER: incomplete_specialist_dispatch_evidence" in result.stderr
    assert "selected_agent" in result.stderr
    assert "selection_reason" in result.stderr
    assert "execution_mode" in result.stderr


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


def test_repair_preserves_user_agent_and_subagent_dispatch_axes(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "\n".join(
            [
                "selected_agent: backend",
                "selected_user_agent: kotlin-domain-specialist",
                "selected_subagents: test-writer, reviewer",
                "selected_skill: backend-kotlin-spring",
                "selection_reason: backend Kotlin implementation with custom domain reviewer",
                "execution_mode: current_session_required fallback",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--quality-bypass-reason",
        "isolate specialist dispatch axis serialization",
        "--skill-load-bypass-reason",
        "isolate specialist dispatch axis serialization",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["specialist_dispatch_gate"]
    assert gate["selected_agents"] == ["backend"]
    assert gate["selected_user_agents"] == ["kotlin-domain-specialist"]
    assert gate["selected_subagents"] == ["reviewer", "test-writer"]
    assert gate["selected_skills"] == ["backend-kotlin-spring"]
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "SPECIALIST_AGENT: backend" in result_text
    assert "SPECIALIST_USER_AGENT: kotlin-domain-specialist" in result_text
    assert "SPECIALIST_SUBAGENT: reviewer" in result_text
    assert "SPECIALIST_SUBAGENT: test-writer" in result_text
    assert "SPECIALIST_SKILL: backend-kotlin-spring" in result_text


def test_repair_accepts_json_specialist_dispatch_axes(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "specialist-dispatch.md").unlink(missing_ok=True)
    (task_dir / "context" / "specialist-dispatch.json").write_text(
        json.dumps(
            {
                "selected_agent": "backend",
                "selected_user_agent": ["domain-reviewer"],
                "selected_subagents": ["test-writer", "reviewer"],
                "selected_skills": ["backend-kotlin-spring"],
                "selection_reason": "backend change with custom review specialist",
                "execution_mode": "current_session_required fallback",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--quality-bypass-reason",
        "isolate JSON specialist dispatch parsing",
        "--skill-load-bypass-reason",
        "isolate JSON specialist dispatch parsing",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    gate = repair["specialist_dispatch_gate"]
    assert gate["matched_paths"] == ["context/specialist-dispatch.json"]
    assert gate["selected_user_agents"] == ["domain-reviewer"]
    assert gate["selected_subagents"] == ["reviewer", "test-writer"]
