"""Tests for core/scripts/evolution-analyzer.py.

Exit code contract:
  0 - report generated
  3 - invalid args / missing task directory
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_RETRY = REPO_ROOT / "core" / "agents" / "supervisor-retry.md"
EVOLUTION_ANALYZER = REPO_ROOT / "core" / "scripts" / "evolution-analyzer.py"
MISTAKE_EVENTS = REPO_ROOT / "core" / "scripts" / "mistake-events.py"
EVOLUTION_LEARNING_EVENTS = REPO_ROOT / "core" / "scripts" / "evolution-learning-events.py"


def _load_evolution_analyzer():
    spec = importlib.util.spec_from_file_location(
        "evolution_analyzer_under_test",
        EVOLUTION_ANALYZER,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


evolution_analyzer = _load_evolution_analyzer()


def _write_register(task_dir: Path, *, task_id: str,
                    task: str = "implement evolution report",
                    modified_files: list[str] | None = None,
                    project_root: str = "/tmp/project",
                    repository: str | None = None) -> None:
    session_id = task_id.rsplit("-", 1)[0]
    payload = {
        "schema_version": 1,
        "task_id": task_id,
        "session_id": session_id,
        "task": task,
        "branch": "crew/evolution-report-analyzer",
        "project_root": project_root,
        "task_dir": str(task_dir),
        "execution_mode": "single",
        "current_phase": "completed",
        "approval_status": "not_required",
        "verification_status": "passed",
    }
    if repository is not None:
        payload["repository"] = repository
    if modified_files is not None:
        payload["modified_files"] = modified_files
    (task_dir / "register.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_pipeline(task_dir: Path) -> None:
    payload = {
        "schema_version": 1,
        "task": "implement evolution report",
        "stages": [{"agents": ["backend"], "skills": ["tdd"]}, "reviewer"],
        "completed_stages": 2,
    }
    (task_dir / "pipeline.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_progress(task_dir: Path, rows: list[dict]) -> None:
    with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _base_progress(task_id: str) -> list[dict]:
    session_id = task_id.rsplit("-", 1)[0]
    return [
        {
            "ts": "2026-01-01T12:00:00Z",
            "trace_id": f"{session_id}.{task_id}.0.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STARTED",
            "detail": "implement evolution report",
        },
        {
            "ts": "2026-01-01T12:01:00Z",
            "trace_id": f"{session_id}.{task_id}.3.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "COMPLETED",
            "detail": "branch=crew/evolution-report-analyzer commits=1",
        },
    ]


def _seed_task(state_dir: Path, task_id: str = "20260101-120000-0") -> Path:
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True)
    _write_register(task_dir, task_id=task_id)
    _write_pipeline(task_dir)
    _write_progress(task_dir, _base_progress(task_id))
    (task_dir / "result.md").write_text(
        "Status: completed\n"
        "Task: implement evolution report\n"
        "Branch: crew/evolution-report-analyzer\n",
        encoding="utf-8",
    )
    return task_dir


def _write_mistake_report(
    task_dir: Path,
    *,
    pattern_key: str = "readonly_review_scope_noun",
    target_assets: list[str] | None = None,
) -> None:
    (task_dir / "context" / "evolution-report.json").write_text(
        json.dumps({
            "schema_version": 1,
            "task_id": task_dir.name,
            "task": "fix routing correction",
            "generation_mode": "report_only",
            "meaningful": True,
            "signals": {
                "mistake_corrections": [{
                    "surface": "routing",
                    "mistake_type": "routing_false_positive",
                    "pattern_key": pattern_key,
                    "corrected_decision": "crew:agent",
                    "evidence_refs": ["context/review.md"],
                    "target_assets": target_assets or ["core/scripts/quality_loop_lib.py"],
                }],
            },
            "observed_patterns": [{
                "kind": "mistake_correction",
                "surface": "routing",
                "mistake_type": "routing_false_positive",
                "pattern_key": pattern_key,
                "summary": "Routing false positive was corrected.",
                "corrected_decision": "crew:agent",
                "target_assets": target_assets or ["core/scripts/quality_loop_lib.py"],
                "evidence_refs": ["context/review.md"],
            }],
            "asset_candidates": [],
            "rejected_candidates": [],
        }),
        encoding="utf-8",
    )


def test_clean_task_writes_report_only_json_and_markdown(
    script_runner, env_with_home, state_dir
):
    task_dir = _seed_task(state_dir)
    json_output = task_dir / "context" / "evolution-report.json"
    markdown_output = task_dir / "context" / "evolution-report.md"

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(json_output),
        "--markdown-output", str(markdown_output),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["task_id"] == task_dir.name
    assert payload["generation_mode"] == "report_only"
    assert payload["meaningful"] is False
    assert payload["asset_candidates"] == []
    assert payload["guardrails"] == {
        "asset_writes": "disabled",
        "generator_invoked": False,
        "verification_bypass": False,
    }
    assert "Learning Report" in markdown_output.read_text(encoding="utf-8")
    assert "No reusable asset candidate" in payload["learning_summary"]

    schema = script_runner(
        "validate-state-schema.py",
        "--state-dir", str(state_dir),
        "--task-dir", str(task_dir),
        env=env_with_home,
    )
    assert schema.returncode == 0, schema.stdout + schema.stderr


def test_register_modified_files_are_reported(script_runner, env_with_home, state_dir):
    task_dir = _seed_task(state_dir)
    _write_register(
        task_dir,
        task_id=task_dir.name,
        modified_files=[
            "core/scripts/evolution-analyzer.py",
            "tests/python/test_evolution_analyzer.py",
        ],
    )

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["signals"]["changed_files"] == [
        "core/scripts/evolution-analyzer.py",
        "tests/python/test_evolution_analyzer.py",
    ]


def test_mistake_event_recorder_is_best_effort_and_non_blocking(tmp_path: Path):
    """success-case(regression) - mistake learning cannot block the main path."""
    task_dir = tmp_path / "task"
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True)

    result = subprocess.run(
        [
            sys.executable,
            str(MISTAKE_EVENTS),
            "record",
            "--task-dir", str(task_dir),
            "--surface", "routing",
            "--mistake-type", "routing_false_positive",
            "--pattern-key", "readonly_review_scope_noun",
            "--original-decision", "crew:run",
            "--corrected-decision", "crew:agent",
            "--correction-source", "review",
            "--summary", "Read-only review scope was corrected after routing.",
            "--evidence-ref", "context/review.md",
            "--target-asset", "core/scripts/quality_loop_lib.py",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    events = [
        json.loads(line)
        for line in (context_dir / "mistake-events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["event_type"] == "mistake_correction"
    assert events[0]["non_blocking"] is True
    assert events[0]["pattern_key"] == "readonly_review_scope_noun"

    blocked_task_dir = tmp_path / "blocked-task"
    blocked_task_dir.mkdir()
    (blocked_task_dir / "context").write_text("not a directory", encoding="utf-8")
    blocked = subprocess.run(
        [
            sys.executable,
            str(MISTAKE_EVENTS),
            "record",
            "--task-dir", str(blocked_task_dir),
            "--surface", "routing",
            "--mistake-type", "routing_false_positive",
            "--pattern-key", "readonly_review_scope_noun",
            "--original-decision", "crew:run",
            "--corrected-decision", "crew:agent",
            "--correction-source", "review",
            "--summary", "This write cannot succeed but must not block.",
        ],
        text=True,
        capture_output=True,
    )

    assert blocked.returncode == 0, blocked.stdout + blocked.stderr


def test_evolution_analyzer_reports_mistake_correction_patterns(
    script_runner, env_with_home, state_dir
):
    """success-case(regression) - corrected mistakes become reusable signals."""
    task_dir = _seed_task(state_dir)
    (task_dir / "context" / "mistake-events.jsonl").write_text(
        json.dumps({
            "schema_version": 1,
            "event_type": "mistake_correction",
            "surface": "routing",
            "mistake_type": "routing_false_positive",
            "pattern_key": "readonly_review_scope_noun",
            "original_decision": "crew:run",
            "corrected_decision": "crew:agent",
            "correction_source": "review",
            "summary": "Read-only review scope noun was initially routed as mutation.",
            "evidence_refs": ["context/review.md"],
            "target_assets": ["core/scripts/quality_loop_lib.py", "tests/python/test_quality_loop_gate.py"],
            "non_blocking": True,
        }) + "\n",
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["meaningful"] is True
    assert payload["signals"]["mistake_corrections"][0]["pattern_key"] == "readonly_review_scope_noun"
    pattern = payload["observed_patterns"][0]
    assert pattern["kind"] == "mistake_correction"
    assert pattern["pattern_key"] == "readonly_review_scope_noun"
    assert pattern["target_assets"] == [
        "core/scripts/quality_loop_lib.py",
        "tests/python/test_quality_loop_gate.py",
    ]


def test_output_paths_must_match_canonical_report_artifacts(
    script_runner, env_with_home, state_dir, tmp_path: Path
):
    """failure-case(regression) - TC-006 rejects non-report task-state writes."""
    rejected_outputs = (
        ("--json-output", "register.json"),
        ("--json-output", "pipeline.json"),
        ("--json-output", "context/other.json"),
        ("--json-output", "context/evolution-report.md"),
        ("--markdown-output", "context/evolution-report.json"),
    )

    for index, (flag, relative_path) in enumerate(rejected_outputs):
        task_dir = _seed_task(state_dir, f"20260101-12000{index}-0")
        result = script_runner(
            "evolution-analyzer.py",
            "--task-dir", str(task_dir),
            flag, str(task_dir / relative_path),
            env=env_with_home,
        )

        assert result.returncode == 3
        assert "output path must be the canonical" in result.stderr

    task_dir = _seed_task(state_dir, "20260101-120010-0")
    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(tmp_path / "generated-skill.json"),
        env=env_with_home,
    )

    assert result.returncode == 3
    assert "output path must be the canonical" in result.stderr


def test_output_path_rejects_canonical_filename_symlink_escape(
    script_runner, env_with_home, state_dir, tmp_path: Path
):
    """failure-case(security) - TC-007 rejects a report symlink outside task state."""
    # given
    task_dir = _seed_task(state_dir)
    outside = tmp_path / "outside.json"
    outside.write_text("sentinel\n", encoding="utf-8")
    json_output = task_dir / "context" / "evolution-report.json"
    json_output.symlink_to(outside)

    # when
    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(json_output),
        env=env_with_home,
    )

    # then
    assert result.returncode == 3
    assert "output path must be the canonical" in result.stderr
    assert outside.read_text(encoding="utf-8") == "sentinel\n"


def test_output_path_rejects_canonical_filename_symlink_loop(
    script_runner, env_with_home, state_dir
):
    """failure-case(security) - invalid report symlink loops return the CLI error contract."""
    # given
    task_dir = _seed_task(state_dir)
    json_output = task_dir / "context" / "evolution-report.json"
    json_output.symlink_to(json_output.name)

    # when
    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(json_output),
        env=env_with_home,
    )

    # then
    assert result.returncode == 3
    assert "output path must be the canonical" in result.stderr


def test_report_write_rejects_symlink_inserted_after_validation(
    monkeypatch, state_dir, tmp_path: Path
):
    """failure-case(security) - descriptor-relative creation closes the TOCTOU gap."""
    task_dir = _seed_task(state_dir)
    json_output = task_dir / "context" / "evolution-report.json"
    outside = tmp_path / "outside.json"
    outside.write_text("sentinel\n", encoding="utf-8")
    args = argparse.Namespace(
        json_output=str(json_output),
        markdown_output=None,
    )
    original_open = evolution_analyzer.os.open
    injected = False

    def racing_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal injected
        if (
            not injected
            and path == json_output.name
            and dir_fd is not None
            and flags & os.O_CREAT
        ):
            json_output.symlink_to(outside)
            injected = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(evolution_analyzer.os, "open", racing_open)

    with pytest.raises(OSError):
        evolution_analyzer.write_report_outputs({}, args, task_dir)

    assert injected is True
    assert outside.read_text(encoding="utf-8") == "sentinel\n"


def test_retry_and_reviewer_loopback_are_observed_without_generation(
    script_runner, env_with_home, state_dir
):
    task_dir = _seed_task(state_dir)
    task_id = task_dir.name
    rows = _base_progress(task_id)
    rows.insert(
        1,
        {
            "ts": "2026-01-01T12:00:30Z",
            "trace_id": f"20260101-120000.{task_id}.2.1",
            "task_id": task_id,
            "session_id": "20260101-120000",
            "event": "RETRY",
            "agent": "backend",
            "detail": "reviewer_rejected: missing test coverage",
        },
    )
    _write_progress(task_dir, rows)

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["meaningful"] is True
    assert payload["signals"]["retries"] == 1
    assert payload["signals"]["reviewer_loop_backs"] == 1
    assert payload["asset_candidates"] == []
    assert payload["rejected_candidates"][0]["rejection_reason"] == "insufficient_repeated_evidence"
    assert any(pattern["kind"] == "review_loop_back" for pattern in payload["observed_patterns"])
    assert payload["guardrails"]["generator_invoked"] is False


def test_blocker_signal_is_reported_as_meaningful(script_runner, env_with_home, state_dir):
    task_dir = _seed_task(state_dir)
    register = json.loads((task_dir / "register.json").read_text(encoding="utf-8"))
    register["current_phase"] = "blocked"
    register["blocked_by"] = ["missing approval"]
    (task_dir / "register.json").write_text(json.dumps(register), encoding="utf-8")
    (task_dir / "result.md").write_text(
        "Status: blocked\n"
        "Task: implement evolution report\n"
        "Blocker: missing approval\n",
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["meaningful"] is True
    assert payload["signals"]["blockers"] == ["missing approval"]
    assert any(pattern["kind"] == "blocker" for pattern in payload["observed_patterns"])


def test_skill_content_depth_maps_to_relevant_rejected_candidate(
    script_runner, env_with_home, state_dir
):
    """success-case(regression) - maps skill depth to a lightweight skill patch suggestion."""
    task_dir = _seed_task(state_dir)
    (task_dir / "context" / "skill-content-audit.json").write_text(
        json.dumps({
            "shallow_findings": [{"skill": "example", "reason": "too shallow"}],
            "effective_followups": [],
        }),
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert [item["kind"] for item in payload["observed_patterns"]] == [
        "skill_content_depth"
    ]
    assert payload["rejected_candidates"] == [{
        "asset_type": "skill",
        "name": "existing-skill-patch-suggestion",
        "reason": "A single task produced a reusable-work signal; prefer a small patch to an existing skill over creating a new asset.",
        "rejection_reason": "insufficient_repeated_evidence",
        "required_evidence": "Collect repeated occurrences before suggesting a minimal patch to the closest existing skill.",
    }]


def test_analyzer_extracts_review_principle_from_kotlin_test_feedback(
    script_runner, env_with_home, state_dir
):
    """success-case(regression) - review philosophy becomes a reusable signal."""
    task_dir = _seed_task(state_dir)
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: NEEDS_CHANGES\n"
        "- [P2] Kotlin/Spring tests should default to Kotest FunSpec + MockK. "
        "JUnit 5 is acceptable only when an existing harness or framework "
        "constraint makes Kotest impractical, and that reason must be stated "
        "before using JUnit 5.\n",
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--json-output", str(task_dir / "context" / "evolution-report.json"),
        "--markdown-output", str(task_dir / "context" / "evolution-report.md"),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads((task_dir / "context" / "evolution-report.json").read_text(encoding="utf-8"))
    principle = payload["signals"]["review_principles"][0]
    assert principle["principle_key"] == "kotlin_spring_kotest_default"
    assert principle["target_assets"] == ["backend-kotlin-spring.md", "tdd.md"]
    assert "Kotest FunSpec + MockK" in principle["principle"]
    assert "JUnit 5 is allowed only" in principle["principle"]
    assert payload["observed_patterns"][0]["kind"] == "review_principle"
    assert payload["observed_patterns"][0]["principle_key"] == "kotlin_spring_kotest_default"
    assert payload["rejected_candidates"][0]["name"] == "review-principle:kotlin_spring_kotest_default"
    assert "Review Principles" in (task_dir / "context" / "evolution-report.md").read_text(encoding="utf-8")

    schema = script_runner(
        "validate-state-schema.py",
        "--state-dir", str(state_dir),
        "--task-dir", str(task_dir),
        env=env_with_home,
    )
    assert schema.returncode == 0, schema.stdout + schema.stderr


def test_analyzer_does_not_extract_review_principle_from_result_summary(
    script_runner, env_with_home, state_dir
):
    """failure-case(regression) - final summaries are not reviewer evidence."""
    task_dir = _seed_task(state_dir)
    (task_dir / "result.md").write_text(
        "Status: completed\n"
        "Kotlin/Spring tests default to Kotest FunSpec + MockK; "
        "JUnit 5 is allowed only when an existing harness constraint applies.\n",
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["signals"]["review_principles"] == []
    assert not any(
        pattern["kind"] == "review_principle"
        for pattern in payload["observed_patterns"]
    )


def test_review_principle_detectors_are_registry_driven() -> None:
    """success-case(maintainability) - reusable review principles live in detector metadata."""
    detectors = evolution_analyzer.REVIEW_PRINCIPLE_DETECTORS
    keys = [detector["principle_key"] for detector in detectors]

    assert keys
    assert len(keys) == len(set(keys))
    assert any(
        detector["principle_key"] == "kotlin_spring_kotest_default"
        and "Kotest FunSpec + MockK" in detector["principle"]
        and detector["target_assets"] == ["backend-kotlin-spring.md", "tdd.md"]
        for detector in detectors
    )


def test_proposal_aggregator_promotes_repeated_report_signals_without_asset_writes(
    script_runner, env_with_home, state_dir
):
    first = _seed_task(state_dir, "20260101-120000-0")
    second = _seed_task(state_dir, "20260102-120000-0")
    for task_dir in (first, second):
        (task_dir / "context" / "evolution-report.json").write_text(
            json.dumps({
                "schema_version": 1,
                "task_id": task_dir.name,
                "task": "improve self evolution",
                "generation_mode": "report_only",
                "meaningful": True,
                "signals": {
                    "retries": 0,
                    "reviewer_loop_backs": 0,
                    "blockers": [],
                    "changed_files": [],
                    "skill_content_audit": {
                        "available": True,
                        "shallow_finding_count": 1,
                    },
                },
                "reused_assets": [],
                "observed_patterns": [{
                    "kind": "skill_content_depth",
                    "summary": "Skill content audit found shallow skill material.",
                    "evidence_refs": ["context/skill-content-audit.json"],
                }],
                "asset_candidates": [],
                "rejected_candidates": [{
                    "asset_type": "skill",
                    "name": "existing-skill-patch-suggestion",
                    "reason": "A single task produced a reusable-work signal; prefer a small patch to an existing skill over creating a new asset.",
                    "rejection_reason": "insufficient_repeated_evidence",
                    "required_evidence": "Collect repeated occurrences before suggesting a minimal patch to the closest existing skill.",
                }],
                "learning_summary": "Reusable-work signals were observed.",
                "guardrails": {
                    "asset_writes": "disabled",
                    "generator_invoked": False,
                    "verification_bypass": False,
                },
            }),
            encoding="utf-8",
        )

    output = state_dir / "learning-candidates" / "proposals.json"
    result = script_runner(
        "evolution-proposal-aggregate.py",
        "--state-dir", str(state_dir),
        "--output", str(output),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["guardrails"] == {
        "asset_writes": "disabled",
        "generator_invoked": False,
        "needs_creation_writes": "disabled",
        "approval_required": True,
    }
    assert payload["proposals"][0]["proposal_type"] == "patch_existing_skill"
    assert payload["proposals"][0]["status"] == "approval_required"
    assert payload["proposals"][0]["evidence_refs"] == [
        "tasks/20260101-120000-0/context/evolution-report.json",
        "tasks/20260102-120000-0/context/evolution-report.json",
    ]


def test_proposal_aggregator_groups_same_pattern_across_candidate_name_drift(
    script_runner, env_with_home, state_dir
):
    first = _seed_task(state_dir, "20260101-120000-0")
    second = _seed_task(state_dir, "20260102-120000-0")
    for task_dir, candidate_name in (
        (first, "skill-content-hardening"),
        (second, "existing-skill-patch-suggestion"),
    ):
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
            }),
            encoding="utf-8",
        )

    output = state_dir / "learning-candidates" / "proposals.json"
    result = script_runner(
        "evolution-proposal-aggregate.py",
        "--state-dir", str(state_dir),
        "--output", str(output),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    proposal = json.loads(output.read_text(encoding="utf-8"))["proposals"][0]
    assert proposal["target_asset"] == "skill_content_depth"
    assert proposal["occurrence_count"] == 2
    assert proposal["evidence_refs"] == [
        "tasks/20260101-120000-0/context/evolution-report.json",
        "tasks/20260102-120000-0/context/evolution-report.json",
    ]


def test_proposal_aggregator_promotes_repeated_review_principles_to_skill_patch(
    script_runner, env_with_home, state_dir
):
    """success-case(regression) - repeated review principles become visible proposals."""
    first = _seed_task(state_dir, "20260101-120000-0")
    second = _seed_task(state_dir, "20260102-120000-0")
    for task_dir in (first, second):
        (task_dir / "context" / "evolution-report.json").write_text(
            json.dumps({
                "schema_version": 1,
                "task_id": task_dir.name,
                "task": "implement Kotlin/Spring tests",
                "generation_mode": "report_only",
                "meaningful": True,
                "signals": {
                    "retries": 0,
                    "reviewer_loop_backs": 0,
                    "blockers": [],
                    "changed_files": [],
                    "skill_content_audit": {
                        "available": False,
                        "shallow_finding_count": 0,
                    },
                    "review_principles": [{
                        "principle_key": "kotlin_spring_kotest_default",
                        "principle": "Kotlin/Spring tests default to Kotest FunSpec + MockK; JUnit 5 is allowed only when an existing harness or framework constraint makes Kotest impractical and the reason is stated first.",
                        "target_assets": ["backend-kotlin-spring.md", "tdd.md"],
                        "evidence_refs": ["context/review.md"],
                    }],
                },
                "reused_assets": [],
                "observed_patterns": [{
                    "kind": "review_principle",
                    "principle_key": "kotlin_spring_kotest_default",
                    "summary": "Reviewer identified a reusable Kotlin/Spring testing convention.",
                    "principle": "Kotlin/Spring tests default to Kotest FunSpec + MockK; JUnit 5 is allowed only when an existing harness or framework constraint makes Kotest impractical and the reason is stated first.",
                    "target_assets": ["backend-kotlin-spring.md", "tdd.md"],
                    "evidence_refs": ["context/review.md"],
                }],
                "asset_candidates": [],
                "rejected_candidates": [],
                "learning_summary": "Reusable-work signals were observed.",
                "guardrails": {
                    "asset_writes": "disabled",
                    "generator_invoked": False,
                    "verification_bypass": False,
                },
            }),
            encoding="utf-8",
        )

    output = state_dir / "learning-candidates" / "proposals.json"
    result = script_runner(
        "evolution-proposal-aggregate.py",
        "--state-dir", str(state_dir),
        "--output", str(output),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    proposal = json.loads(output.read_text(encoding="utf-8"))["proposals"][0]
    assert proposal["target_asset"] == "review_principle:kotlin_spring_kotest_default"
    assert proposal["proposal_type"] == "patch_existing_skill"
    assert proposal["source"] == "reviewer_finding"
    assert proposal["target_assets"] == ["backend-kotlin-spring.md", "tdd.md"]
    assert "Kotest FunSpec + MockK" in proposal["review_principle"]
    assert "repeated review principle" in proposal["promotion_reason"]


def test_proposal_aggregator_promotes_repeated_mistake_corrections(
    script_runner, env_with_home, state_dir
):
    """success-case(regression) - repeated corrected mistakes become visible proposals."""
    first = _seed_task(state_dir, "20260101-120000-0")
    second = _seed_task(state_dir, "20260102-120000-0")
    for task_dir in (first, second):
        (task_dir / "context" / "evolution-report.json").write_text(
            json.dumps({
                "schema_version": 1,
                "task_id": task_dir.name,
                "task": "fix routing correction",
                "generation_mode": "report_only",
                "meaningful": True,
                "signals": {
                    "retries": 0,
                    "reviewer_loop_backs": 0,
                    "blockers": [],
                    "changed_files": [],
                    "skill_content_audit": {
                        "available": False,
                        "shallow_finding_count": 0,
                    },
                    "mistake_corrections": [{
                        "surface": "routing",
                        "mistake_type": "routing_false_positive",
                        "pattern_key": "readonly_review_scope_noun",
                        "corrected_decision": "crew:agent",
                        "evidence_refs": ["context/review.md"],
                        "target_assets": ["core/scripts/quality_loop_lib.py"],
                    }],
                },
                "reused_assets": [],
                "observed_patterns": [{
                    "kind": "mistake_correction",
                    "surface": "routing",
                    "mistake_type": "routing_false_positive",
                    "pattern_key": "readonly_review_scope_noun",
                    "summary": "Routing false positive was corrected.",
                    "corrected_decision": "crew:agent",
                    "target_assets": ["core/scripts/quality_loop_lib.py"],
                    "evidence_refs": ["context/review.md"],
                }],
                "asset_candidates": [],
                "rejected_candidates": [{
                    "asset_type": "rule",
                    "name": "mistake-correction:readonly_review_scope_noun",
                    "reason": "A corrected mistake produced a reusable routing pattern.",
                    "rejection_reason": "insufficient_repeated_evidence",
                    "required_evidence": "Collect repeated corrected mistakes before proposing a system change.",
                }],
                "learning_summary": "Reusable-work signals were observed.",
                "guardrails": {
                    "asset_writes": "disabled",
                    "generator_invoked": False,
                    "verification_bypass": False,
                },
            }),
            encoding="utf-8",
        )

    output = state_dir / "learning-candidates" / "proposals.json"
    result = script_runner(
        "evolution-proposal-aggregate.py",
        "--state-dir", str(state_dir),
        "--output", str(output),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    proposal = json.loads(output.read_text(encoding="utf-8"))["proposals"][0]
    assert proposal["target_asset"] == "mistake_correction:readonly_review_scope_noun"
    assert proposal["proposal_type"] == "investigate_reusable_asset"
    assert proposal["source"] == "user_feedback"
    assert proposal["target_assets"] == ["core/scripts/quality_loop_lib.py"]
    assert "corrected mistake pattern" in proposal["promotion_reason"]


def test_learning_events_are_materialized_idempotently_from_reports(
    script_runner, env_with_home, state_dir
):
    """RED: repeated learning needs a durable event SSOT outside task-local reports."""
    task_dir = _seed_task(state_dir, "20260101-120000-0")
    _write_register(
        task_dir,
        task_id=task_dir.name,
        project_root="/tmp/agent-crew-worktree-a",
        repository="git@github.com:woogiekim/agent-crew.git",
    )
    _write_mistake_report(task_dir)

    output = state_dir / "learning" / "events.jsonl"
    first = script_runner(
        "evolution-learning-events.py",
        "--state-dir", str(state_dir),
        "--task-dir", str(task_dir),
        "--output", str(output),
        env=env_with_home,
    )
    second = script_runner(
        "evolution-learning-events.py",
        "--state-dir", str(state_dir),
        "--task-dir", str(task_dir),
        "--output", str(output),
        env=env_with_home,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["repository"] == "git@github.com:woogiekim/agent-crew.git"
    assert rows[0]["repository_key"] == "github.com/woogiekim/agent-crew"
    assert rows[0]["failure_signature"] == "mistake_correction:readonly_review_scope_noun"
    assert rows[0]["evidence_ref"] == "tasks/20260101-120000-0/context/evolution-report.json"
    assert rows[0]["reviewer_status"] == "corrected"


def test_proposal_aggregator_prefers_learning_events_and_groups_worktrees(
    script_runner, env_with_home, state_dir
):
    """RED: worktree-local task paths should not be the repeat-detection boundary."""
    output = state_dir / "learning" / "events.jsonl"
    for task_id, root in (
        ("20260101-120000-0", "/tmp/agent-crew-worktree-a"),
        ("20260102-120000-0", "/tmp/agent-crew-worktree-b"),
    ):
        task_dir = _seed_task(state_dir, task_id)
        _write_register(
            task_dir,
            task_id=task_id,
            project_root=root,
            repository="https://github.com/woogiekim/agent-crew.git",
        )
        _write_mistake_report(task_dir)
        result = script_runner(
            "evolution-learning-events.py",
            "--state-dir", str(state_dir),
            "--task-dir", str(task_dir),
            "--output", str(output),
            env=env_with_home,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    proposals = state_dir / "learning-candidates" / "proposals.json"
    result = script_runner(
        "evolution-proposal-aggregate.py",
        "--state-dir", str(state_dir),
        "--output", str(proposals),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    proposal = json.loads(proposals.read_text(encoding="utf-8"))["proposals"][0]
    assert proposal["target_asset"] == "mistake_correction:readonly_review_scope_noun"
    assert proposal["occurrence_count"] == 2
    assert proposal["evidence_refs"] == [
        "tasks/20260101-120000-0/context/evolution-report.json",
        "tasks/20260102-120000-0/context/evolution-report.json",
    ]
    assert proposal["repository_key"] == "github.com/woogiekim/agent-crew"


def test_proposal_aggregator_does_not_group_other_repository_events(
    script_runner, env_with_home, state_dir
):
    """RED: similar failures from another repository must not create a project proposal."""
    output = state_dir / "learning" / "events.jsonl"
    for task_id, repository in (
        ("20260101-120000-0", "https://github.com/woogiekim/agent-crew.git"),
        ("20260102-120000-0", "https://github.com/woogiekim/other-project.git"),
    ):
        task_dir = _seed_task(state_dir, task_id)
        _write_register(task_dir, task_id=task_id, repository=repository)
        _write_mistake_report(task_dir)
        result = script_runner(
            "evolution-learning-events.py",
            "--state-dir", str(state_dir),
            "--task-dir", str(task_dir),
            "--output", str(output),
            env=env_with_home,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    proposals = state_dir / "learning-candidates" / "proposals.json"
    result = script_runner(
        "evolution-proposal-aggregate.py",
        "--state-dir", str(state_dir),
        "--output", str(proposals),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(proposals.read_text(encoding="utf-8"))["proposals"] == []


def test_proposal_aggregator_unions_mistake_correction_targets_across_reports(
    script_runner, env_with_home, state_dir
):
    """failure-case(regression) - later evidence must not lose target assets."""
    first = _seed_task(state_dir, "20260101-120000-0")
    second = _seed_task(state_dir, "20260102-120000-0")
    for task_dir, target_assets in (
        (first, []),
        (second, ["core/scripts/quality_loop_lib.py"]),
    ):
        (task_dir / "context" / "evolution-report.json").write_text(
            json.dumps({
                "schema_version": 1,
                "task_id": task_dir.name,
                "task": "fix routing correction",
                "generation_mode": "report_only",
                "meaningful": True,
                "observed_patterns": [{
                    "kind": "mistake_correction",
                    "surface": "routing",
                    "mistake_type": "routing_false_positive",
                    "pattern_key": "readonly_review_scope_noun",
                    "summary": "Routing false positive was corrected.",
                    "corrected_decision": "crew:agent",
                    "target_assets": target_assets,
                    "evidence_refs": ["context/review.md"],
                }],
                "asset_candidates": [],
            }),
            encoding="utf-8",
        )

    output = state_dir / "learning-candidates" / "proposals.json"
    result = script_runner(
        "evolution-proposal-aggregate.py",
        "--state-dir", str(state_dir),
        "--output", str(output),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    proposal = json.loads(output.read_text(encoding="utf-8"))["proposals"][0]
    assert proposal["target_assets"] == ["core/scripts/quality_loop_lib.py"]


def test_proposal_aggregator_preserves_existing_lifecycle_decisions(
    script_runner, env_with_home, state_dir
):
    first = _seed_task(state_dir, "20260101-120000-0")
    second = _seed_task(state_dir, "20260102-120000-0")
    third = _seed_task(state_dir, "20260103-120000-0")
    for task_dir in (first, second, third):
        (task_dir / "context" / "evolution-report.json").write_text(
            json.dumps({
                "schema_version": 1,
                "task_id": task_dir.name,
                "generation_mode": "report_only",
                "observed_patterns": [{"kind": "skill_content_depth"}],
                "asset_candidates": [],
                "rejected_candidates": [{
                    "asset_type": "skill",
                    "name": "existing-skill-patch-suggestion",
                }],
            }),
            encoding="utf-8",
        )

    output = state_dir / "learning-candidates" / "proposals.json"
    output.parent.mkdir(parents=True)
    output.write_text(
        json.dumps({
            "schema_version": 1,
            "proposals": [{
                "candidate_id": "existing-skill-patch-suggestion-2x",
                "proposal_type": "patch_existing_skill",
                "status": "approved",
                "target_skill": "documentation-impact.md",
                "patch_body": "## Approved Patch\n\nKeep this text.\n",
                "decision_reason": "operator approved",
            }],
        }),
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-proposal-aggregate.py",
        "--state-dir", str(state_dir),
        "--output", str(output),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    proposal = json.loads(output.read_text(encoding="utf-8"))["proposals"][0]
    assert proposal["candidate_id"] == "existing-skill-patch-suggestion-2x"
    assert proposal["status"] == "approved"
    assert proposal["target_skill"] == "documentation-impact.md"
    assert proposal["patch_body"] == "## Approved Patch\n\nKeep this text.\n"
    assert proposal["decision_reason"] == "operator approved"
    assert proposal["occurrence_count"] == 3
    assert len(proposal["evidence_refs"]) == 3


def test_proposal_apply_requires_approved_patch_existing_skill(
    script_runner, env_with_home, state_dir, tmp_path: Path
):
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    skill = skill_dir / "example.md"
    skill.write_text("# Skill: example\n", encoding="utf-8")
    proposals = state_dir / "learning-candidates" / "proposals.json"
    proposals.parent.mkdir(parents=True)
    proposals.write_text(
        json.dumps({
            "schema_version": 1,
            "proposals": [{
                "candidate_id": "example-2x",
                "proposal_type": "patch_existing_skill",
                "status": "approval_required",
                "target_skill": "example.md",
                "patch_body": "## Added Rule\n\nUse repeated evidence only.\n",
            }],
        }),
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-proposal-apply.py",
        "--proposals", str(proposals),
        "--skill-dir", str(skill_dir),
        "--audit-output", str(state_dir / "learning-candidates" / "apply-audit.json"),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert skill.read_text(encoding="utf-8") == "# Skill: example\n"
    audit = json.loads((state_dir / "learning-candidates" / "apply-audit.json").read_text(encoding="utf-8"))
    assert audit["applied"] == []
    assert audit["skipped"][0]["reason"] == "not_approved"


def test_proposal_apply_appends_skill_patch_and_creates_agent_maker_requests(
    script_runner, env_with_home, state_dir, tmp_path: Path
):
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    skill = skill_dir / "example.md"
    skill.write_text("# Skill: example\n", encoding="utf-8")
    proposals = state_dir / "learning-candidates" / "proposals.json"
    proposals.parent.mkdir(parents=True)
    proposals.write_text(
        json.dumps({
            "schema_version": 1,
            "proposals": [
                {
                    "candidate_id": "example-2x",
                    "proposal_type": "patch_existing_skill",
                    "status": "approved",
                    "target_skill": "example.md",
                    "patch_body": "## Added Rule\n\nUse repeated evidence only.\n",
                    "evidence_refs": ["tasks/one/context/evolution-report.json"],
                },
                {
                    "candidate_id": "new-agent-2x",
                    "proposal_type": "create_agent",
                    "status": "approved",
                    "asset_name": "review-fix-verifier",
                    "asset_purpose": "Verify repeated review-fix evidence before closeout.",
                    "evidence_refs": ["tasks/one/context/evolution-report.json"],
                    "promotion_reason": "Repeated review-fix mistakes need a specialist verifier.",
                },
                {
                    "candidate_id": "new-skill-2x",
                    "proposal_type": "create_skill",
                    "status": "approved",
                    "asset_name": "review-fix-discipline",
                    "asset_purpose": "Reusable review-fix verification guidance.",
                    "evidence_refs": ["tasks/two/context/evolution-report.json"],
                    "promotion_reason": "Repeated review-fix mistakes need a reusable skill.",
                },
                {
                    "candidate_id": "new-command-2x",
                    "proposal_type": "create_command",
                    "status": "approved",
                    "asset_name": "review-fix-audit",
                    "asset_purpose": "Run a repeatable review-fix audit workflow.",
                    "evidence_refs": ["tasks/three/context/evolution-report.json"],
                    "promotion_reason": "Repeated review-fix mistakes need a reusable command.",
                },
            ],
        }),
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-proposal-apply.py",
        "--proposals", str(proposals),
        "--skill-dir", str(skill_dir),
        "--audit-output", str(state_dir / "learning-candidates" / "apply-audit.json"),
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    text = skill.read_text(encoding="utf-8")
    assert "<!-- agent-crew-evolution:example-2x:start -->" in text
    assert "Use repeated evidence only." in text
    assert not (skill_dir / "new-agent.md").exists()
    request_dir = state_dir / "learning-candidates" / "agent-maker-requests"
    requests = sorted(path.name for path in request_dir.glob("*.md"))
    assert requests == [
        "new-agent-2x.md",
        "new-command-2x.md",
        "new-skill-2x.md",
    ]
    request_text = (request_dir / "new-agent-2x.md").read_text(encoding="utf-8")
    assert "crew:agent-maker" in request_text
    assert "ASSET_TYPE: agent" in request_text
    assert "Verify repeated review-fix evidence before closeout." in request_text

    audit = json.loads((state_dir / "learning-candidates" / "apply-audit.json").read_text(encoding="utf-8"))
    assert audit["guardrails"]["asset_creation"] == "agent_maker_only"
    assert audit["guardrails"]["needs_creation_writes"] == "disabled"
    assert audit["applied"][0]["candidate_id"] == "example-2x"
    assert {
        (item["candidate_id"], item["status"])
        for item in audit["applied"]
    } == {
        ("example-2x", "applied"),
        ("new-agent-2x", "agent_maker_request_created"),
        ("new-skill-2x", "agent_maker_request_created"),
        ("new-command-2x", "agent_maker_request_created"),
    }


def test_proposal_summary_reports_pending_items(script_runner, env_with_home, state_dir):
    proposals = state_dir / "learning-candidates" / "proposals.json"
    proposals.parent.mkdir(parents=True)
    proposals.write_text(
        json.dumps({
            "schema_version": 1,
            "proposals": [
                {
                    "candidate_id": "existing-skill-patch-suggestion-2x",
                    "proposal_type": "patch_existing_skill",
                    "status": "approval_required",
                    "target_asset": "existing-skill-patch-suggestion",
                    "occurrence_count": 2,
                    "evidence_refs": [
                        "tasks/one/context/evolution-report.json",
                        "tasks/two/context/evolution-report.json",
                    ],
                },
                {
                    "candidate_id": "already-approved-2x",
                    "proposal_type": "patch_existing_skill",
                    "status": "approved",
                },
            ],
        }),
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-proposal-summary.py",
        "--proposals", str(proposals),
        "--format", "text",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "SELF_EVOLUTION_PROPOSALS: 1 pending" in result.stdout
    assert "- existing-skill-patch-suggestion-2x" in result.stdout
    assert "type: patch_existing_skill" in result.stdout
    assert "evidence: 2 tasks" in result.stdout
    assert "already-approved-2x" not in result.stdout


def test_proposal_summary_points_creation_proposals_to_agent_maker(
    script_runner, env_with_home, state_dir
):
    proposals = state_dir / "learning-candidates" / "proposals.json"
    proposals.parent.mkdir(parents=True)
    proposals.write_text(
        json.dumps({
            "schema_version": 1,
            "proposals": [{
                "candidate_id": "review-fix-verifier-2x",
                "proposal_type": "create_agent",
                "status": "approval_required",
                "asset_name": "review-fix-verifier",
                "asset_purpose": "Verify repeated review-fix evidence before closeout.",
                "occurrence_count": 2,
            }],
        }),
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-proposal-summary.py",
        "--proposals", str(proposals),
        "--format", "text",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "type: create_agent" in result.stdout
    assert "target: review-fix-verifier" in result.stdout
    assert "next: review and approve; approved creation proposals are handed to crew:agent-maker" in result.stdout


def test_proposal_summary_surfaces_target_principle_and_reason(
    script_runner, env_with_home, state_dir
):
    proposals = state_dir / "learning-candidates" / "proposals.json"
    proposals.parent.mkdir(parents=True)
    proposals.write_text(
        json.dumps({
            "schema_version": 1,
            "proposals": [{
                "candidate_id": "review-principle-kotlin-spring-kotest-default-2x",
                "proposal_type": "patch_existing_skill",
                "status": "approval_required",
                "target_asset": "review_principle:kotlin_spring_kotest_default",
                "target_assets": ["backend-kotlin-spring.md", "tdd.md"],
                "review_principle": "Kotlin/Spring tests default to Kotest FunSpec + MockK; JUnit 5 is allowed only when a concrete existing harness or framework constraint makes Kotest impractical and the reason is stated first.",
                "promotion_reason": "2 independent evolution reports recorded the same repeated review principle.",
                "occurrence_count": 2,
                "evidence_refs": [
                    "tasks/one/context/evolution-report.json",
                    "tasks/two/context/evolution-report.json",
                ],
            }],
        }),
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-proposal-summary.py",
        "--proposals", str(proposals),
        "--format", "text",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "target: backend-kotlin-spring.md, tdd.md" in result.stdout
    assert "principle: Kotlin/Spring tests default to Kotest FunSpec + MockK" in result.stdout
    assert "reason: 2 independent evolution reports" in result.stdout


def test_proposal_summary_json_counts_pending_items(script_runner, env_with_home, state_dir):
    proposals = state_dir / "learning-candidates" / "proposals.json"
    proposals.parent.mkdir(parents=True)
    proposals.write_text(
        json.dumps({
            "schema_version": 1,
            "proposals": [{
                "candidate_id": "investigate-reusable-asset-2x",
                "proposal_type": "investigate_reusable_asset",
                "status": "approval_required",
                "occurrence_count": 3,
            }],
        }),
        encoding="utf-8",
    )

    result = script_runner(
        "evolution-proposal-summary.py",
        "--proposals", str(proposals),
        "--format", "json",
        env=env_with_home,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["pending_count"] == 1
    assert payload["proposals"][0]["candidate_id"] == "investigate-reusable-asset-2x"


def test_supervisor_closeout_documents_proposal_aggregation_step():
    document = SUPERVISOR_RETRY.read_text(encoding="utf-8")

    assert "#### 2e. Evolution proposals — approval-gated surfacing" in document
    assert "evolution-proposal-aggregate.py" in document
    assert "evolution-proposal-summary.py" in document
    assert "EVOLUTION_PROPOSALS" in document
    assert "EVOLUTION_PROPOSALS_FAILED" in document
    assert "rm -f \"${EVOLUTION_PROPOSALS_SUMMARY}\"" in document
    assert "--format text > \"${EVOLUTION_PROPOSALS_SUMMARY}\"" in document


def _evolution_closeout_block() -> str:
    document = SUPERVISOR_RETRY.read_text(encoding="utf-8")
    section = document.split(
        "#### 2d. Evolution report — report-only reusable asset analysis",
        1,
    )[1]
    return section.split("```bash\n", 1)[1].split("\n```", 1)[0]


def _aar_closeout_block() -> str:
    document = SUPERVISOR_RETRY.read_text(encoding="utf-8")
    section = document.split(
        "#### 2c. AAR debrief — close the learning loop",
        1,
    )[1]
    return section.split("```bash\n", 1)[1].split("\n```", 1)[0]


def test_aar_debrief_logs_failed_event_when_debrief_json_is_unreadable(tmp_path: Path):
    """regression: AAR debrief parser failures must not disappear as not_meaningful."""
    agent_crew_home = tmp_path / "home"
    script = agent_crew_home / "scripts" / "telemetry-aggregate.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "#!/usr/bin/env python3\nprint('not-json')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    block = _aar_closeout_block()
    harness = (
        "log_progress() { printf '%s|%s\\n' \"$1\" \"$2\"; }\n"
        "HAS_COST_TRACKING=0\n"
        + block
    )

    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "AGENT_CREW_HOME": str(agent_crew_home),
            "STATE_DIR": str(tmp_path / "state"),
            "TASK_ID": "20260101-120000-0",
        },
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "AAR_DEBRIEF_FAILED|non_blocking=true reason=invalid_debrief_output"
    ]


def _write_evolution_stub(agent_crew_home: Path) -> None:
    script = agent_crew_home / "scripts" / "evolution-analyzer.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path


def argument(name: str) -> Path:
    return Path(sys.argv[sys.argv.index(name) + 1])


mode = os.environ["EVOLUTION_STUB_MODE"]
task_dir = argument("--task-dir")
if (task_dir / "context").is_symlink():
    raise SystemExit(3)
for flag in ("--json-output", "--markdown-output"):
    argument(flag).unlink(missing_ok=True)
if mode in {"partial-nonzero", "partial-zero", "success"}:
    argument("--json-output").write_text("fresh-json\\n", encoding="utf-8")
if mode == "success":
    argument("--markdown-output").write_text("fresh-markdown\\n", encoding="utf-8")
if mode != "success":
    for flag in ("--json-output", "--markdown-output"):
        argument(flag).unlink(missing_ok=True)
raise SystemExit(1 if mode in {"fail", "partial-nonzero"} else 0)
""",
        encoding="utf-8",
    )


