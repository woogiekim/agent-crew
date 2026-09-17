"""v2 비교 입력은 최초 SHA와 의미 있는 증거에 고정된다."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core/scripts"))
spec = importlib.util.spec_from_file_location("variant_collector_inputs", ROOT / "core/scripts/variant-session-collect.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def v2(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    git(base, "init", "-b", "main")
    git(base, "config", "user.name", "Test")
    git(base, "config", "user.email", "test@example.invalid")
    (base / "app.py").write_text("value = 0\n")
    git(base, "add", ".")
    git(base, "commit", "-m", "base")
    head = git(base, "rev-parse", "HEAD")
    worktree = tmp_path / "candidate"
    git(base, "worktree", "add", "-b", "crew/v1", str(worktree), head)
    (worktree / "app.py").write_text("value = 1\n")
    git(worktree, "commit", "-am", "candidate")
    state = tmp_path / "state"
    task = state / "tasks/v1"
    (task / "context").mkdir(parents=True)
    (task / "result.md").write_text("STATUS: completed\nSUMMARY: implemented\n")
    session = {"session_id": "20260911-120000", "session_type": "variants", "status": "running",
               "variants_workflow_version": 2, "outcome_mode": "synthesis", "pre_run_head": head,
               "base_task": "원문 그대로", "candidate_count": 1,
               "selection_status": "pending", "selected_task_id": None,
               "tasks": [{"task_id": "v1", "status": "completed", "branch": "crew/v1",
                          "project_root": str(worktree), "base_project_root": str(base),
                          "task_dir": str(task), "task": "원문 그대로"}]}
    collector.write_json(state / "session.json", session)
    return base, worktree, state, task, session


def test_base_head_movement_keeps_comparison_base(v2):
    base, _, _, _, session = v2
    before = collector.review_inputs(session)
    (base / "app.py").write_text("value = 2\n")
    git(base, "commit", "-am", "new base work")
    assert collector.review_inputs(session) == before


def test_progress_log_does_not_invalidate_review(v2):
    _, _, _, task, session = v2
    before = collector.review_inputs(session)
    (task / "progress.log").write_text("resumed\n")
    (task / "context/current-status.md").write_text("resumed\n")
    assert collector.review_inputs(session) == before


def test_acceptance_evidence_invalidates_review(v2):
    _, _, _, task, session = v2
    before = collector.review_inputs(session)
    (task / "context/tests.log").write_text("new acceptance output\n")
    assert collector.review_inputs(session) != before


def test_missing_base_is_rejected(v2):
    *_, session = v2
    del session["pre_run_head"]
    with pytest.raises(ValueError, match="pre_run_head"):
        collector.review_inputs(session)


def test_mutating_variants_reject_non_git_before_handoffs(tmp_path):
    project = tmp_path / "plain"
    project.mkdir()
    home = tmp_path / "home"
    result = subprocess.run(
        ["bash", str(ROOT / "core/bin/crew"), "run", "--variants", "2", "implement"],
        cwd=project, env={**os.environ, "AGENT_CREW_HOME": str(home), "PROJECT_ROOT": str(project)},
        text=True, capture_output=True)
    assert result.returncode != 0
    assert "Git" in result.stdout + result.stderr
    assert not list(home.rglob("handoff.md"))


def test_read_only_variants_cannot_create_git_worktrees(v2, tmp_path):
    base, _, _, _, _ = v2
    before = git(base, "worktree", "list", "--porcelain")
    result = subprocess.run(
        ["bash", str(ROOT / "core/bin/crew"), "run", "--read-only", "--variants", "2", "inspect"],
        cwd=base, env={**os.environ, "AGENT_CREW_HOME": str(tmp_path / "home"), "PROJECT_ROOT": str(base)},
        text=True, capture_output=True)
    assert result.returncode != 0
    assert git(base, "worktree", "list", "--porcelain") == before


def test_collection_does_not_complete_v2_workflow(v2):
    _, _, state, _, _ = v2
    assert collector.collect_variants(state)[0] == 0
    assert collector.load_json(state / "session.json")["status"] == "running"


def test_v2_collection_guides_synthesis_not_selection(v2):
    output = collector.collect_variants(v2[2])[1]
    assert "crew variants resume" in output
    assert "Select one candidate implementation first" not in output


def test_v2_refuses_a_plain_text_review(v2):
    _, _, state, _, _ = v2
    ready = json.loads(collector.collect_until_terminal(state, 0, 1, True)[1])
    receipt = json.loads(collector.manage_review(state, ready["input_hash"], None, None, None)[1])
    report = state / "draft.md"
    report.write_text("review")
    with pytest.raises(ValueError):
        collector.manage_review(state, None, receipt["token"], None, str(report))
    assert collector.load_json(state / "variant-review-state.json")["status"] == "running"


def test_new_run_records_synthesis_contract_and_pinned_base(v2, tmp_path):
    base, _, _, _, _ = v2
    home = tmp_path / "crew-home"
    result = subprocess.run(["bash", str(ROOT / "core/bin/crew"), "run", "--variants", "2", "원문 그대로"],
                            cwd=base, env={**os.environ, "AGENT_CREW_HOME": str(home), "PROJECT_ROOT": str(base),
                                           "AGENT_CREW_AUTO_SYNC_RUNTIME_ON_RUN": "0", "AGENT_CREW_AUTO_SYNC_HOOKS_ON_RUN": "0"},
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    session = json.loads(next((home / "state").glob("*/session.json")).read_text())
    assert session["variants_workflow_version"] == 2
    assert session["outcome_mode"] == "synthesis"
    for task in session["tasks"]:
        assert collector.load_json(Path(task["task_dir"]) / "pipeline.json")["planning_required"] is True
    assert session["base_task"] == "원문 그대로"
    assert "crew variants resume" in result.stdout
    assert not (base / ".gitignore").exists()
    assert ".crew-worktrees/" in (base / ".git/info/exclude").read_text(encoding="utf-8").splitlines()
    for task in session["tasks"]:
        assert git(task["project_root"], "rev-parse", "HEAD") == session["pre_run_head"]
