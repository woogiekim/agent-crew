"""기존 후보 재사용과 비교 리뷰의 재개 계약을 검증한다."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "core/scripts/variant-session-collect.py"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def command(state, action, *args):
    return subprocess.run([sys.executable, str(SCRIPT), action, "--state-dir", str(state), *args],
                          capture_output=True, text=True, timeout=10)


@pytest.fixture
def resumable(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    git(base, "init", "-b", "main")
    git(base, "config", "user.name", "Test")
    git(base, "config", "user.email", "test@example.invalid")
    (base / "shared.txt").write_text("original\n")
    git(base, "add", ".")
    git(base, "commit", "-m", "initial")
    worktree = tmp_path / "candidate"
    git(base, "worktree", "add", "-b", "crew/v1", str(worktree))
    (worktree / "shared.txt").write_text("candidate\n")
    git(worktree, "commit", "-am", "candidate")
    state = tmp_path / "state"
    task_dir = state / "tasks/v1"
    task_dir.mkdir(parents=True)
    (task_dir / "result.md").write_text("STATUS: completed\nSUMMARY: candidate\n")
    session = {"session_type": "variants", "session_id": "resume-test",
               "selection_status": "pending", "selected_task_id": None,
               "tasks": [{"task_id": "v1", "branch": "crew/v1", "status": "completed",
                          "project_root": str(worktree), "base_project_root": str(base)}]}
    session["tasks"][0]["task_dir"] = str(task_dir)
    (state / "session.json").write_text(json.dumps(session))
    return base, worktree, state, task_dir


def payload(result):
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_resume_reuses_completed_review_and_never_selects_or_merges(resumable):
    base, worktree, state, _ = resumable
    before = git(base, "rev-parse", "HEAD"), git(worktree, "rev-parse", "HEAD")
    ready = payload(command(state, "resume", "--timeout", "0"))
    assert ready["next_action"] == "review_required"
    claim = payload(command(state, "review", "--claim", ready["input_hash"]))
    assert payload(command(state, "resume", "--timeout", "0"))["next_action"] == "review_in_progress"
    assert command(state, "review", "--claim", ready["input_hash"]).returncode == 2
    report = state / "draft.md"
    report.write_text("# 비교 리뷰\n\nv1 추천. 요구사항과 테스트를 검토했다.\n")
    payload(command(state, "review", "--complete", claim["token"], "--report", str(report)))

    assert payload(command(state, "resume", "--timeout", "0"))["next_action"] == "review_complete"
    assert (state / "variant-review.md").read_text() == report.read_text()
    assert before == (git(base, "rev-parse", "HEAD"), git(worktree, "rev-parse", "HEAD"))
    assert json.loads((state / "session.json").read_text())["selected_task_id"] is None


def test_timeout_then_resume_retains_candidates(resumable):
    _, _, state, task_dir = resumable
    (task_dir / "result.md").write_text("STATUS: running\n")
    first = command(state, "resume", "--timeout", "0")
    assert first.returncode == 3
    assert not (state / "variant-review-state.json").exists()
    (task_dir / "result.md").write_text("STATUS: completed\n")
    ready = payload(command(state, "resume", "--timeout", "0"))
    assert ready["next_action"] == "review_required"
    assert [t["task_id"] for t in json.loads((state / "session.json").read_text())["tasks"]] == ["v1"]


@pytest.mark.parametrize("change", ["commit", "result", "evidence", "session"])
def test_review_completion_rejects_changed_inputs(resumable, change):
    _, worktree, state, task_dir = resumable
    ready = payload(command(state, "resume", "--timeout", "0"))
    claim = payload(command(state, "review", "--claim", ready["input_hash"]))
    if change == "commit":
        (worktree / "shared.txt").write_text("changed\n")
        git(worktree, "commit", "-am", "changed")
    elif change == "result":
        (task_dir / "result.md").write_text("STATUS: completed\nSUMMARY: changed\n")
    elif change == "evidence":
        (task_dir / "context").mkdir()
        (task_dir / "context/tests.log").write_text("new evidence\n")
    else:
        session = json.loads((state / "session.json").read_text())
        session["session_id"] = "replacement"
        (state / "session.json").write_text(json.dumps(session))
    report = state / "draft.md"
    report.write_text("stale report")

    assert command(state, "review", "--complete", claim["token"], "--report", str(report)).returncode == 2
    assert not (state / "variant-review.md").exists()


def test_release_requires_owner_token_and_allows_explicit_retry(resumable):
    _, _, state, _ = resumable
    ready = payload(command(state, "resume", "--timeout", "0"))
    claim = payload(command(state, "review", "--claim", ready["input_hash"]))
    assert command(state, "review", "--release", "wrong").returncode == 2
    payload(command(state, "review", "--release", claim["token"]))
    retry = payload(command(state, "review", "--claim", ready["input_hash"]))
    assert retry["token"] != claim["token"]


def test_wait_does_not_collect_replacement_session(resumable, monkeypatch):
    _, _, state, task_dir = resumable
    spec = importlib.util.spec_from_file_location("collector", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (task_dir / "result.md").write_text("STATUS: running\n")
    replacement = {"session_type": "variants", "session_id": "new", "tasks": []}

    def replace_session(_):
        assert not (state / ".variants.lock").exists()
        (state / "session.json").write_text(json.dumps(replacement))

    monkeypatch.setattr(module.time, "sleep", replace_session)
    code, _ = module.collect_until_terminal(state, 10, 1)
    assert code == 2
    assert json.loads((state / "session.json").read_text()) == replacement


@pytest.mark.parametrize("contents", ["{broken", "{}", '{"status":"running"}'])
def test_corrupt_review_receipt_fails_closed(resumable, contents):
    _, _, state, _ = resumable
    (state / "variant-review-state.json").write_text(contents)
    assert command(state, "resume", "--timeout", "0").returncode == 2
    assert (state / "variant-review-state.json").read_text() == contents


def test_completed_review_becomes_stale_when_evidence_changes(resumable):
    _, _, state, task_dir = resumable
    ready = payload(command(state, "resume", "--timeout", "0"))
    claim = payload(command(state, "review", "--claim", ready["input_hash"]))
    report = state / "draft.md"
    report.write_text("review")
    payload(command(state, "review", "--complete", claim["token"], "--report", str(report)))
    (task_dir / "result.md").write_text("STATUS: completed\nSUMMARY: corrected\n")

    changed = payload(command(state, "resume", "--timeout", "0"))
    assert changed["next_action"] == "review_required"
    assert changed["input_hash"] != ready["input_hash"]
    assert command(state, "review", "--claim", ready["input_hash"]).returncode == 2


def test_native_resume_and_review_forward_options(resumable, tmp_path):
    base, _, state, _ = resumable
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "state/base").symlink_to(state, target_is_directory=True)
    env = {**os.environ, "PROJECT_ROOT": str(base), "AGENT_CREW_HOME": str(home)}
    cli = SCRIPT.parents[1] / "bin/crew"
    result = subprocess.run(["bash", str(cli), "variants", "resume", "--timeout", "0"],
                            cwd=base, env=env, capture_output=True, text=True, timeout=10)
    ready = payload(result)
    claim = subprocess.run(["bash", str(cli), "variants", "review", "--claim", ready["input_hash"]],
                           cwd=base, env=env, capture_output=True, text=True, timeout=10)
    assert payload(claim)["status"] == "running"


def test_resume_reports_no_successful_candidates_without_claiming_review(resumable):
    _, _, state, task_dir = resumable
    (task_dir / "result.md").write_text("STATUS: blocked\nBLOCKER: unavailable\n")
    ready = payload(command(state, "resume", "--timeout", "0"))
    assert ready["next_action"] == "no_completed_candidates"
    assert command(state, "review", "--claim", ready["input_hash"]).returncode == 2


def test_concurrent_review_claims_have_only_one_owner(resumable):
    _, _, state, _ = resumable
    ready = payload(command(state, "resume", "--timeout", "0"))
    args = [sys.executable, str(SCRIPT), "review", "--state-dir", str(state), "--claim", ready["input_hash"]]
    processes = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    try:
        for process in processes:
            process.communicate(timeout=10)
        assert sorted(process.returncode for process in processes) == [0, 2]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()


def test_interrupted_wait_can_resume_without_new_tasks(resumable, monkeypatch):
    _, _, state, task_dir = resumable
    spec = importlib.util.spec_from_file_location("collector", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (task_dir / "result.md").write_text("STATUS: running\n")

    def interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(module.time, "sleep", interrupt)
    with pytest.raises(KeyboardInterrupt):
        module.collect_until_terminal(state, 10, 1, resume=True)
    assert not (state / ".variants.lock").exists()
    before = json.loads((state / "session.json").read_text())["tasks"]
    (task_dir / "result.md").write_text("STATUS: completed\n")

    assert payload(command(state, "resume", "--timeout", "0"))["next_action"] == "review_required"
    after = json.loads((state / "session.json").read_text())["tasks"]
    assert [(t["task_id"], t["project_root"]) for t in before] == [(t["task_id"], t["project_root"]) for t in after]
