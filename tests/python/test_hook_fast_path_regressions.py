"""Behavioral regressions for optimized PostToolUse hook paths."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_approval_module():
    path = REPO_ROOT / "core/scripts/check-plaintext-approval.py"
    spec = importlib.util.spec_from_file_location("check_plaintext_approval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mixed_language_korean_approval_prompt_is_rejected():
    module = load_approval_module()

    assert module.find_violation("merge 할까요?") is not None
    assert module.find_violation("git push 할까요?") is not None


def test_supervisor_guard_ignores_stale_legacy_state_when_keyed_state_exists(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)

    slug = project.name
    digest = hashlib.sha256(str(project.resolve()).encode("utf-8")).hexdigest()[:10]
    keyed = home / "state" / f"{slug}-{digest}"
    keyed.mkdir(parents=True)

    legacy_task = home / "state" / project.name / "tasks" / "stale"
    legacy_task.mkdir(parents=True)
    (legacy_task.parent / "active.stale").touch()
    (legacy_task / "progress.log").write_text(
        "2026-01-01T00:00:00Z | STAGE_DONE | backend - APPROVED\n",
        encoding="utf-8",
    )

    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"cwd": str(project), "command": "true"}}
    )
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "core/hooks/supervisor-progress-guard.sh")],
        input=payload,
        text=True,
        capture_output=True,
        env={"AGENT_CREW_HOME": str(home), "PATH": "/usr/bin:/bin"},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (legacy_task / "result.violation.md").exists()
