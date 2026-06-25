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
                                "task_interpretation": "Keep skill-load fixture updates narrow.",
                                "planned_application": "Record only the understood rule needed by the pass case.",
                            }
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
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


def test_non_tdd_selected_skill_requires_matching_loaded_skill_path(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Implement a frontend workflow",
        selected_skill="frontend-typescript-react",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- ~/.agent-crew/system/agents/skills/tdd.md\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "BLOCKER: missing_required_skill_load_evidence" in result.stderr
    assert "frontend-typescript-react.md" in result.stderr


def test_json_skill_load_satisfies_non_tdd_selected_skill(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Implement a frontend workflow",
        selected_skill="frontend-typescript-react",
    )
    (task_dir / "context" / "skill-load.json").write_text(
        json.dumps(
            {
                "loaded_skills": [
                    "~/.agent-crew/user/skills/frontend-typescript-react.md"
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--skill-use-bypass-reason",
        "isolate JSON skill-load parsing",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["skill_load_gate"]["loaded_skill_names"] == ["frontend-typescript-react.md"]
    assert repair["skill_load_gate"]["required_skills"] == ["frontend-typescript-react.md"]


def test_skill_directory_skill_md_satisfies_selected_skill_name(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Implement a current-session fallback repair",
        selected_skill="current-session-fallback-repair",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- /Users/wook/.codex/memories/skills/current-session-fallback-repair/SKILL.md\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "external-skill-approval.md").write_text(
        "APPROVED: /Users/wook/.codex/memories/skills/current-session-fallback-repair/SKILL.md\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--skill-use-bypass-reason",
        "isolate Codex skill directory load parsing",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert "current-session-fallback-repair.md" in repair["skill_load_gate"]["loaded_skill_names"]
    assert repair["skill_load_gate"]["required_skills"] == ["current-session-fallback-repair.md"]


def test_external_codex_plugin_skill_requires_explicit_approval(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Implement a backend workflow",
        selected_skill="test-driven-development",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- /Users/wook/.codex/plugins/cache/claude-plugins-official/superpowers/6.0.3/skills/test-driven-development/SKILL.md\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--skill-use-bypass-reason",
        "isolate external skill policy",
    )

    assert result.returncode != 0
    assert "BLOCKER: unapproved_external_skill_load" in result.stderr
    assert "test-driven-development" in result.stderr
    assert "context/external-skill-approval.md" in result.stderr


def test_agent_crew_codex_wrapper_skill_does_not_require_external_approval(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Run an agent-crew workflow",
        selected_skill="crew-run",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- /Users/wook/.codex/skills/crew-run/SKILL.md\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--skill-use-bypass-reason",
        "isolate agent-crew wrapper allow-list",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["skill_load_gate"].get("external_skill_paths", []) == []
    assert repair["skill_load_gate"].get("unapproved_external_skill_paths", []) == []


def test_external_codex_plugin_skill_passes_with_explicit_approval(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(
        state_dir,
        task_id,
        task="Implement a backend workflow",
        selected_skill="test-driven-development",
    )
    (task_dir / "context" / "skill-load.md").write_text(
        "SKILL_LOAD: passed\n"
        "Loaded before implementation:\n"
        "- /Users/wook/.codex/plugins/cache/claude-plugins-official/superpowers/6.0.3/skills/test-driven-development/SKILL.md\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "external-skill-approval.md").write_text(
        "APPROVED: /Users/wook/.codex/plugins/cache/claude-plugins-official/superpowers/6.0.3/skills/test-driven-development/SKILL.md\n",
        encoding="utf-8",
    )

    result = _repair(
        state_dir,
        task_id,
        "--skill-use-bypass-reason",
        "isolate external skill approval",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["skill_load_gate"]["external_skill_paths"] == [
        "/Users/wook/.codex/plugins/cache/claude-plugins-official/superpowers/6.0.3/skills/test-driven-development/SKILL.md"
    ]
    assert repair["skill_load_gate"]["unapproved_external_skill_paths"] == []


def test_repair_accepts_skill_load_evidence_for_tdd_specialist(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    _write_skill_plan(task_dir)
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
                        "rule_evidence": [
                            {
                                "rule_id": "KISS",
                                "artifact_refs": ["tests/python/test_repair_task_state_skill_load_gate.py"],
                                "diff_refs": ["tests/python/test_repair_task_state_skill_load_gate.py"],
                                "verification": [
                                    "python3 -m pytest tests/python/test_repair_task_state_skill_load_gate.py -q"
                                ],
                                "adversarial_checks": ["confirmed TDD-only skill remains excluded"],
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
