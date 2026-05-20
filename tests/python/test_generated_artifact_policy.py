"""Repository policy checks for generated agent-crew artifacts."""
from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def git_check_ignore(path: str) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO_ROOT,
        text=True,
    )
    return proc.returncode == 0


def test_generated_project_artifacts_are_ignored():
    for path in (
        ".agent-crew/state/example.json",
        ".codex/agents/example.toml",
        ".claude/settings.local.json",
        ".crew-worktrees/task-001/file.txt",
        ".crew_task_id",
    ):
        assert git_check_ignore(path), f"{path} must remain untracked generated output"


def test_readme_documents_generated_artifact_policy():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Host-generated project artifacts" in text
    assert "should remain uncommitted" in text
    assert "registered in `.git/info/exclude` during setup" in text