def test_supervisor_closeout_logs_success_only_for_fresh_complete_reports(tmp_path: Path):
    """boundary-case(audit) - accepts only fresh, complete analyzer reports."""
    agent_crew_home = tmp_path / "home"
    state_dir = tmp_path / "state"
    _write_evolution_stub(agent_crew_home)
    block = _evolution_closeout_block()
    harness = "log_progress() { printf '%s|%s\\n' \"$1\" \"$2\"; }\n" + block

    for mode in ("fail", "partial-nonzero", "partial-zero", "success"):
        task_dir = state_dir / "tasks" / mode
        context_dir = task_dir / "context"
        context_dir.mkdir(parents=True)
        json_output = context_dir / "evolution-report.json"
        markdown_output = context_dir / "evolution-report.md"
        json_output.write_text("stale-json\n", encoding="utf-8")
        markdown_output.write_text("stale-markdown\n", encoding="utf-8")

        result = subprocess.run(
            ["bash", "-c", harness],
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "AGENT_CREW_HOME": str(agent_crew_home),
                "AGENT_CREW_EVOLUTION_MODE": "report",
                "EVOLUTION_STUB_MODE": mode,
                "STATE_DIR": str(state_dir),
                "TASK_DIR": str(task_dir),
            },
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        events = [line.split("|", 1)[0] for line in result.stdout.splitlines()]
        if mode == "success":
            assert events == ["EVOLUTION_ANALYZER"]
            assert json_output.read_text(encoding="utf-8") == "fresh-json\n"
            assert markdown_output.read_text(encoding="utf-8") == "fresh-markdown\n"
        else:
            assert events == ["EVOLUTION_ANALYZER_FAILED"]
            assert not json_output.exists()
            assert not markdown_output.exists()


