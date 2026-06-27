"""Tests for TDD cycle evidence on manual Codex fallback repair."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"


def _write_test_checklist_artifacts(task_dir: Path) -> None:
    (task_dir / "context" / "test-checklist.md").write_text(
        "| TC-ID | Category | Given | When | Then | Priority | Level | Reason |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| TC-001 | Regression | repair fallback has TDD evidence | repair runs | quality gate passes | P1 | MUST | fallback closeout |\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "test-checklist-review.md").write_text(
        "REVIEW: APPROVED\n"
        "CHECKLIST_REVIEW_RESULT: approved\n"
        "- Missing MUST: none\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "test-case-mapping.md").write_text(
        "| TC-ID | Test | Covered |\n"
        "|---|---|---|\n"
        "| TC-001 | tests/python/test_repair_task_state_tdd_red_gate.py | YES |\n",
        encoding="utf-8",
    )


def _write_task(state_dir: Path, task_id: str = "20260604-000000-0") -> Path:
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (task_dir / "context").mkdir()
    (task_dir / "register.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "session_id": "20260604-000000",
                "task": "Implement production mapping fix",
                "current_phase": "handoff_ready",
                "host_bridge_status": "current_session_required",
                "blocked_by": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task": "Implement production mapping fix",
                "stages": [
                    {"agents": ["backend"], "tdd_parallel": True},
                    "reviewer",
                ],
                "completed_stages": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows = [
        {
            "ts": "2026-06-04T00:00:00Z",
            "trace_id": f"20260604-000000.{task_id}.1.1",
            "task_id": task_id,
            "session_id": "20260604-000000",
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "test-writer",
            "attempt": 1,
            "status": "completed",
            "detail": "TDD RED GREEN REFACTOR, focused pytest passed",
            "files": ["context/tdd_log.md", "tests/python/test_mapping_fix.py"],
        },
        {
            "ts": "2026-06-04T00:00:01Z",
            "trace_id": f"20260604-000000.{task_id}.1.1",
            "task_id": task_id,
            "session_id": "20260604-000000",
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "backend",
            "attempt": 1,
            "status": "completed",
            "detail": "backend implementation complete",
            "files": [],
        },
        {
            "ts": "2026-06-04T00:00:02Z",
            "trace_id": f"20260604-000000.{task_id}.2.1",
            "task_id": task_id,
            "session_id": "20260604-000000",
            "event": "STAGE_DONE",
            "stage": 2,
            "agent": "reviewer",
            "attempt": 1,
            "status": "completed",
            "detail": "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
            "files": ["context/review.md"],
        },
    ]
    with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    (task_dir / "context" / "specialist-dispatch.md").write_text(
        "selected_agent: backend\n"
        "selected_skill: tdd\n"
        "selection_reason: implementation-stage mapping fix\n"
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
    (task_dir / "context" / "skill-use.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "core/rules/code-quality.md",
                        "applied_rules": ["KISS", "YAGNI", "DRY"],
                        "evidence_refs": ["tests/python/test_repair_task_state_tdd_red_gate.py"],
                        "output_files": ["tests/python/test_repair_task_state_tdd_red_gate.py"],
                        "verification": ["python3 -m pytest tests/python/test_repair_task_state_tdd_red_gate.py -q"],
                        "rule_evidence": [
                            {
                                "rule_id": "KISS",
                                "artifact_refs": ["tests/python/test_repair_task_state_tdd_red_gate.py"],
                                "diff_refs": ["tests/python/test_repair_task_state_tdd_red_gate.py"],
                                "verification": [
                                    "python3 -m pytest tests/python/test_repair_task_state_tdd_red_gate.py -q"
                                ],
                                "adversarial_checks": ["confirmed quality-loop failures still block first"],
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
    (task_dir / "context" / "skill-plan.json").write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "skill_path": "core/rules/code-quality.md",
                        "rules": [
                            {
                                "rule_id": "KISS",
                                "task_interpretation": "Keep TDD repair gate evidence scoped to repair state.",
                                "planned_application": "Add no extra pipeline semantics beyond existing quality checks.",
                            }
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd_log.md").write_text(
        "TDD: RED -> GREEN -> REFACTOR. focused pytest passed.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "quality-metrics.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hallucination_detected": False,
                "rollback_performed": False,
                "human_intervention_required": False,
                "factuality_review": "passed",
                "evidence_paths": ["context/review.md"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _write_test_checklist_artifacts(task_dir)
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
            *extra,
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def test_mutating_repair_records_advisory_without_red_phase_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["red_phase_advisory"] is True
    assert repair["quality_gate"]["refactor_phase_advisory"] is True
    assert repair["quality_gate"]["red_phase_evidence_paths"] == []
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "TDD_RED_PHASE: advisory" in result_text
    assert "TDD_REFACTOR_PHASE: advisory" in result_text


def test_mutating_repair_accepts_red_and_refactor_phase_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: refactor review complete; post-refactor pytest passed.\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["red_phase_passed"] is True
    assert repair["quality_gate"]["red_phase_evidence_paths"] == ["context/tdd-red.md"]
    assert repair["quality_gate"]["green_phase_passed"] is True
    assert repair["quality_gate"]["refactor_phase_passed"] is True
    assert repair["quality_gate"]["refactor_phase_evidence_paths"] == ["context/tdd-refactor.md"]
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "TDD_GREEN_PHASE: passed" in result_text
    assert "TDD_RED_PHASE: passed" in result_text
    assert "TDD_RED_EVIDENCE: context/tdd-red.md" in result_text
    assert "TDD_REFACTOR_PHASE: passed" in result_text
    assert "TDD_REFACTOR_EVIDENCE: context/tdd-refactor.md" in result_text


def test_mutating_repair_records_advisory_with_red_but_without_refactor_phase_evidence(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["red_phase_passed"] is True
    assert repair["quality_gate"]["red_phase_advisory"] is False
    assert repair["quality_gate"]["refactor_phase_passed"] is True
    assert repair["quality_gate"]["refactor_phase_advisory"] is True
    assert repair["quality_gate"]["refactor_phase_evidence_paths"] == []


def test_mutating_repair_ignores_refactor_mentions_inside_red_artifact(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n"
        "Expected follow-up artifact: context/tdd-refactor.md.\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id, "--quality-evidence", "context/tdd-red.md")

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["red_phase_evidence_paths"] == ["context/tdd-red.md"]
    assert repair["quality_gate"]["refactor_phase_evidence_paths"] == []
    assert repair["quality_gate"]["refactor_phase_advisory"] is True


def test_mutating_repair_accepts_explicit_tdd_exception(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "tdd-exception.md").write_text(
        "TDD_EXCEPTION: red failure cannot be produced because the target harness is unavailable.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: no-op refactor decision documented; post-refactor verification passed.\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["red_phase_passed"] is True
    assert repair["quality_gate"]["tdd_exception_paths"] == ["context/tdd-exception.md"]
    assert repair["quality_gate"]["refactor_phase_passed"] is True
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "TDD_RED_PHASE: exception" in result_text
    assert "TDD_EXCEPTION: context/tdd-exception.md" in result_text
    assert "TDD_REFACTOR_PHASE: passed" in result_text


def test_quality_bypass_records_missing_red_phase(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260604-000000-0"
    task_dir = _write_task(state_dir, task_id)
    for name in ("register.json", "pipeline.json"):
        path = task_dir / name
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["task"] = "Implement production mapping fix and deploy the release"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    result = _repair(
        state_dir,
        task_id,
        "--quality-bypass-reason",
        "manual current-session repair without runnable red-phase evidence",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["quality_gate"]["bypassed"] is True
    assert repair["quality_gate"]["red_phase_passed"] is False
    assert repair["quality_gate"]["red_phase_evidence_paths"] == []
    assert repair["quality_gate"]["refactor_phase_passed"] is False
    assert repair["quality_gate"]["refactor_phase_evidence_paths"] == []
