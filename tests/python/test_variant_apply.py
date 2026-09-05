"""실제 Git worktree로 variants 적용 미리보기의 무변경 계약을 검증한다."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "core/scripts/variant-session-collect.py"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


@pytest.fixture
def candidate(tmp_path):
    base = tmp_path / "한글 base"
    base.mkdir()
    git(base, "init", "-b", "main")
    git(base, "config", "user.name", "Test")
    git(base, "config", "user.email", "test@example.invalid")
    (base / "shared.txt").write_text("original\n")
    git(base, "add", ".")
    git(base, "commit", "-m", "initial")
    worktree = tmp_path / "variant"
    git(base, "worktree", "add", "-b", "crew/v1", str(worktree))
    (worktree / "shared.txt").write_text("candidate\n")
    git(worktree, "commit", "-am", "candidate")
    state = tmp_path / "state"
    state.mkdir()
    session = {
        "session_type": "variants", "selection_status": "selected",
        "selected_task_id": "v1", "tasks": [{
            "task_id": "v1", "status": "completed", "branch": "crew/v1",
            "project_root": str(worktree), "base_project_root": str(base),
        }],
    }
    (state / "session.json").write_text(json.dumps(session))
    return base, worktree, state, session


def apply(state, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "apply", "--state-dir", str(state), *args],
        text=True, capture_output=True,
    )


def snapshot(base, worktree, state):
    # 내용 비교로 refs, index, 객체, 세션 및 사용자 파일의 변이를 함께 잡는다.
    return {
        str(path): path.read_bytes()
        for root in (base, worktree, state)
        for path in root.rglob("*") if path.is_file()
    }


@pytest.mark.parametrize("conflict", [False, True])
def test_dry_run_reports_merge_result_without_mutating_repository(candidate, conflict):
    base, worktree, state, _ = candidate
    if conflict:
        (base / "shared.txt").write_text("target\n")
        git(base, "commit", "-am", "target")
    before = snapshot(base, worktree, state)

    result = apply(state, "--target", "main", "--dry-run")

    assert result.returncode == (1 if conflict else 0), result.stderr
    assert f"merge_status: {'conflict' if conflict else 'clean'}" in result.stdout
    assert "target_branch: main" in result.stdout
    assert "shared.txt" in result.stdout
    assert git(base, "rev-parse", "main") in result.stdout
    assert git(base, "rev-parse", "crew/v1") in result.stdout
    assert snapshot(base, worktree, state) == before


@pytest.mark.parametrize("problem", ["missing-target", "shared", "wrong-branch", "foreign", "dirty", "running", "unselected"])
def test_dry_run_rejects_invalid_candidate(candidate, problem, tmp_path):
    base, worktree, state, session = candidate
    task = session["tasks"][0]
    target = "main"
    expected = {
        "missing-target": "대상 브랜치", "shared": "독립 worktree",
        "wrong-branch": "후보 브랜치", "foreign": "동일한 저장소",
        "dirty": "미커밋", "running": "completed", "unselected": "No selected variant",
    }[problem]
    if problem == "missing-target":
        target = "missing"
    elif problem == "shared":
        task["project_root"] = str(base)
    elif problem == "wrong-branch":
        task["branch"] = "main"
    elif problem == "foreign":
        other = tmp_path / "other"
        other.mkdir()
        git(other, "init")
        task["project_root"] = str(other)
    elif problem == "dirty":
        (worktree / "untracked.txt").write_text("pending")
    elif problem == "running":
        task["status"] = "running"
    else:
        session["selection_status"] = "pending"
    (state / "session.json").write_text(json.dumps(session))
    before = snapshot(base, worktree, state)

    result = apply(state, "--target", target, "--dry-run")

    assert result.returncode == 2
    assert expected in result.stdout + result.stderr
    assert snapshot(base, worktree, state) == before


@pytest.mark.parametrize("args", [("--target", "main"), ("--dry-run",)])
def test_dry_run_requires_target_and_mode_together(candidate, args):
    result = apply(candidate[2], *args)

    assert result.returncode == 2
    assert "--target" in result.stderr and "--dry-run" in result.stderr


def test_native_cli_forwards_dry_run_options(candidate, tmp_path):
    base, _, state, _ = candidate
    home = tmp_path / "crew-home"
    legacy = home / "state" / base.name
    legacy.mkdir(parents=True)
    (legacy / "session.json").write_bytes((state / "session.json").read_bytes())

    result = subprocess.run(
        ["bash", str(ROOT / "core/bin/crew"), "variants", "apply", "--target", "main", "--dry-run"],
        cwd=base, env={**os.environ, "AGENT_CREW_HOME": str(home), "PROJECT_ROOT": str(base)},
        text=True, capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "merge_status: clean" in result.stdout


def test_dry_run_does_not_execute_custom_merge_driver(candidate):
    base, worktree, state, _ = candidate
    git(base, "config", "merge.custom.driver", "touch unexpected-driver-output")
    before = snapshot(base, worktree, state)

    result = apply(state, "--target", "main", "--dry-run")

    assert result.returncode == 2
    assert "merge driver" in result.stdout
    assert snapshot(base, worktree, state) == before


def plan_hash(state):
    result = apply(state, "--target", "main", "--dry-run")
    assert result.returncode in (0, 1), result.stdout + result.stderr
    hashes = [line.split(": ", 1)[1] for line in result.stdout.splitlines()
              if line.startswith("plan_hash: ")]
    assert len(hashes) == 1, result.stdout
    return hashes[0]


@pytest.mark.parametrize("diverged", [False, True])
def test_confirm_merges_selected_commit_and_records_receipt(candidate, diverged):
    base, worktree, state, _ = candidate
    if diverged:
        (base / "target.txt").write_text("keep target work\n")
        git(base, "add", ".")
        git(base, "commit", "-m", "target change")
    target_sha = git(base, "rev-parse", "HEAD")
    candidate_sha = git(worktree, "rev-parse", "HEAD")
    approved = plan_hash(state)

    result = apply(state, "--target", "main", "--confirm", approved)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "apply_status: applied" in result.stdout
    assert (base / "shared.txt").read_text() == "candidate\n"
    assert git(base, "show", "-s", "--format=%P", "HEAD").split() == [target_sha, candidate_sha]
    assert git(worktree, "rev-parse", "HEAD") == candidate_sha
    if diverged:
        assert (base / "target.txt").read_text() == "keep target work\n"
    session = json.loads((state / "session.json").read_text())
    assert session["apply_status"] == "applied"
    assert session["applied_branch"] == "main"
    assert session["applied_task_id"] == "v1"
    assert session["applied_at"]
    assert session["apply_record"]["plan_hash"] == approved
    assert session["apply_record"]["applied_commit"] == git(base, "rev-parse", "HEAD")

    before = snapshot(base, worktree, state)
    retry = apply(state, "--target", "main", "--confirm", approved)
    assert retry.returncode == 0, retry.stdout + retry.stderr
    assert "already_applied" in retry.stdout
    assert snapshot(base, worktree, state) == before


@pytest.mark.parametrize("changed", ["candidate", "target", "selection", "token", "config", "hook"])
def test_confirm_rejects_stale_or_wrong_plan_without_mutation(candidate, changed):
    base, worktree, state, session = candidate
    approved = plan_hash(state)
    if changed in ("candidate", "target"):
        git(worktree if changed == "candidate" else base, "commit", "--allow-empty", "-m", "changed")
    elif changed == "selection":
        session["tasks"][0]["task_id"] = "v2"
        session["selected_task_id"] = "v2"
        (state / "session.json").write_text(json.dumps(session))
    elif changed == "config":
        git(base, "config", "merge.renames", "false")
    elif changed == "hook":
        hook = base / ".git/hooks/pre-merge-commit"
        hook.write_text("#!/bin/sh\nexit 0\n")
        hook.chmod(0o755)
    else:
        approved = "0" * 64
    before = snapshot(base, worktree, state)

    result = apply(state, "--target", "main", "--confirm", approved)

    assert result.returncode == 2
    assert "plan_hash" in result.stdout
    assert snapshot(base, worktree, state) == before


def test_confirm_conflict_does_not_start_merge(candidate):
    base, worktree, state, _ = candidate
    (base / "shared.txt").write_text("target conflict\n")
    git(base, "commit", "-am", "conflicting target")
    approved = plan_hash(state)
    before = snapshot(base, worktree, state)

    result = apply(state, "--target", "main", "--confirm", approved)

    assert result.returncode == 1
    assert "merge_status: conflict" in result.stdout
    assert snapshot(base, worktree, state) == before


def test_confirm_requires_target_checked_out_in_original_worktree(candidate):
    base, worktree, state, _ = candidate
    git(base, "switch", "-c", "other")
    approved = plan_hash(state)
    before = snapshot(base, worktree, state)

    result = apply(state, "--target", "main", "--confirm", approved)

    assert result.returncode == 2
    assert "checkout" in result.stdout
    assert snapshot(base, worktree, state) == before


def test_failed_merge_is_recorded_and_retry_does_not_restart_it(candidate):
    base, worktree, state, _ = candidate
    hook = base / ".git/hooks/pre-merge-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    approved = plan_hash(state)
    target_sha = git(base, "rev-parse", "HEAD")

    result = apply(state, "--target", "main", "--confirm", approved)

    assert result.returncode == 2, result.stdout + result.stderr
    session = json.loads((state / "session.json").read_text())
    assert session["apply_status"] == "failed"
    assert session["apply_record"]["error"]
    assert git(base, "rev-parse", "HEAD") == target_sha
    assert (base / ".git/MERGE_HEAD").exists()
    before = snapshot(base, worktree, state)
    retry = apply(state, "--target", "main", "--confirm", approved)
    assert retry.returncode == 2
    assert "복구" in retry.stdout
    assert snapshot(base, worktree, state) == before

    git(base, "merge", "--abort")
    hook.unlink()
    fresh_plan = plan_hash(state)
    recovered = apply(state, "--target", "main", "--confirm", fresh_plan)
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    receipt = json.loads((state / "session.json").read_text())
    assert receipt["apply_status"] == "applied"
    assert receipt["apply_history"][0]["status"] == "failed"
    assert receipt["apply_history"][0]["plan_hash"] == approved


def test_confirm_respects_repository_operation_lock(candidate):
    base, worktree, state, _ = candidate
    approved = plan_hash(state)
    lock = base / ".git/crew-variants-apply.lock"
    lock.mkdir()
    before = snapshot(base, worktree, state)

    result = apply(state, "--target", "main", "--confirm", approved)

    assert result.returncode == 2
    assert "잠금" in result.stdout
    assert lock.is_dir()
    assert snapshot(base, worktree, state) == before


def test_native_cli_accepts_approved_plan(candidate, tmp_path):
    base, _, state, _ = candidate
    home = tmp_path / "crew-home"
    legacy = home / "state" / base.name
    legacy.mkdir(parents=True)
    (legacy / "session.json").write_bytes((state / "session.json").read_bytes())
    approved = plan_hash(legacy)

    result = subprocess.run(
        ["bash", str(ROOT / "core/bin/crew"), "variants", "apply", "--target", "main", "--confirm", approved],
        cwd=base, env={**os.environ, "AGENT_CREW_HOME": str(home), "PROJECT_ROOT": str(base)},
        text=True, capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "apply_status: applied" in result.stdout
    assert (base / "shared.txt").read_text() == "candidate\n"


@pytest.mark.parametrize("args", [("--confirm",), ("--target", "main", "--confirm"),
                                  ("--target", "main", "--dry-run", "--confirm", "abc")])
def test_confirm_requires_one_explicit_mode_and_plan_hash(candidate, args):
    assert apply(candidate[2], *args).returncode == 2


def test_native_run_guides_candidate_collection_to_variants_command(candidate, tmp_path):
    base, _, _, _ = candidate
    result = subprocess.run(
        ["bash", str(ROOT / "core/bin/crew"), "run", "--variants", "3", "compare candidates"],
        cwd=base, env={**os.environ, "AGENT_CREW_HOME": str(tmp_path / "crew-home"),
                       "PROJECT_ROOT": str(base), "AGENT_CREW_AUTO_SYNC_RUNTIME_ON_RUN": "0",
                       "AGENT_CREW_AUTO_SYNC_HOOKS_ON_RUN": "0"},
        text=True, capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "crew variants collect" in result.stdout
    assert "crew status --collect" not in result.stdout
