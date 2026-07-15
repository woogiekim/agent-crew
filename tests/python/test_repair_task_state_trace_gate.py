"""Trace-first repair quality-gate tests for repair-task-state.py (F6, AC-004/005).

Spec: context/prd.md § F6 + AC-001/AC-004/AC-005; checklist
context/test-checklist.md (TC-038..TC-047, TC-052, TC-053). Derived from the
contract only — the parallel implementer's repair-task-state.py rewiring is NOT
read. The gate is exercised as a black box via ``repair-task-state.py``
subprocess (like the existing tests/python/test_quality_loop_gate.py suite).

RED state is expected: several assertions (trace-first pass without docs,
contradiction label, remediation wording no longer instructing tdd-red.md
authoring) fail until the implementer lands F6.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _trace_gate_fixtures as fx  # noqa: E402

REPAIR = fx.REPAIR


def run_repair(state_dir: Path, task_id: str, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPAIR),
            "--state-dir",
            str(state_dir),
            "--status",
            "completed",
            "--note",
            "manual completion",
            *extra,
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def _repair_record(task_dir: Path) -> dict:
    return json.loads(
        (task_dir / "context" / "manual-fallback-repair.json").read_text(encoding="utf-8")
    )


def _full_trace_passing_task(tmp_path: Path):
    """A task whose red/green/refactor/review all pass purely on trace."""
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "tests/test_update_gate.py", "def test_ok():\n    assert True\n", "add test")
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)
    fx.write_tool_events(
        task_dir,
        fx.red_then_green_rows(green_start="2026-07-15T09:00:00Z", green_end="2026-07-15T09:00:01Z"),
    )
    fx.write_delegation(task_dir, [fx.delegation_row(agent_role="reviewer")])
    fx.write_progress_buffer(task_dir, fx.implementer_and_reviewer_events(task_id=task_id))
    fx.write_quality_metrics(task_dir)
    fx.write_test_checklist_artifacts(task_dir)
    return state_dir, task_id, task_dir, repo, base


# ==========================================================================
# F6 — trace-first enforcement
# ==========================================================================
def test_success_case_gate_passes_on_trace_evidence_only(tmp_path):
    # TC-038: trace red/green/refactor/review pass without --quality-evidence docs.
    state_dir, task_id, task_dir, _repo, _base = _full_trace_passing_task(tmp_path)

    result = run_repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _repair_record(task_dir)["quality_gate"]["passed"] is True


def test_boundary_case_quality_evidence_doc_demoted_when_trace_available(tmp_path):
    # TC-039: --quality-evidence doc supplied while trace source is available;
    # the trace outcome stays authoritative (gate still passes on trace).
    state_dir, task_id, task_dir, _repo, _base = _full_trace_passing_task(tmp_path)
    (task_dir / "context" / "extra-review.md").write_text(
        "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json\n", encoding="utf-8"
    )

    result = run_repair(state_dir, task_id, "--quality-evidence", "context/extra-review.md")

    assert result.returncode == 0, result.stdout + result.stderr


def test_failure_case_blocked_output_never_instructs_authoring_tdd_docs(tmp_path):
    # TC-040 (AC-005): no SystemExit BLOCKER/DETAIL/NEXT text tells agents to
    # author context/tdd-red.md or context/tdd-refactor.md.
    repo = tmp_path / "repo"
    fx.init_git_repo(repo)
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    # No trace, no docs, no checklist -> the gate blocks.

    result = run_repair(state_dir, task_id)

    assert result.returncode != 0, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert "tdd-red.md" not in combined
    assert "tdd-refactor.md" not in combined


def test_failure_case_remediation_points_to_rerun_or_reviewer(tmp_path):
    # TC-041 (AC-005): remediation wording points to re-running the focused
    # test or invoking an independent reviewer.
    repo = tmp_path / "repo"
    fx.init_git_repo(repo)
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path, project_root=repo)

    result = run_repair(state_dir, task_id)

    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert ("re-run" in combined) or ("rerun" in combined) or ("reviewer" in combined)


def test_failure_case_contradiction_blocks_repair(tmp_path):
    # TC-042: git shows no test change but a test path is claimed.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "src/prod_only.py", "X = 1\n", "prod only")
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)
    fx.write_progress_buffer(
        task_dir, fx.implementer_and_reviewer_events(task_id=task_id, include_test_file=True)
    )
    fx.write_quality_metrics(task_dir)
    fx.write_test_checklist_artifacts(task_dir)

    result = run_repair(state_dir, task_id)

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "STATUS: blocked" in combined
    assert "test_file_claim_contradicts_git" in combined


# ==========================================================================
# Back-compat: CLI flags retained (AC-004)
# ==========================================================================
def test_boundary_case_quality_bypass_reason_flag_retained(tmp_path):
    # TC-043: --quality-bypass-reason bypasses a failing gate.
    repo = tmp_path / "repo"
    fx.init_git_repo(repo)
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path, project_root=repo)

    result = run_repair(
        state_dir, task_id, "--quality-bypass-reason", "emergency; reviewer unavailable"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    record = _repair_record(task_dir)
    assert record["quality_gate"]["bypassed"] is True
    assert record["quality_gate"]["bypass_reason"] == "emergency; reviewer unavailable"


def test_regression_case_quality_cli_flags_accepted(tmp_path):
    # TC-044: --quality-evidence and --quality-bypass-reason still parse.
    help_proc = subprocess.run(
        [sys.executable, str(REPAIR), "--help"], text=True, capture_output=True
    )
    assert help_proc.returncode == 0
    assert "--quality-evidence" in help_proc.stdout
    assert "--quality-bypass-reason" in help_proc.stdout


# ==========================================================================
# Back-compat: legacy task dirs (AC-004)
# ==========================================================================
def test_regression_case_legacy_doc_evidence_still_passes(tmp_path):
    # TC-045 / TC-046: a legacy dir with NO trace files and old-style passing
    # doc evidence repairs exactly as before.
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path)  # no project_root
    fx.write_progress_buffer(task_dir, fx.implementer_and_reviewer_events(task_id=task_id))
    fx.write_quality_metrics(task_dir)
    fx.write_test_checklist_artifacts(task_dir)
    (task_dir / "context" / "tdd_log.md").write_text(
        "TDD: RED -> GREEN -> REFACTOR. tests passed 12.\n", encoding="utf-8"
    )
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n", encoding="utf-8"
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: refactor review complete; post-refactor pytest passed.\n", encoding="utf-8"
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json.\n", encoding="utf-8"
    )

    result = run_repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _repair_record(task_dir)["quality_gate"]["passed"] is True


def test_regression_case_legacy_red_refactor_advisory_preserved(tmp_path):
    # TC-047: legacy no-trace dir keeps advisory (soft) red/refactor behavior,
    # so pipeline-outcome evidence alone still repairs.
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path)  # no project_root, no traces
    fx.write_progress_buffer(task_dir, fx.implementer_and_reviewer_events(task_id=task_id))
    fx.write_quality_metrics(task_dir)
    fx.write_test_checklist_artifacts(task_dir)

    result = run_repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    record = _repair_record(task_dir)
    assert record["quality_gate"]["passed"] is True
    assert record["quality_gate"]["red_phase_advisory"] is True
    assert record["quality_gate"]["refactor_phase_advisory"] is True


def test_boundary_case_absent_hook_does_not_change_gate_semantics(tmp_path):
    # TC-052 (SHOULD): with no tool-events.jsonl (hook not installed), the gate
    # degrades to source-unavailable and still passes on legacy pipeline evidence.
    state_dir, task_id, task_dir = fx.make_state_task(tmp_path)
    assert not (task_dir / "tool-events.jsonl").exists()
    fx.write_progress_buffer(task_dir, fx.implementer_and_reviewer_events(task_id=task_id))
    fx.write_quality_metrics(task_dir)
    fx.write_test_checklist_artifacts(task_dir)

    result = run_repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr


# ==========================================================================
# F8 — governance doc alignment (AC-005)
# ==========================================================================
def test_regression_case_governance_docs_describe_trace_derived_path():
    # TC-053 (SHOULD): governance docs no longer instruct authoring the
    # attestation files and describe the trace-derived authoritative path.
    sv = (fx.REPO_ROOT / "core" / "rules" / "self-verification.md").read_text(encoding="utf-8")
    pb = (
        fx.REPO_ROOT / "core" / "rules" / "state-files" / "progress-buffer-jsonl.md"
    ).read_text(encoding="utf-8")

    # The state-file doc's sibling section should reference the trace surface.
    assert "tool-events" in pb.lower()
    # Neither doc should present authoring tdd-red.md / tdd-refactor.md as the
    # remediation path.
    lowered = (sv + pb).lower()
    assert "author context/tdd-red.md" not in lowered
    assert "write context/tdd-red.md" not in lowered
