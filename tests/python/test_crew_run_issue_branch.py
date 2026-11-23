"""Contract for the native issue-plus-work-branch entry."""

import json
import os
import subprocess
from pathlib import Path

import pytest


CREW = Path(__file__).resolve().parents[2] / "core" / "bin" / "crew"


def git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check, capture_output=True, text=True,
    )


@pytest.fixture
def repository(tmp_path, monkeypatch):
    home = tmp_path / "crew-home"
    repo = tmp_path / "checkout"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Crew Test")
    git(repo, "config", "user.email", "crew@example.invalid")
    git(repo, "config", "branch.autoSetupMerge", "always")
    git(repo, "commit", "--allow-empty", "-m", "initial")
    git(repo, "commit", "--allow-empty", "-m", "latest")

    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    git(repo, "remote", "add", "origin", str(origin))
    monkeypatch.setenv("AGENT_CREW_HOME", str(home))
    monkeypatch.setenv("AGENT_CREW_RUNTIME_DRIFT_CHECK_ON_RUN", "0")
    monkeypatch.setenv("AGENT_CREW_HOST", "codex")
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    monkeypatch.delenv("AGENT_CREW_HOST_BRIDGE_COMMAND", raising=False)
    return repo, origin, home


def run_crew(repo, *args):
    return subprocess.run(
        [str(CREW), "run", *args], cwd=repo, capture_output=True, text=True, timeout=60,
    )


def register_path(home):
    paths = list(home.glob("state/*/tasks/*/register.json"))
    assert len(paths) == 1, paths
    return paths[0]


def install_issue_probe(tmp_path, monkeypatch, home):
    probe = tmp_path / "issue-probe.json"
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        """#!/usr/bin/env python3
import json, os, subprocess
from pathlib import Path
data = {
    'path': str(Path.cwd().resolve()),
    'branch': subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
    'head': subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    'registered_branch': json.loads(next(Path(os.environ['AGENT_CREW_HOME']).glob(
        'state/*/tasks/*/register.json')).read_text())['branch'],
}
Path(os.environ['CREW_TEST_ISSUE_PROBE']).write_text(json.dumps(data))
print(json.dumps({'number': 421, 'title': 'fixture', 'comments': []}))
""",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    monkeypatch.setenv("CREW_TEST_ISSUE_PROBE", str(probe))
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    return probe


@pytest.mark.parametrize("linked", [False, True], ids=["checkout", "detached-linked-worktree"])
def test_issue_branch_is_verified_before_ingestion_and_first_push_tracks_same_name(
    linked, repository, tmp_path, monkeypatch,
):
    repo, origin, home = repository
    main_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    target = repo
    if linked:
        target = tmp_path / "linked"
        git(repo, "worktree", "add", "--detach", str(target), "HEAD^")
    initial_head = git(target, "rev-parse", "HEAD").stdout.strip()
    initial_paths = [
        line for line in git(repo, "worktree", "list", "--porcelain").stdout.splitlines()
        if line.startswith("worktree ")
    ]
    probe = install_issue_probe(tmp_path, monkeypatch, home)
    raw = "#421   feat/ENRBE-421" if linked else "#421 feat/ENRBE-421"
    argv = ["--", raw] if linked else ["#421", "feat/ENRBE-421"]

    result = run_crew(target, *argv)

    assert result.returncode == 0, result.stderr or result.stdout
    assert git(target, "branch", "--show-current").stdout.strip() == "feat/ENRBE-421"
    assert git(target, "rev-parse", "HEAD").stdout.strip() == initial_head
    assert git(target, "for-each-ref", "--format=%(upstream:short)", "refs/heads/feat/ENRBE-421").stdout.strip() == ""
    assert git(repo, "rev-parse", "refs/heads/main").stdout.strip() == main_head
    assert [
        line for line in git(repo, "worktree", "list", "--porcelain").stdout.splitlines()
        if line.startswith("worktree ")
    ] == initial_paths
    assert json.loads(probe.read_text()) == {
        "path": str(target.resolve()), "branch": "feat/ENRBE-421",
        "head": initial_head, "registered_branch": "feat/ENRBE-421",
    }
    register = register_path(home)
    assert json.loads(register.read_text())["task"] == raw
    assert json.loads(register.read_text())["project_root"] == str(target.resolve())
    assert f"TASK: {raw}\n" in (register.parent / "handoff.md").read_text()
    assert git(origin, "for-each-ref", "refs/heads").stdout == ""

    git(target, "push", "-u", "origin", "feat/ENRBE-421")

    assert git(origin, "rev-parse", "refs/heads/feat/ENRBE-421").stdout.strip() == initial_head
    assert git(target, "rev-parse", "--abbrev-ref", "@{upstream}").stdout.strip() == "origin/feat/ENRBE-421"


