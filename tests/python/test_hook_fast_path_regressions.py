"""Behavioral regressions for optimized PostToolUse hook paths."""

import hashlib
import importlib.util
import json
import os
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


def test_auto_issue_hook_fast_rejects_generic_agent_crew_state_paths(tmp_path):
    home = tmp_path / "home"
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True)
    crew_log = tmp_path / "crew.log"
    crew = bin_dir / "crew"
    crew.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{crew_log}'\n"
        "cat >/dev/null\n"
        "exit 0\n",
        encoding="utf-8",
    )
    crew.chmod(0o755)

    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": (
                "sed -n '1,80p' "
                "/Users/wook/.agent-crew/state/agent-crew-9608d22982/tasks/demo/handoff.md"
            )
        },
        "tool_response": {"stdout": "# Supervisor Handoff\nSTATUS: handoff_ready\n"},
    }
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "core/hooks/auto-issue-report.sh")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={
            "AGENT_CREW_HOME": str(home),
            "HOME": str(tmp_path),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert not crew_log.exists()


def test_auto_issue_hook_fast_rejects_unrelated_error_output(tmp_path):
    home = tmp_path / "home"
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True)
    crew_log = tmp_path / "crew.log"
    crew = bin_dir / "crew"
    crew.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{crew_log}'\n"
        "cat >/dev/null\n"
        "exit 0\n",
        encoding="utf-8",
    )
    crew.chmod(0o755)

    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "grep error build.log"},
        "tool_response": {
            "stderr": "error: unrelated build failure\n",
            "returncode": 1,
        },
    }
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "core/hooks/auto-issue-report.sh")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={
            "AGENT_CREW_HOME": str(home),
            "HOME": str(tmp_path),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
    assert not crew_log.exists()


def test_supervisor_guard_fast_rejects_unrelated_payload_before_python(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python3 = fake_bin / "python3"
    python3.write_text(
        "#!/usr/bin/env bash\nprintf 'python should not run\\n' >&2\nexit 97\n",
        encoding="utf-8",
    )
    python3.chmod(0o755)

    payload = json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
            "tool_response": {"stdout": "/tmp\n", "returncode": 0},
        }
    )
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "core/hooks/supervisor-progress-guard.sh")],
        input=payload,
        text=True,
        capture_output=True,
        env={
            "AGENT_CREW_HOME": str(tmp_path / "home"),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_supervisor_guard_ignores_active_markers_from_other_projects_before_python(tmp_path):
    home = tmp_path / "home"
    other_task = home / "state" / "other-project" / "tasks" / "stale"
    other_task.mkdir(parents=True)
    (other_task.parent / "active.stale").touch()

    project = tmp_path / "current-project"
    (project / ".git").mkdir(parents=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    python3 = fake_bin / "python3"
    python3.write_text(
        "#!/usr/bin/env bash\nprintf 'python should not run\\n' >&2\nexit 97\n",
        encoding="utf-8",
    )
    python3.chmod(0o755)

    payload = json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"cwd": str(project), "command": "pwd"},
            "tool_response": {"stdout": str(project), "returncode": 0},
        }
    )
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "core/hooks/supervisor-progress-guard.sh")],
        input=payload,
        text=True,
        capture_output=True,
        env={
            "AGENT_CREW_HOME": str(home),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""