def test_supervisor_closeout_rejects_symlinked_context_before_file_operations(
    tmp_path: Path,
):
    """failure-case(security) - a context symlink cannot redirect closeout writes."""
    agent_crew_home = tmp_path / "home"
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "symlink-context"
    outside = tmp_path / "outside"
    outside.mkdir(parents=True)
    task_dir.mkdir(parents=True)
    (task_dir / "context").symlink_to(outside, target_is_directory=True)
    _write_evolution_stub(agent_crew_home)

    json_output = outside / "evolution-report.json"
    markdown_output = outside / "evolution-report.md"
    stderr_output = outside / "evolution-report.stderr.txt"
    json_output.write_text("outside-json\n", encoding="utf-8")
    markdown_output.write_text("outside-markdown\n", encoding="utf-8")
    stderr_output.write_text("outside-stderr\n", encoding="utf-8")

    block = _evolution_closeout_block()
    harness = "log_progress() { printf '%s|%s\\n' \"$1\" \"$2\"; }\n" + block
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "AGENT_CREW_HOME": str(agent_crew_home),
            "AGENT_CREW_EVOLUTION_MODE": "report",
            "EVOLUTION_STUB_MODE": "success",
            "STATE_DIR": str(state_dir),
            "TASK_DIR": str(task_dir),
        },
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "EVOLUTION_ANALYZER_FAILED|non_blocking=true reason=analyzer_or_artifact_prep_failed"
    ]
    assert json_output.read_text(encoding="utf-8") == "outside-json\n"
    assert markdown_output.read_text(encoding="utf-8") == "outside-markdown\n"
    assert stderr_output.read_text(encoding="utf-8") == "outside-stderr\n"


