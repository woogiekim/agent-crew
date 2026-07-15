"""Trace-derived quality-evidence unit tests (F1-F5).

Spec: context/prd.md § "Input/Output Contract" + AC-001..AC-003; checklist
context/test-checklist.md (TC-001..TC-037, TC-054). Derived from the contract
only — the parallel implementer's quality_loop_lib.py additions are NOT read.

RED state is expected: the F1-F4 functions and F5 trace rewiring do not exist
yet on ``quality_loop_lib``, so the ``sut`` calls raise/mismatch until the
implementer lands them. Nature prefixes (success/boundary/failure-case) label
each test; TC-IDs live in context/test-case-mapping.md, not test names.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _trace_gate_fixtures as fx  # noqa: E402


@pytest.fixture()
def sut():
    """System under test: freshly loaded quality_loop_lib module."""
    return fx.load_quality_lib()


# ==========================================================================
# F1 — git_change_evidence(task_dir, register)
# ==========================================================================
def test_success_case_git_change_evidence_classifies_added_test_file(tmp_path, sut):
    # TC-001: real start-head..HEAD diff adds a test file.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "tests/test_thing.py", "def test_x():\n    assert True\n", "add test")
    state_dir, _tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)

    evidence = sut.git_change_evidence(task_dir, {"project_root": str(repo)})

    assert evidence["available"] is True
    assert evidence["base"] == base
    assert any("tests/test_thing.py" in p for p in evidence["test_paths"])
    assert not any("tests/test_thing.py" in p for p in evidence["prod_paths"])


def test_success_case_git_change_evidence_classifies_production_only_change(tmp_path, sut):
    # TC-002: diff touches only a production file.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "src/module.py", "VALUE = 1\n", "prod change")
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)

    evidence = sut.git_change_evidence(task_dir, {"project_root": str(repo)})

    assert any("src/module.py" in p for p in evidence["prod_paths"])
    assert evidence["test_paths"] == []


def test_boundary_case_git_change_evidence_falls_back_to_pre_run_head(tmp_path, sut):
    # TC-003: start-head.txt absent, pre-run-head.txt present.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "tests/test_fb.py", "def test_y():\n    assert True\n", "add test")
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_pre_run_head(task_dir, base)  # no start-head.txt

    evidence = sut.git_change_evidence(task_dir, {"project_root": str(repo)})

    assert evidence["available"] is True
    assert evidence["base"] == base


def test_boundary_case_git_change_evidence_unavailable_when_no_baseline(tmp_path, sut):
    # TC-004: neither baseline file present.
    repo = tmp_path / "repo"
    fx.init_git_repo(repo)
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)

    evidence = sut.git_change_evidence(task_dir, {"project_root": str(repo)})

    assert evidence["available"] is False


def test_boundary_case_git_change_evidence_unavailable_when_project_root_missing(tmp_path, sut):
    # TC-005: register lacks project_root / not an existing dir.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path, project_root=None)
    fx.write_start_head(task_dir, base)

    evidence = sut.git_change_evidence(task_dir, {})

    assert evidence["available"] is False


def test_boundary_case_git_change_evidence_includes_uncommitted_test_file(tmp_path, sut):
    # TC-006 (SHOULD): uncommitted working-tree test change is collected.
    # ``git diff --name-status HEAD`` (the F1 method) surfaces modifications to
    # tracked files, so the fixture commits the test file at the baseline and
    # then leaves an uncommitted modification.
    repo = tmp_path / "repo"
    fx.init_git_repo(repo)
    base = fx.commit_file(repo, "tests/test_uncommitted.py", "def test_z():\n    pass\n", "seed test")
    fx.write_working_tree_file(
        repo, "tests/test_uncommitted.py", "def test_z():\n    assert True  # edited\n"
    )
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)  # base == HEAD; change lives in the work tree

    evidence = sut.git_change_evidence(task_dir, {"project_root": str(repo)})

    assert any("tests/test_uncommitted.py" in p for p in evidence["test_paths"])


def test_boundary_case_git_change_evidence_commit_list_shape(tmp_path, sut):
    # TC-007 (SHOULD): commits carry string sha + integer epoch ct.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "tests/test_shape.py", "def test_s():\n    pass\n", "add test")
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)

    evidence = sut.git_change_evidence(task_dir, {"project_root": str(repo)})

    assert evidence["commits"], "expected at least one commit in base..HEAD"
    for commit in evidence["commits"]:
        assert isinstance(commit["sha"], str) and commit["sha"]
        assert isinstance(commit["ct"], int)


def test_failure_case_git_change_evidence_tolerates_non_git_dir(tmp_path, sut):
    # TC-008: project_root is not a git repo — degrade, never raise.
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path, project_root=not_a_repo)
    fx.write_start_head(task_dir, "0" * 40)

    evidence = sut.git_change_evidence(task_dir, {"project_root": str(not_a_repo)})

    assert evidence["available"] is False


def test_failure_case_git_change_evidence_tolerates_malformed_baseline_sha(tmp_path, sut):
    # TC-009: start-head.txt holds a nonexistent sha.
    repo = tmp_path / "repo"
    fx.init_git_repo(repo)
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, "deadbeefnotasha")

    evidence = sut.git_change_evidence(task_dir, {"project_root": str(repo)})

    assert evidence["available"] is False


# ==========================================================================
# F2 — tool_event_test_runs(task_dir)
# ==========================================================================
def test_success_case_tool_event_test_runs_derives_red_then_green(tmp_path, sut):
    # TC-010: failing run followed by later passing run.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    fx.write_tool_events(task_dir, fx.red_then_green_rows())

    runs = sut.tool_event_test_runs(task_dir)

    assert runs["available"] is True
    assert runs["red_run"] is not None
    assert runs["red_run"]["exit_code"] == 1
    assert runs["green_run"] is not None
    assert runs["green_run"]["exit_code"] == 0
    assert runs["green_run"]["ended_at"] > runs["red_run"]["ended_at"]


@pytest.mark.parametrize(
    "command",
    [
        "pytest tests/",
        "python -m pytest tests/unit",
        "npm test",
        "yarn test",
        "go test ./...",
        "gradle test",
        "./gradlew test",
        "bash tests/run-all.sh",
        "bats tests/foo.bats",
    ],
)
def test_boundary_case_tool_event_test_runs_recognizes_test_commands(tmp_path, sut, command):
    # TC-011: each supported test-command pattern is recognized as a run.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    fx.write_tool_events(
        task_dir,
        [
            fx.tool_event_row(
                action_summary=command,
                started_at="2026-07-15T00:00:01Z",
                ended_at="2026-07-15T00:00:02Z",
                status="completed",
                exit_code=0,
            )
        ],
    )

    runs = sut.tool_event_test_runs(task_dir)

    assert runs["available"] is True
    assert len(runs["runs"]) == 1


def test_boundary_case_tool_event_test_runs_ignores_row_without_integer_exit_code(tmp_path, sut):
    # TC-012: a test-command row lacking an integer exit_code is not a run.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    fx.write_tool_events(
        task_dir,
        [
            fx.tool_event_row(
                action_summary="pytest tests/",
                started_at="2026-07-15T00:00:01Z",
                ended_at="2026-07-15T00:00:02Z",
                status="running",
                exit_code=None,
            )
        ],
    )

    runs = sut.tool_event_test_runs(task_dir)

    assert runs["runs"] == []
    assert runs["available"] is False


def test_boundary_case_tool_event_test_runs_ignores_non_test_commands(tmp_path, sut):
    # TC-013 (SHOULD): non-test commands are not counted.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    fx.write_tool_events(
        task_dir,
        [
            fx.tool_event_row(
                action_summary="git status",
                started_at="2026-07-15T00:00:01Z",
                ended_at="2026-07-15T00:00:02Z",
                exit_code=0,
            ),
            fx.tool_event_row(
                action_summary="ls -la",
                started_at="2026-07-15T00:00:03Z",
                ended_at="2026-07-15T00:00:04Z",
                exit_code=0,
            ),
        ],
    )

    runs = sut.tool_event_test_runs(task_dir)

    assert runs["runs"] == []
    assert runs["available"] is False


def test_boundary_case_tool_event_test_runs_unavailable_without_test_rows(tmp_path, sut):
    # TC-014: no test-run-shaped rows -> availability False, red/green None.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    fx.write_tool_events(task_dir, [fx.host_bridge_row(
        started_at="2026-07-15T00:00:01Z", ended_at="2026-07-15T00:00:09Z")])

    runs = sut.tool_event_test_runs(task_dir)

    assert runs["available"] is False
    assert runs["red_run"] is None
    assert runs["green_run"] is None


def test_boundary_case_tool_event_test_runs_reports_final_green_flag(tmp_path, sut):
    # TC-015 (SHOULD): final_green_after_last_commit key present + tri-state.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    fx.write_tool_events(task_dir, fx.red_then_green_rows())

    runs = sut.tool_event_test_runs(task_dir)

    assert "final_green_after_last_commit" in runs
    assert runs["final_green_after_last_commit"] in (True, False, None)


def test_boundary_case_tool_event_test_runs_green_without_preceding_red(tmp_path, sut):
    # TC-016 (SHOULD): a passing run with no earlier failing run.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    fx.write_tool_events(
        task_dir,
        [
            fx.tool_event_row(
                action_summary="pytest tests/",
                started_at="2026-07-15T00:00:05Z",
                ended_at="2026-07-15T00:00:06Z",
                status="completed",
                exit_code=0,
            )
        ],
    )

    runs = sut.tool_event_test_runs(task_dir)

    assert runs["available"] is True
    assert runs["red_run"] is None
    assert runs["green_run"] is not None


def test_failure_case_tool_event_test_runs_tolerates_malformed_jsonl(tmp_path, sut):
    # TC-017: missing/malformed tool-events.jsonl -> unavailable, never raise.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    (task_dir / "tool-events.jsonl").write_text(
        "{ not valid json\n" "also-not-json\n", encoding="utf-8"
    )

    runs = sut.tool_event_test_runs(task_dir)

    assert runs["available"] is False

    # And when the file is entirely absent:
    _s2, _t2, task_dir2 = fx.make_state_task(tmp_path, task_id="20260715-000000-1")
    runs2 = sut.tool_event_test_runs(task_dir2)
    assert runs2["available"] is False


# ==========================================================================
# F3 — independent_review_evidence(task_dir)
# ==========================================================================
def test_success_case_independent_review_via_delegation_span(tmp_path, sut):
    # TC-018: delegation.jsonl reviewer span corroborates.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    fx.write_delegation(task_dir, [fx.delegation_row(agent_role="reviewer")])

    review = sut.independent_review_evidence(task_dir)

    assert review["corroborated"] is True
    assert "delegation" in review["sources"]


def test_success_case_independent_review_via_reviewer_cost_row(tmp_path, sut):
    # TC-019: cost/{TASK_ID}.jsonl reviewer row corroborates.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    fx.write_cost_rows(task_dir, [fx.cost_row(agent="reviewer")])

    review = sut.independent_review_evidence(task_dir)

    assert review["corroborated"] is True
    assert "cost" in review["sources"]


def test_success_case_independent_review_via_host_bridge_window(tmp_path, sut):
    # TC-020: host-bridge tool-event window brackets reviewer-approved event ts.
    _state_dir, task_id, task_dir = fx.make_state_task(tmp_path)
    fx.write_progress_buffer(
        task_dir, [fx.reviewer_approved_event(ts="2026-07-15T00:00:05Z", task_id=task_id)]
    )
    fx.write_tool_events(
        task_dir,
        [fx.host_bridge_row(started_at="2026-07-15T00:00:01Z", ended_at="2026-07-15T00:00:09Z")],
    )

    review = sut.independent_review_evidence(task_dir)

    assert review["corroborated"] is True
    assert "host_bridge_window" in review["sources"]


def test_boundary_case_independent_review_not_corroborated_without_source(tmp_path, sut):
    # TC-021: reviewer-approved event but no delegation/cost/window.
    _state_dir, task_id, task_dir = fx.make_state_task(tmp_path)
    fx.write_progress_buffer(
        task_dir, [fx.reviewer_approved_event(task_id=task_id)]
    )

    review = sut.independent_review_evidence(task_dir)

    assert review["corroborated"] is False


def test_boundary_case_independent_review_window_must_bracket_event(tmp_path, sut):
    # TC-022 (SHOULD): host-bridge window NOT containing the event ts fails.
    _state_dir, task_id, task_dir = fx.make_state_task(tmp_path)
    fx.write_progress_buffer(
        task_dir, [fx.reviewer_approved_event(ts="2026-07-15T00:00:20Z", task_id=task_id)]
    )
    fx.write_tool_events(
        task_dir,
        [fx.host_bridge_row(started_at="2026-07-15T00:00:01Z", ended_at="2026-07-15T00:00:09Z")],
    )

    review = sut.independent_review_evidence(task_dir)

    assert "host_bridge_window" not in review["sources"]


def test_failure_case_independent_review_tolerates_missing_files(tmp_path, sut):
    # TC-023: all three trace files missing/malformed -> unavailable, no raise.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    (task_dir / "delegation.jsonl").write_text("garbage\n", encoding="utf-8")
    (task_dir / "tool-events.jsonl").write_text("{bad\n", encoding="utf-8")

    review = sut.independent_review_evidence(task_dir)

    assert review["available"] is False
    assert review["corroborated"] is False


# ==========================================================================
# F4 — trace_quality_evidence(task_dir, register)
# ==========================================================================
def test_success_case_trace_quality_evidence_all_phases_from_trace(tmp_path, sut):
    # TC-024: all trace sources present + passing.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    last = fx.commit_file(repo, "tests/test_all.py", "def test_a():\n    pass\n", "add test")
    _state_dir, task_id, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)
    fx.write_tool_events(
        task_dir,
        fx.red_then_green_rows(green_start="2026-07-15T09:00:00Z", green_end="2026-07-15T09:00:01Z"),
    )
    fx.write_delegation(task_dir, [fx.delegation_row(agent_role="reviewer")])
    fx.write_progress_buffer(task_dir, [fx.reviewer_approved_event(task_id=task_id)])

    evidence = sut.trace_quality_evidence(task_dir, {"project_root": str(repo)})

    for phase in ("red", "green", "refactor", "review"):
        assert phase in evidence
        assert set(("passed", "evidence_source")).issubset(evidence[phase])
    assert evidence["review"]["evidence_source"] == "trace"
    # Three sub-reports are embedded alongside the per-phase verdicts.
    assert any(key not in {"red", "green", "refactor", "review"} for key in evidence)


def test_boundary_case_trace_quality_evidence_doc_fallback_when_trace_absent(tmp_path, sut):
    # TC-025: red trace unavailable but legacy tdd-red.md present -> document.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n",
        encoding="utf-8",
    )

    evidence = sut.trace_quality_evidence(task_dir, {})

    assert evidence["red"]["evidence_source"] == "document"


def test_boundary_case_trace_quality_evidence_none_state(tmp_path, sut):
    # TC-026: neither trace nor doc evidence for a phase.
    _state_dir, _tid, task_dir = fx.make_state_task(tmp_path)

    evidence = sut.trace_quality_evidence(task_dir, {})

    assert evidence["red"]["evidence_source"] == "none"
    assert evidence["red"]["passed"] is False


# ==========================================================================
# F5 — check_quality_loop trace rewiring + new labels
# ==========================================================================
def _passing_baseline(tmp_path, sut, *, task="Implement a new update gate", task_id="20260715-000000-0"):
    """A check_quality_loop scenario wired to pass on legacy doc/pipeline paths.

    Individual F5 tests vary ONE dimension and assert only the specific label
    presence/absence, so they stay robust to unrelated coverage checks.
    """
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "tests/test_update_gate.py", "def test_ok():\n    assert True\n", "add test")
    _state_dir, tid, task_dir = fx.make_state_task(
        tmp_path, task, task_id=task_id, project_root=repo
    )
    fx.write_start_head(task_dir, base)
    fx.write_progress_buffer(task_dir, fx.implementer_and_reviewer_events(task_id=tid))
    fx.write_quality_metrics(task_dir)
    fx.write_test_checklist_artifacts(task_dir)
    return repo, base, task_dir


def test_success_case_check_quality_loop_test_file_satisfied_by_git(tmp_path, sut):
    # TC-027: git shows a real added test file; no test-path string claims.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "tests/test_git_only.py", "def test_ok():\n    assert True\n", "add test")
    _state_dir, tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)
    # No test path in progress events (files:[]) and none in result.md.
    fx.write_progress_buffer(
        task_dir, fx.implementer_and_reviewer_events(task_id=tid, include_test_file=False)
    )
    fx.write_quality_metrics(task_dir)
    fx.write_test_checklist_artifacts(task_dir)

    payload = sut.check_quality_loop(task_dir)

    assert "missing_tdd_test_file" not in payload["failures"]


def test_failure_case_check_quality_loop_contradiction_is_hard(tmp_path, sut):
    # TC-028: git available, no test-file change, yet a test path is claimed.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "src/prod_only.py", "X = 1\n", "prod only, no test")
    _state_dir, tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)
    # Progress events CLAIM a test file that git never changed.
    fx.write_progress_buffer(
        task_dir, fx.implementer_and_reviewer_events(task_id=tid, include_test_file=True)
    )
    fx.write_quality_metrics(task_dir)
    fx.write_test_checklist_artifacts(task_dir)

    payload = sut.check_quality_loop(task_dir)

    assert "test_file_claim_contradicts_git" in payload["failures"]
    assert "test_file_claim_contradicts_git" in payload["hard_failures"]


def test_success_case_check_quality_loop_red_green_from_tool_events(tmp_path, sut):
    # TC-029: tool-events red-then-green satisfy red/green without tdd-red.md.
    repo, _base, task_dir = _passing_baseline(tmp_path, sut)
    fx.write_tool_events(task_dir, fx.red_then_green_rows())
    assert not (task_dir / "context" / "tdd-red.md").exists()

    payload = sut.check_quality_loop(task_dir)

    assert "missing_tdd_red_phase_evidence" not in payload["failures"]
    assert "trace_evidence" in payload
    assert payload["trace_evidence"]["red"]["evidence_source"] == "trace"


def test_boundary_case_check_quality_loop_legacy_docs_when_trace_unavailable(tmp_path, sut):
    # TC-030: no test-run rows, but legacy tdd-red.md/tdd-refactor.md present.
    repo, _base, task_dir = _passing_baseline(tmp_path, sut)
    # No tool-events.jsonl -> F2 unavailable.
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected before implementation.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "tdd-refactor.md").write_text(
        "TDD-REFACTOR: refactor review complete; post-refactor pytest passed.\n",
        encoding="utf-8",
    )

    payload = sut.check_quality_loop(task_dir)

    assert "missing_tdd_red_phase_evidence" not in payload["failures"]
    assert "missing_tdd_refactor_phase_evidence" not in payload["failures"]


def test_boundary_case_check_quality_loop_labels_preserved_on_empty_evidence(tmp_path, sut):
    # TC-031: F2 unavailable AND no legacy docs -> today's labels still appear.
    repo, _base, task_dir = _passing_baseline(tmp_path, sut)
    # No tool-events, no tdd-red.md / tdd-refactor.md.

    payload = sut.check_quality_loop(task_dir)

    assert "missing_tdd_red_phase_evidence" in payload["failures"]
    assert "missing_tdd_refactor_phase_evidence" in payload["failures"]
    # Current classification preserved: these stay soft on standard-risk.
    assert "missing_tdd_red_phase_evidence" in payload["soft_failures"]


def test_failure_case_reviewer_approval_without_span_reported(tmp_path, sut):
    # TC-032: reviewer-approved event WITHOUT F3 corroboration.
    repo, _base, task_dir = _passing_baseline(tmp_path, sut)
    # Baseline has a reviewer-approved event but no delegation/cost/window.

    payload = sut.check_quality_loop(task_dir)

    assert "reviewer_approval_without_independent_span" in payload["failures"]
    # Standard-risk task -> soft classification.
    assert "reviewer_approval_without_independent_span" in payload["soft_failures"]


def test_failure_case_reviewer_approval_without_span_hard_under_strict(tmp_path, sut):
    # TC-032 (strict half): high-risk task escalates the label to hard.
    repo, _base, task_dir = _passing_baseline(
        tmp_path, sut, task="Deploy the release and push to remote"
    )

    payload = sut.check_quality_loop(task_dir)

    assert payload["strict_gate_required"] is True
    assert "reviewer_approval_without_independent_span" in payload["hard_failures"]


def test_success_case_corroborated_reviewer_approval_passes(tmp_path, sut):
    # TC-033: reviewer-approved event WITH corroboration (delegation span).
    repo, _base, task_dir = _passing_baseline(tmp_path, sut)
    fx.write_delegation(task_dir, [fx.delegation_row(agent_role="reviewer")])

    payload = sut.check_quality_loop(task_dir)

    assert "reviewer_approval_without_independent_span" not in payload["failures"]


def test_validation_case_reviewer_span_label_in_soft_set_and_escalates(sut):
    # TC-034: SOFT_QUALITY_FAILURES wiring + strict escalation.
    assert "reviewer_approval_without_independent_span" in sut.SOFT_QUALITY_FAILURES

    soft_hard, soft_soft = sut.classify_quality_failures(
        ["reviewer_approval_without_independent_span"], strict_gate_required=False
    )
    assert soft_soft == ["reviewer_approval_without_independent_span"]
    assert soft_hard == []

    strict_hard, strict_soft = sut.classify_quality_failures(
        ["reviewer_approval_without_independent_span"], strict_gate_required=True
    )
    assert strict_hard == ["reviewer_approval_without_independent_span"]
    assert strict_soft == []


def test_success_case_check_quality_loop_exposes_trace_evidence_block(tmp_path, sut):
    # TC-035: payload gains a trace_evidence block reflecting F1-F4.
    repo, _base, task_dir = _passing_baseline(tmp_path, sut)

    payload = sut.check_quality_loop(task_dir)

    assert "trace_evidence" in payload
    trace = payload["trace_evidence"]
    for phase in ("red", "green", "refactor", "review"):
        assert phase in trace
        assert "evidence_source" in trace[phase]


def test_boundary_case_trace_takes_precedence_over_document(tmp_path, sut):
    # TC-036: both trace and matching legacy doc present -> trace wins.
    repo, _base, task_dir = _passing_baseline(tmp_path, sut)
    fx.write_tool_events(task_dir, fx.red_then_green_rows())
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected.\n", encoding="utf-8"
    )

    payload = sut.check_quality_loop(task_dir)

    assert payload["trace_evidence"]["red"]["evidence_source"] == "trace"


def test_failure_case_contradiction_blocks_over_doc_fallback(tmp_path, sut):
    # TC-037: contradiction present AND doc claims the phase passes.
    repo = tmp_path / "repo"
    base = fx.init_git_repo(repo)
    fx.commit_file(repo, "src/prod_only.py", "X = 1\n", "prod only")
    _state_dir, tid, task_dir = fx.make_state_task(tmp_path, project_root=repo)
    fx.write_start_head(task_dir, base)
    fx.write_progress_buffer(
        task_dir, fx.implementer_and_reviewer_events(task_id=tid, include_test_file=True)
    )
    fx.write_quality_metrics(task_dir)
    fx.write_test_checklist_artifacts(task_dir)
    # A doc claims the test/red phase passed.
    (task_dir / "context" / "tdd-red.md").write_text(
        "TDD-RED: focused pytest failed as expected; tests added.\n", encoding="utf-8"
    )

    payload = sut.check_quality_loop(task_dir)

    assert "test_file_claim_contradicts_git" in payload["hard_failures"]


def test_success_case_check_quality_loop_is_deterministic(tmp_path, sut):
    # TC-054 (SUGGESTION): read-only gate yields identical verdict twice.
    repo, _base, task_dir = _passing_baseline(tmp_path, sut)
    fx.write_tool_events(task_dir, fx.red_then_green_rows())
    fx.write_delegation(task_dir, [fx.delegation_row(agent_role="reviewer")])

    first = sut.check_quality_loop(task_dir)
    second = sut.check_quality_loop(task_dir)

    assert first["failures"] == second["failures"]
    assert first["passed"] == second["passed"]
    assert first["trace_evidence"] == second["trace_evidence"]
