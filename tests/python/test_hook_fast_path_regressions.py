"""Behavioral regressions for optimized PostToolUse hook paths."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]


def keyed_state_dir(home: Path, project: Path) -> Path:
    slug = project.name.lower()
    digest = hashlib.sha256(str(project.resolve()).encode("utf-8")).hexdigest()[:10]
    return home / "state" / f"{slug}-{digest}"


def write_active_task(home: Path, project: Path, task_id: str = "20260721-000000-0") -> Path:
    state_dir = keyed_state_dir(home, project)
    task_dir = state_dir / "tasks" / task_id
    task_dir.mkdir(parents=True)
    (state_dir / "tasks" / f"active.{task_id}").write_text("", encoding="utf-8")
    return task_dir


def load_approval_module():
    path = REPO_ROOT / "core/scripts/check-plaintext-approval.py"
    spec = importlib.util.spec_from_file_location("check_plaintext_approval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_hook_with_open_stdin(script: Path, payload: dict, *, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(
        ["bash", str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env or os.environ.copy(),
    )
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload))
    proc.stdin.flush()

    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=1)
        raise AssertionError(f"{script.name} waited for stdin EOF; stdout={stdout!r} stderr={stderr!r}")
    finally:
        proc.stdin.close()

    stdout = proc.stdout.read() if proc.stdout is not None else ""
    stderr = proc.stderr.read() if proc.stderr is not None else ""

    return subprocess.CompletedProcess(
        args=["bash", str(script)],
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_guard_dangerous_commands_does_not_wait_for_stdin_eof() -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "sed -n '1,230p' core/audit.py"},
    }

    result = run_hook_with_open_stdin(REPO_ROOT / "core/hooks/guard-dangerous-commands.sh", payload)

    assert result.returncode == 0, result.stderr


def test_guard_dangerous_commands_records_timing_events_with_open_stdin(tmp_path) -> None:
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "sed -n '1,230p' core/audit.py"},
    }
    timing_log = tmp_path / "hook-timings.jsonl"
    env = os.environ.copy()
    env["AGENT_CREW_HOOK_TIMING_LOG"] = str(timing_log)

    result = run_hook_with_open_stdin(
        REPO_ROOT / "core/hooks/guard-dangerous-commands.sh",
        payload,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    rows = [
        json.loads(line)
        for line in timing_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["event"] for row in rows] == ["start", "finish"]
    assert {row["hook"] for row in rows} == {"guard-dangerous-commands"}
    assert rows[1]["elapsed_seconds"] >= 0


def test_post_tool_use_dispatcher_does_not_wait_for_stdin_eof(tmp_path) -> None:
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"cwd": str(tmp_path), "command": "pwd"},
        "tool_response": {"returncode": 0, "stdout": str(tmp_path)},
    }
    env = os.environ.copy()
    env["AGENT_CREW_HOME"] = str(REPO_ROOT / "core")
    payload_root = tmp_path / "payloads"
    env["AGENT_CREW_HOOK_PAYLOAD_DIR"] = str(payload_root)

    result = run_hook_with_open_stdin(
        REPO_ROOT / "core/hooks/post-tool-use-dispatcher.sh",
        payload,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert list(payload_root.glob("*/posttooluse-*.json"))


def test_post_tool_use_dispatcher_records_timing_events_with_open_stdin(tmp_path) -> None:
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"cwd": str(tmp_path), "command": "pwd"},
        "tool_response": {"returncode": 0, "stdout": str(tmp_path)},
    }
    env = os.environ.copy()
    env["AGENT_CREW_HOME"] = str(REPO_ROOT / "core")
    payload_root = tmp_path / "payloads"
    env["AGENT_CREW_HOOK_PAYLOAD_DIR"] = str(payload_root)
    timing_log = tmp_path / "hook-timings.jsonl"
    env["AGENT_CREW_HOOK_TIMING_LOG"] = str(timing_log)

    result = run_hook_with_open_stdin(
        REPO_ROOT / "core/hooks/post-tool-use-dispatcher.sh",
        payload,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    rows = [
        json.loads(line)
        for line in timing_log.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["event"] for row in rows] == ["start", "finish"]
    assert {row["hook"] for row in rows} == {"post-tool-use-dispatcher"}
    assert rows[1]["elapsed_seconds"] >= 0


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


def test_auto_issue_hook_reports_matching_user_prompt_without_blocking(tmp_path):
    home = tmp_path / "home"
    bin_dir = home / "bin"
    bin_dir.mkdir(parents=True)
    crew_started = tmp_path / "crew.started"
    crew_finished = tmp_path / "crew.finished"
    crew = bin_dir / "crew"
    crew.write_text(
        "#!/usr/bin/env bash\n"
        f"touch '{crew_started}'\n"
        "cat >/dev/null\n"
        "sleep 10\n"
        f"touch '{crew_finished}'\n",
        encoding="utf-8",
    )
    crew.chmod(0o755)

    payload = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "agent-crew hook timed out with traceback",
    }
    started = time.perf_counter()
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
        timeout=5,
        check=False,
    )
    elapsed = time.perf_counter() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 5
    for _ in range(60):
        if crew_started.exists():
            break
        time.sleep(0.05)
    assert crew_started.exists()
    assert not crew_finished.exists()


def test_auto_route_does_not_run_hidden_bridge_status_router():
    text = (REPO_ROOT / "core/hooks/auto-route.sh").read_text(encoding="utf-8")

    assert "HOST_BRIDGE_READY, HOST_BRIDGE_REASON = _bridge_status()" not in text
    assert "_bridge_status()" not in text
    assert "COMMAND_PAT" in text
    assert "explicit {command} invocation detected" in text


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


def test_post_tool_use_dispatcher_spools_large_payload_without_truncation(tmp_path):
    home = tmp_path / "home"
    child_log = tmp_path / "child.log"
    child = tmp_path / "child-hook.sh"
    child.write_text(
        "#!/usr/bin/env bash\n"
        "payload=$(cat)\n"
        "python3 - \"$1\" \"$payload\" <<'PY'\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        "payload = sys.argv[2]\n"
        "data = json.loads(payload)\n"
        "assert data['agent_crew_hook_envelope'] == 1\n"
        "assert 'xxxxxxxxxx' not in payload\n"
        "Path(sys.argv[1]).write_text(json.dumps({\n"
        "    'payload_path': data['payload_path'],\n"
        "    'payload_sha256': data['payload_sha256'],\n"
        "    'payload_bytes': data['payload_bytes'],\n"
        "    'tool_name': data['tool_name'],\n"
        "    'command': data['command'],\n"
        "    'envelope_bytes': len(payload),\n"
        "}), encoding='utf-8')\n"
        "PY\n",
        encoding="utf-8",
    )
    child.chmod(0o755)

    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "cwd": str(tmp_path),
            "command": "python3 -c 'print large output'",
        },
        "tool_response": {
            "stdout": "x" * 20_000_000,
            "stderr": "",
            "returncode": 0,
        },
    }
    raw = json.dumps(payload)
    expected_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    started = time.perf_counter()

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "core/hooks/post-tool-use-dispatcher.sh")],
        input=raw,
        text=True,
        capture_output=True,
        env={
            "AGENT_CREW_HOME": str(home),
            "AGENT_CREW_POST_TOOL_USE_CHILDREN": f"*:bash {child} {child_log}",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        },
        timeout=15,
        check=False,
    )

    elapsed = time.perf_counter() - started
    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed < 15
    record = json.loads(child_log.read_text(encoding="utf-8"))
    payload_path = Path(record["payload_path"])
    assert payload_path.is_file()
    assert record["payload_sha256"] == ""
    assert record["payload_bytes"] == len(raw.encode("utf-8"))
    assert record["tool_name"] == "Bash"
    assert record["command"] == payload["tool_input"]["command"]
    assert record["envelope_bytes"] < 4096
    assert hashlib.sha256(payload_path.read_bytes()).hexdigest() == expected_hash


def test_post_tool_use_dispatcher_preserves_korean_auto_issue_signal_parity(tmp_path):
    home = tmp_path / "home"
    child_log = tmp_path / "child.log"
    child = tmp_path / "child-hook.sh"
    child.write_text(
        "#!/usr/bin/env bash\n"
        "payload=$(cat)\n"
        "python3 - \"$1\" \"$payload\" <<'PY'\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        "data = json.loads(sys.argv[2])\n"
        "Path(sys.argv[1]).write_text(json.dumps({\n"
        "    'contains_auto_issue_signal': data['contains_auto_issue_signal'],\n"
        "    'payload_path': data['payload_path'],\n"
        "}), encoding='utf-8')\n"
        "PY\n",
        encoding="utf-8",
    )
    child.chmod(0o755)

    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"cwd": str(tmp_path), "command": "echo ok"},
        "tool_response": {
            "stdout": "에이전트크루 오류 발생\n",
            "stderr": "",
            "returncode": 0,
        },
    }

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "core/hooks/post-tool-use-dispatcher.sh")],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        env={
            "AGENT_CREW_HOME": str(home),
            "AGENT_CREW_POST_TOOL_USE_CHILDREN": f"Bash:bash {child} {child_log}",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        },
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(child_log.read_text(encoding="utf-8"))
    assert record["contains_auto_issue_signal"] is True
    assert Path(record["payload_path"]).is_file()


def test_post_tool_use_dispatcher_skips_default_async_children_without_signals(tmp_path):
    home = tmp_path / "home"
    hook_dir = home / "hooks"
    hook_dir.mkdir(parents=True)
    for name in ("auto-issue-report.sh", "mnemos-capture-guard.sh"):
        hook = hook_dir / name
        hook.write_text(
            "#!/usr/bin/env bash\n"
            "cat >/dev/null\n"
            f"touch '{tmp_path / (name + '.called')}'\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)

    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"cwd": str(tmp_path), "command": "echo ok"},
        "tool_response": {"stdout": "plain output", "stderr": "", "returncode": 0},
    }

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "core/hooks/post-tool-use-dispatcher.sh")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={
            "AGENT_CREW_HOME": str(home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        },
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (tmp_path / "auto-issue-report.sh.called").exists()
    assert not (tmp_path / "mnemos-capture-guard.sh.called").exists()
    assert not (home / "state/hook-payloads/.async").exists()


def test_post_tool_use_dispatcher_records_bash_tool_event_without_child_recorder(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    task_dir = write_active_task(home, project)
    payload = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "cwd": str(project),
            "command": "pytest tests/python/test_hook_fast_path_regressions.py -q",
        },
        "tool_response": {"returncode": 0},
    }

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "core/hooks/post-tool-use-dispatcher.sh")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={
            "AGENT_CREW_HOME": str(home),
            "AGENT_CREW_POST_TOOL_USE_CHILDREN": "",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        },
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    rows = [
        json.loads(line)
        for line in (task_dir / "tool-events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["tool_name"] == "Bash"
    assert rows[0]["action_summary"] == payload["tool_input"]["command"]
    assert rows[0]["exit_code"] == 0


def test_post_tool_use_dispatcher_keeps_bash_sync_path_internal():
    shell_text = (REPO_ROOT / "core/hooks/post-tool-use-dispatcher.sh").read_text(
        encoding="utf-8"
    )
    python_text = (REPO_ROOT / "core/scripts/post-tool-use-dispatcher.py").read_text(
        encoding="utf-8"
    )

    assert "record_bash_tool_event" in python_text
    assert "check_supervisor_progress" in python_text
    assert "Bash:bash '${AGENT_CREW_HOME}/hooks/tool-event-recorder.sh'" not in shell_text
    assert "Bash:bash '${AGENT_CREW_HOME}/hooks/supervisor-progress-guard.sh'" not in shell_text