def test_supervisor_closeout_does_not_use_symlinked_stderr_artifact(
    tmp_path: Path,
):
    """failure-case(security) - stderr redirection cannot truncate a symlink target."""
    agent_crew_home = tmp_path / "home"
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "symlink-stderr"
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True)
    _write_evolution_stub(agent_crew_home)

    outside_stderr = tmp_path / "outside-stderr.txt"
    outside_stderr.write_text("outside-stderr\n", encoding="utf-8")
    (context_dir / "evolution-report.stderr.txt").symlink_to(outside_stderr)

    block = _evolution_closeout_block()
    harness = "log_progress() { printf '%s|%s\\n' \"$1\" \"$2\"; }\n" + block
    result = subprocess.run(
        ["bash", "-c", harness],
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "AGENT_CREW_HOME": str(agent_crew_home),
            "AGENT_CREW_EVOLUTION_MODE": "report",
            "EVOLUTION_STUB_MODE": "success",
            "STATE_DIR": str(state_dir),
            "TASK_DIR": str(task_dir),
        },
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [
        "EVOLUTION_ANALYZER|mode=report artifacts=context/evolution-report.json,context/evolution-report.md"
    ]
    assert outside_stderr.read_text(encoding="utf-8") == "outside-stderr\n"
    assert (context_dir / "evolution-report.json").is_file()
    assert (context_dir / "evolution-report.md").is_file()


def test_supervisor_closeout_delegates_artifact_lifecycle_to_analyzer():
    block = _evolution_closeout_block()

    assert "EVOLUTION_STDERR_OUTPUT" not in block
    assert "rm -f" not in block


def test_output_is_deterministic(script_runner, env_with_home, state_dir):
    task_dir = _seed_task(state_dir)

    first = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )
    second = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(task_dir),
        "--format", "json",
        env=env_with_home,
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    assert first.stdout == second.stdout


def test_missing_task_dir_exits_3(script_runner, env_with_home, tmp_path: Path):
    result = script_runner(
        "evolution-analyzer.py",
        "--task-dir", str(tmp_path / "missing-task"),
        env=env_with_home,
    )

    assert result.returncode == 3
    assert "task directory not found" in result.stderr