def test_plane_style_issue_key_uses_the_explicit_branch(repository):
    repo, _, home = repository

    result = run_crew(repo, "ENRBE-421 feat/ENRBE-421")

    assert result.returncode == 0, result.stderr or result.stdout
    assert git(repo, "branch", "--show-current").stdout.strip() == "feat/ENRBE-421"
    assert json.loads(register_path(home).read_text())["task"] == "ENRBE-421 feat/ENRBE-421"


def test_failed_checkout_does_not_ingest_issue_or_start_handoff(repository, tmp_path, monkeypatch):
    repo, origin, home = repository
    git(repo, "branch", "feat/already-exists")
    probe = install_issue_probe(tmp_path, monkeypatch, home)

    result = run_crew(repo, "#421 feat/already-exists")

    assert result.returncode != 0
    assert "STATUS: handoff_ready" not in result.stdout
    assert git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert not probe.exists()
    assert not list(home.glob("state/*/tasks/*/register.json"))
    assert git(origin, "for-each-ref", "refs/heads").stdout == ""


@pytest.mark.parametrize("raw", ["#421", "ENRBE-421 검토", "일반 작업 설명"])
def test_issue_only_and_task_descriptions_keep_existing_flow(raw, repository, tmp_path, monkeypatch):
    repo, _, home = repository
    install_issue_probe(tmp_path, monkeypatch, home)

    result = run_crew(repo, raw)

    assert result.returncode == 0, result.stderr or result.stdout
    assert git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert json.loads(register_path(home).read_text())["task"] == raw


@pytest.mark.parametrize("options", [("--read-only",), ("--variants", "2")])
def test_explicit_branch_conflicts_are_rejected_before_checkout(options, repository):
    repo, _, home = repository

    result = run_crew(repo, *options, "ENRBE-421 feat/rejected")

    assert result.returncode != 0
    assert git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert not list(home.glob("state/*/tasks/*/register.json"))


def test_invalid_explicit_branch_does_not_start_a_handoff(repository):
    repo, _, home = repository

    result = run_crew(repo, "ENRBE-421", "feat/invalid..name")

    assert result.returncode != 0
    assert git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert not list(home.glob("state/*/tasks/*/register.json"))


def test_branch_verification_failure_does_not_start_a_handoff(repository, tmp_path, monkeypatch):
    repo, _, home = repository
    probe = install_issue_probe(tmp_path, monkeypatch, home)
    hooks = repo / ".git" / "hooks"
    git(repo, "config", "core.hooksPath", str(hooks))
    hook = hooks / "post-checkout"
    hook.write_text("#!/bin/sh\ngit symbolic-ref HEAD refs/heads/main\n", encoding="utf-8")
    hook.chmod(0o755)

    result = run_crew(repo, "#421 feat/not-active")

    assert result.returncode != 0
    assert git(repo, "branch", "--show-current").stdout.strip() == "main"
    assert not probe.exists()
    assert not list(home.glob("state/*/tasks/*/register.json"))


def test_separate_arguments_accept_an_unqualified_branch(repository):
    repo, _, home = repository

    result = run_crew(repo, "ENRBE-421", "topic")

    assert result.returncode == 0, result.stderr or result.stdout
    assert git(repo, "branch", "--show-current").stdout.strip() == "topic"
    register = json.loads(register_path(home).read_text())
    assert register["task"] == "ENRBE-421 topic"
    assert register["issue_ref"] == "ENRBE-421"
