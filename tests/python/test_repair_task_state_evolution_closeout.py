"""Repair closeout coverage for self-evolution artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"


def _write_task(state_dir: Path, task_id: str, *, task: str = "Inspect project status") -> Path:
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({
            "schema_version": 1,
            "task_id": task_id,
            "session_id": task_id.rsplit("-", 1)[0],
            "task": task,
            "project_root": str(state_dir.parent / "repo"),
            "current_phase": "handoff_ready",
            "host_bridge_status": "current_session_required",
            "blocked_by": [],
        }) + "\n",
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps({"schema_version": 1, "stages": ["supervisor"], "completed_stages": 0}) + "\n",
        encoding="utf-8",
    )
    (task_dir / "progress.buffer.jsonl").write_text("", encoding="utf-8")
    (task_dir / "result.md").write_text("STATUS: handoff_ready\n", encoding="utf-8")
    return task_dir


def _write_skill_depth_report(task_dir: Path, candidate_name: str = "skill-content-hardening") -> None:
    (task_dir / "context" / "evolution-report.json").write_text(
        json.dumps({
            "schema_version": 1,
            "task_id": task_dir.name,
            "generation_mode": "report_only",
            "meaningful": True,
            "observed_patterns": [{
                "kind": "skill_content_depth",
                "summary": "Skill content audit found shallow skill material.",
                "evidence_refs": ["context/skill-content-audit.json"],
            }],
            "asset_candidates": [],
            "rejected_candidates": [{
                "asset_type": "skill",
                "name": candidate_name,
                "rejection_reason": "insufficient_repeated_evidence",
            }],
        }) + "\n",
        encoding="utf-8",
    )


def _write_fixed_review_finding(
    task_dir: Path,
    *,
    finding_id: str = "F-001",
    pattern_key: str = "current-session-fallback-evolution-ingestion",
) -> None:
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: NEEDS_CHANGES\n"
        "Finding: current-session fallback review corrections are not ingested "
        "before evolution closeout.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "quality-evidence.md").write_text(
        "Reviewer evidence\n\n"
        "- Initial reviewer finding: current-session fallback review findings "
        "were not converted into mistake events.\n"
        "- Fix reviewed after implementation: repair closeout now materializes "
        "the correction before running evolution analyzer.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "finding-register.json").write_text(
        json.dumps({
            "schema_version": 1,
            "findings": [
                {
                    "id": finding_id,
                    "title": "Current-session fallback review learning is not ingested",
                    "severity": "P2",
                    "status": "fixed",
                    "source": {"artifact": "context/review.md"},
                    "affected": [{"file": "core/scripts/repair-task-state.py", "line": 230}],
                    "recommended_fix": (
                        "Materialize fixed current-session fallback review findings "
                        "as mistake events before evolution analyzer runs."
                    ),
                    "verification": {
                        "test_targets": [
                            "tests/python/test_repair_task_state_evolution_closeout.py"
                        ]
                    },
                    "resolution_note": (
                        "Repair closeout writes an idempotent mistake event before "
                        "running evolution analyzer."
                    ),
                    "learning": {"pattern_key": pattern_key},
                }
            ],
        }) + "\n",
        encoding="utf-8",
    )


def test_completed_repair_runs_evolution_closeout_and_surfaces_pending_proposals(tmp_path: Path):
    state_dir = tmp_path / "state"
    previous = _write_task(state_dir, "20260101-120000-0")
    _write_skill_depth_report(previous)

    task_id = "20260102-120000-0"
    task_dir = _write_task(state_dir, task_id)
    (task_dir / "context" / "skill-content-audit.json").write_text(
        json.dumps({
            "shallow_findings": [{"skill": "example", "reason": "thin"}],
            "effective_followups": [],
        }) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state-dir", str(state_dir),
            "--status", "completed",
            "--note", "manual completion",
            task_id,
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (task_dir / "context" / "evolution-report.json").is_file()
    assert (task_dir / "context" / "evolution-report.md").is_file()
    summary = task_dir / "context" / "evolution-proposals-summary.txt"
    assert summary.is_file()
    assert "SELF_EVOLUTION_PROPOSALS: 1 pending" in summary.read_text(encoding="utf-8")
    assert "Self-Evolution Proposals" in (task_dir / "result.md").read_text(encoding="utf-8")

    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["evolution_closeout"]["analyzer"] == "completed"
    assert repair["evolution_closeout"]["pending_proposals"] == 1


def test_current_session_repair_materializes_fixed_review_finding_before_evolution(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260102-120000-0"
    task_dir = _write_task(state_dir, task_id, task="Audit current-session fallback learning evidence")
    _write_fixed_review_finding(task_dir)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state-dir", str(state_dir),
            "--status", "completed",
            "--note", "review finding fixed",
            task_id,
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    events = [
        json.loads(line)
        for line in (task_dir / "context" / "mistake-events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(events) == 1
    assert events[0]["event_type"] == "mistake_correction"
    assert events[0]["pattern_key"] == "current-session-fallback-evolution-ingestion"
    assert events[0]["correction_source"] == "reviewer_finding_register"
    assert events[0]["provenance"]["source_ref"] == "context/finding-register.json#F-001"
    assert events[0]["provenance"]["explicit_reviewer_finding"] is True
    assert events[0]["provenance"]["inferred"] is False
    assert "context/review.md" in events[0]["evidence_refs"]
    assert "context/quality-evidence.md" in events[0]["evidence_refs"]

    report = json.loads((task_dir / "context" / "evolution-report.json").read_text(encoding="utf-8"))
    patterns = report["observed_patterns"]
    assert any(
        item.get("kind") == "mistake_correction"
        and item.get("pattern_key") == "current-session-fallback-evolution-ingestion"
        for item in patterns
    )

    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["evolution_closeout"]["learning_materialization"]["recorded"] == 1


def test_current_session_repair_does_not_duplicate_materialized_review_events(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260102-120000-0"
    task_dir = _write_task(state_dir, task_id, task="Audit current-session fallback learning evidence")
    _write_fixed_review_finding(task_dir)

    for _ in range(2):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--state-dir", str(state_dir),
                "--status", "completed",
                "--note", "review finding fixed",
                task_id,
            ],
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    events = [
        json.loads(line)
        for line in (task_dir / "context" / "mistake-events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(events) == 1


def test_clean_or_malformed_current_session_repair_does_not_emit_noisy_learning(tmp_path: Path):
    state_dir = tmp_path / "state"
    clean_task = _write_task(state_dir, "20260102-120000-0", task="Clean fallback review")
    (clean_task / "context" / "review.md").write_text("REVIEW: APPROVED\n", encoding="utf-8")

    malformed_task = _write_task(state_dir, "20260102-120001-0", task="Malformed fallback review")
    (malformed_task / "context" / "finding-register.json").write_text(
        json.dumps({"schema_version": 1, "findings": [{"id": "F-bad", "status": "fixed"}]}) + "\n",
        encoding="utf-8",
    )

    for task_id, task_dir in [
        ("20260102-120000-0", clean_task),
        ("20260102-120001-0", malformed_task),
    ]:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--state-dir", str(state_dir),
                "--status", "completed",
                "--note", "manual completion",
                task_id,
            ],
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (task_dir / "context" / "mistake-events.jsonl").exists()


def test_native_repair_keeps_existing_evolution_closeout_without_fallback_learning(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260102-120000-0"
    task_dir = _write_task(state_dir, task_id, task="Native host task")
    register = json.loads((task_dir / "register.json").read_text(encoding="utf-8"))
    register["host_bridge_status"] = "completed"
    (task_dir / "register.json").write_text(json.dumps(register) + "\n", encoding="utf-8")
    _write_fixed_review_finding(task_dir)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state-dir", str(state_dir),
            "--status", "completed",
            "--note", "native completion",
            task_id,
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (task_dir / "context" / "mistake-events.jsonl").exists()
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["evolution_closeout"]["analyzer"] == "completed"


def test_repeated_current_session_review_corrections_aggregate_as_approval_required_proposal(
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    for task_id in ["20260102-120000-0", "20260103-120000-0"]:
        task_dir = _write_task(state_dir, task_id, task="Audit current-session fallback learning evidence")
        _write_fixed_review_finding(task_dir, finding_id=f"F-{task_id[-1]}")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--state-dir", str(state_dir),
                "--status", "completed",
                "--note", "review finding fixed",
                task_id,
            ],
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    proposals = json.loads((state_dir / "learning-candidates" / "proposals.json").read_text(encoding="utf-8"))
    matching = [
        item for item in proposals["proposals"]
        if item["target_asset"] == "mistake_correction:current-session-fallback-evolution-ingestion"
    ]
    assert len(matching) == 1
    assert matching[0]["status"] == "approval_required"
    assert matching[0]["proposal_type"] == "investigate_reusable_asset"
    assert matching[0]["occurrence_count"] == 2
    assert proposals["guardrails"]["asset_writes"] == "disabled"
    assert proposals["guardrails"]["generator_invoked"] is False


def test_learning_materialization_failure_does_not_block_repair_completion(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_id = "20260102-120000-0"
    task_dir = _write_task(state_dir, task_id, task="Audit current-session fallback learning evidence")
    _write_fixed_review_finding(task_dir)
    (task_dir / "context" / "mistake-events.jsonl").mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state-dir", str(state_dir),
            "--status", "completed",
            "--note", "review finding fixed",
            task_id,
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads((task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8"))
    assert repair["status"] == "completed"
    assert "learning_materialization_failed" in repair["evolution_closeout"]["errors"]
