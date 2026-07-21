"""Focused coverage for crew-runtime.py fallback and error paths."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUNTIME = REPO_ROOT / "core" / "scripts" / "crew-runtime.py"
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load_module(RUNTIME, "crew_runtime_coverage")


def _register(task_id: str = "20260101-120000-0") -> dict:
    return {"task_id": task_id, "session_id": "20260101-120000", "task": "runtime task", "branch": "crew/runtime"}


def _agent_args(root: Path, *agent_args: str, list_: bool = False, routing: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        asset_root=str(root),
        agent_args=list(agent_args),
        list=list_,
        routing=routing,
        project_root=str(root / "project"),
        host_bridge_command=None,
    )


def _write_registry(root: Path) -> None:
    rules = root / "rules"
    rules.mkdir(parents=True)
    (rules / "agent-routing.md").write_text(
        "\n".join([
            "## Agent Registry",
            "| Agent | Scope | Keywords | Safe | Reason |",
            "| --- | --- | --- | --- | --- |",
            "| analyst | Read-only analysis | explain | yes | — |",
            "| unsafe | Mutating work | deploy | no | requires supervisor context |",
            "| short | Bad row |",
            "",
            "## Auto-Routing Rules",
            "| Order | Signal | Keywords | Agent |",
            "| --- | --- | --- | --- |",
            "| 1 | Analysis | explain | analyst |",
            "### Matching semantics",
        ]),
        encoding="utf-8",
    )


def test_basic_helpers_cover_fallbacks(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *_args, **_kwargs: str(tmp_path))
    assert runtime.git_root() == tmp_path.resolve()

    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("no git")))
    assert runtime.git_root() == Path.cwd().resolve()

    missing = tmp_path / "missing.txt"
    assert runtime.load_text(missing) == ""

    for name in ("AGENT_CREW_AGENT_UUID", "AGENT_CREW_HOST_AGENT_UUID", "CODEX_THREAD_ID", "CODEX_SESSION_ID"):
        monkeypatch.delenv(name, raising=False)
    assert runtime.agent_uuid_for_display() == "unavailable"

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    assert runtime.latest_progress_event(task_dir)["detail"] == "no progress events yet"
    (task_dir / "progress.buffer.jsonl").write_text("{bad json\n", encoding="utf-8")
    (task_dir / "progress.log").write_text("2026-01-01T00:00:00Z | LOG | detail\nraw line\n", encoding="utf-8")
    assert runtime.latest_progress_event(task_dir)["detail"] == "raw line"
    (task_dir / "progress.log").write_text("2026-01-01T00:00:00Z | LOG | detail\n", encoding="utf-8")
    assert runtime.latest_progress_event(task_dir)["event"] == "LOG"

    assert runtime.progress_age_seconds({}) is None
    assert runtime.progress_age_seconds({"ts": "not-a-date"}) is None
    long_detail = "x" * 140
    (task_dir / "progress.buffer.jsonl").write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "event": "WAIT", "agent": "", "stage": 2, "detail": long_detail}),
        encoding="utf-8",
    )
    wait = runtime.render_wait_progress(
        {"task_id": "task-1"},
        task_dir,
    )
    assert "task_id=task-1" in wait
    assert "..." in wait


def test_host_bridge_start_failure_and_timeout_paths(monkeypatch, tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    register = _register(task_dir.name)
    monkeypatch.setenv("AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS", "bad")
    monkeypatch.setenv("AGENT_CREW_BRIDGE_TIMEOUT_SECONDS", "bad")

    def raise_popen(*_args, **_kwargs):
        raise RuntimeError("cannot start")

    monkeypatch.setattr(runtime.subprocess, "Popen", raise_popen)
    failed = runtime.invoke_host_bridge(
        "bridge-command",
        task_dir=task_dir,
        register=register,
        project_root=tmp_path,
    )
    assert failed["returncode"] == 127
    assert failed["failure_class"] == "host_bridge_start_failed"

    monkeypatch.undo()
    monkeypatch.setenv("AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS", "0.001")
    monkeypatch.setenv("AGENT_CREW_BRIDGE_TIMEOUT_SECONDS", "0.01")
    timeout_dir = tmp_path / "timeout"
    timeout_dir.mkdir()
    timed_out = runtime.invoke_host_bridge(
        f"{sys.executable} -c 'import time; time.sleep(1)'",
        task_dir=timeout_dir,
        register=_register(timeout_dir.name),
        project_root=tmp_path,
    )
    assert timed_out["timed_out"] is True
    assert timed_out["returncode"] == 124
    assert timed_out["failure_class"] == "host_bridge_timeout"


def test_host_bridge_executes_parsed_argv_without_shell(monkeypatch, tmp_path: Path):
    """success-case(security) - host bridge runtime executes parsed argv without shell."""
    # given
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    captured = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return "bridge ok\n", ""

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(runtime.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("AGENT_CREW_BRIDGE_TIMEOUT_SECONDS", "1")

    # when
    record = runtime.invoke_host_bridge(
        "bridge-command --mode 'two words'",
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
    )

    # then
    assert record["returncode"] == 0
    assert captured["args"] == ["bridge-command", "--mode", "two words"]
    assert captured["kwargs"]["shell"] is False


def test_host_bridge_expands_user_path_for_executable_head(monkeypatch, tmp_path: Path):
    """success-case(compatibility) - runtime matches checker tilde expansion for executable head."""
    # given
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    captured = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return "bridge ok\n", ""

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(runtime.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("AGENT_CREW_BRIDGE_TIMEOUT_SECONDS", "1")

    # when
    record = runtime.invoke_host_bridge(
        "~/bridge --mode safe",
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
    )

    # then
    assert record["returncode"] == 0
    assert captured["args"] == [str(home / "bridge"), "--mode", "safe"]
    assert captured["kwargs"]["shell"] is False


def test_host_bridge_does_not_execute_shell_metacharacters(tmp_path: Path):
    """success-case(security) - metacharacters are argv, not shell syntax."""
    # given
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    sentinel = tmp_path / "sentinel"

    # when
    record = runtime.invoke_host_bridge(
        f"{sys.executable} -c 'print(\"bridge ok\")' ; touch {sentinel}",
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
    )

    # then
    assert record["returncode"] == 0
    assert not sentinel.exists()


def test_host_bridge_rejects_unparseable_command_before_shell(monkeypatch, tmp_path: Path):
    """failure-case(validation) - rejects unparseable host bridge command before shell execution."""
    # given
    task_dir = tmp_path / "task"
    task_dir.mkdir()

    def fail_popen(*_args, **_kwargs):
        raise AssertionError("Popen must not be called for unparseable command")

    monkeypatch.setattr(runtime.subprocess, "Popen", fail_popen)

    # when
    record = runtime.invoke_host_bridge(
        "'unterminated",
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
    )

    # then
    assert record["returncode"] == 127
    assert record["failure_class"] == "host_bridge_start_failed"
    assert "No closing quotation" in record["stderr"]


def test_host_bridge_wait_progress_surfaces_child_output(monkeypatch, tmp_path: Path, capsys):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    script = tmp_path / "bridge.py"
    script.write_text(
        "\n".join([
            "import time",
            "print('child-progress: reviewer started', flush=True)",
            "time.sleep(0.08)",
            "print('child-progress: reviewer finished', flush=True)",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS", "0.01")
    monkeypatch.setenv("AGENT_CREW_BRIDGE_TIMEOUT_SECONDS", "1")

    record = runtime.invoke_host_bridge(
        f"{sys.executable} {script}",
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
    )

    stderr = capsys.readouterr().err
    progress_log = (task_dir / "progress.log").read_text(encoding="utf-8")
    output_tail = task_dir / "context" / "host-bridge-output-tail.txt"
    assert record["returncode"] == 0
    assert record["output_observed"] is True
    assert record["output_tail_path"] == "context/host-bridge-output-tail.txt"
    assert output_tail.is_file()
    assert "child-progress: reviewer finished" in output_tail.read_text(encoding="utf-8")
    assert "child-progress: reviewer started" in stderr
    assert "HOST_BRIDGE_OUTPUT" in progress_log


def test_host_bridge_preserves_normalized_task_before_stdout_tail_truncation(tmp_path: Path):
    """failure-case(regression) - full bridge stdout is parsed before record stdout truncation."""
    # given
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    script = tmp_path / "bridge.py"
    expected = "Implement the long normalization result"
    script.write_text(
        "\n".join([
            "import json",
            f"print(json.dumps({{'normalized_task': {expected!r}}}), flush=True)",
            "print('x' * 5000, flush=True)",
        ]),
        encoding="utf-8",
    )

    # when
    record = runtime.invoke_host_bridge(
        f"{sys.executable} {script}",
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
    )

    # then
    assert record["returncode"] == 0
    assert expected not in record["stdout"]
    assert record["normalized_task"] == expected
    assert runtime.normalized_task_from_bridge_record(record) == expected


def test_success_case_regression_records_host_bridge_selection_source(tmp_path: Path):
    """success-case(regression) - records why the host bridge command was selected."""
    # given
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    bridge = tmp_path / "codex-host-bridge"
    bridge.write_text("#!/usr/bin/env bash\nprintf 'done\\n'\n", encoding="utf-8")
    bridge.chmod(0o755)
    resolution = {
        "command": str(bridge),
        "source": "capabilities.host",
        "host": "codex",
        "capabilities_path": str(tmp_path / "capabilities.json"),
    }

    # when
    record = runtime.invoke_host_bridge(
        str(bridge),
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
        bridge_resolution=resolution,
    )

    # then
    invocation = json.loads((task_dir / "context" / "host-bridge-invocation.json").read_text(encoding="utf-8"))
    assert record["bridge_selection_source"] == "capabilities.host"
    assert record["bridge_selection_host"] == "codex"
    assert invocation["bridge_selection_source"] == "capabilities.host"
    assert invocation["bridge_selection_capabilities_path"] == str(tmp_path / "capabilities.json")


def test_failure_case_regression_blocks_claude_default_bridge_in_active_codex_session(monkeypatch, tmp_path: Path):
    """failure-case(regression) - active Codex sessions refuse accidental Claude default bridges."""
    # given
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    marker = tmp_path / "claude-started"
    bridge = tmp_path / "claude-host-bridge"
    bridge.write_text(f"#!/usr/bin/env bash\ntouch {marker}\n", encoding="utf-8")
    bridge.chmod(0o755)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    monkeypatch.delenv("AGENT_CREW_ALLOW_CROSS_HOST_BRIDGE", raising=False)
    resolution = {
        "command": str(bridge),
        "source": "capabilities.host",
        "host": "claude",
        "capabilities_path": str(tmp_path / "capabilities.json"),
    }

    # when
    record = runtime.invoke_host_bridge(
        str(bridge),
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
        bridge_resolution=resolution,
    )

    # then
    assert record["status"] == "current_session_required"
    assert record["failure_class"] == "current_session_required"
    assert "refusing claude-host-bridge from an active Codex session" in record["stderr"]
    assert not marker.exists()


def test_failure_case_regression_blocks_wrapped_claude_bridge_in_active_codex_session(monkeypatch, tmp_path: Path):
    """failure-case(regression) - wrapped shell commands cannot hide claude-host-bridge in Codex."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    marker = tmp_path / "claude-started"
    bridge = tmp_path / "claude-host-bridge"
    bridge.write_text(f"#!/usr/bin/env bash\ntouch {marker}\n", encoding="utf-8")
    bridge.chmod(0o755)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    monkeypatch.delenv("AGENT_CREW_ALLOW_CROSS_HOST_BRIDGE", raising=False)

    record = runtime.invoke_host_bridge(
        f"bash -c '{bridge}'",
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
    )

    assert record["status"] == "current_session_required"
    assert record["failure_class"] == "current_session_required"
    assert "refusing claude-host-bridge from an active Codex session" in record["stderr"]
    assert not marker.exists()


def test_failure_case_regression_blocks_mixed_claude_fallback_bridge_in_active_codex_session(monkeypatch, tmp_path: Path):
    """failure-case(regression) - mixed bridge commands cannot fall back to Claude in Codex."""
    # given
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    codex_marker = tmp_path / "codex-started"
    claude_marker = tmp_path / "claude-started"
    codex_bridge = bin_dir / "codex-host-bridge"
    claude_bridge = bin_dir / "claude-host-bridge"
    codex_bridge.write_text(
        f"#!/usr/bin/env bash\ntouch {codex_marker}\nexit 1\n",
        encoding="utf-8",
    )
    claude_bridge.write_text(f"#!/usr/bin/env bash\ntouch {claude_marker}\n", encoding="utf-8")
    codex_bridge.chmod(0o755)
    claude_bridge.chmod(0o755)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.delenv("AGENT_CREW_ALLOW_CROSS_HOST_BRIDGE", raising=False)

    # when
    record = runtime.invoke_host_bridge(
        "bash -c 'codex-host-bridge || claude-host-bridge'",
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
    )

    # then
    assert record["status"] == "current_session_required"
    assert record["failure_class"] == "current_session_required"
    assert "refusing claude-host-bridge from an active Codex session" in record["stderr"]
    assert not codex_marker.exists()
    assert not claude_marker.exists()


def test_failure_case_regression_command_run_blocks_claude_default_bridge_in_codex(monkeypatch, tmp_path: Path, capsys):
    """failure-case(regression) - crew run does not trust stale Claude capabilities in Codex."""
    # given
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    state_info = runtime.resolve_project_state(
        home=home,
        project_root=project,
        ensure=True,
        migrate_legacy=True,
    )
    state_dir = Path(state_info["state_dir"])
    (state_dir / "capabilities.json").write_text(json.dumps({"host": "claude"}), encoding="utf-8")
    claude_marker = tmp_path / "claude-started"
    codex_marker = tmp_path / "codex-started"
    claude_bridge = home / "adapters" / "claude" / "bin" / "claude-host-bridge"
    codex_bridge = home / "adapters" / "codex" / "bin" / "codex-host-bridge"
    claude_bridge.parent.mkdir(parents=True)
    codex_bridge.parent.mkdir(parents=True)
    claude_bridge.write_text(f"#!/usr/bin/env bash\ntouch {claude_marker}\n", encoding="utf-8")
    codex_bridge.write_text(f"#!/usr/bin/env bash\ntouch {codex_marker}\n", encoding="utf-8")
    claude_bridge.chmod(0o755)
    codex_bridge.chmod(0o755)
    monkeypatch.setenv("AGENT_CREW_HOME", str(home))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")

    # when
    args = argparse.Namespace(
        task="read docs",
        project_root=str(project),
        fake_host_result=None,
        host_bridge_command=None,
    )
    assert runtime.command_run(args) == 0

    # then
    out = capsys.readouterr().out
    task_dirs = sorted((state_dir / "tasks").iterdir())
    invocation = json.loads((task_dirs[-1] / "context" / "host-bridge-invocation.json").read_text(encoding="utf-8"))
    assert "HOST_BRIDGE: auto_completed" in out
    assert invocation["bridge_selection_source"] == "active_host_env"
    assert invocation["bridge_selection_host"] == "codex"
    assert invocation["status"] == "completed"
    assert codex_marker.exists()
    assert not claude_marker.exists()


def test_default_bridge_prefers_active_codex_env_over_stale_capabilities(monkeypatch, tmp_path: Path):
    """failure-case(regression) - active Codex env wins over stale Claude capabilities."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    state_info = runtime.resolve_project_state(home=home, project_root=project, ensure=True, migrate_legacy=True)
    state_dir = Path(state_info["state_dir"])
    (state_dir / "capabilities.json").write_text(json.dumps({"host": "claude"}), encoding="utf-8")
    codex_bridge = home / "adapters" / "codex" / "bin" / "codex-host-bridge"
    claude_bridge = home / "adapters" / "claude" / "bin" / "claude-host-bridge"
    codex_bridge.parent.mkdir(parents=True)
    claude_bridge.parent.mkdir(parents=True)
    codex_bridge.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    claude_bridge.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    codex_bridge.chmod(0o755)
    claude_bridge.chmod(0o755)
    monkeypatch.delenv("AGENT_CREW_HOST", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-1")

    resolution = runtime.resolve_host_bridge(None, home, project)

    assert resolution["command"] == str(codex_bridge)
    assert resolution["source"] == "active_host_env"
    assert resolution["host"] == "codex"


def test_default_bridge_prefers_active_claude_env_over_stale_capabilities(monkeypatch, tmp_path: Path):
    """failure-case(regression) - active Claude env wins over stale Codex capabilities."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    state_info = runtime.resolve_project_state(home=home, project_root=project, ensure=True, migrate_legacy=True)
    state_dir = Path(state_info["state_dir"])
    (state_dir / "capabilities.json").write_text(json.dumps({"host": "codex"}), encoding="utf-8")
    codex_bridge = home / "adapters" / "codex" / "bin" / "codex-host-bridge"
    claude_bridge = home / "adapters" / "claude" / "bin" / "claude-host-bridge"
    codex_bridge.parent.mkdir(parents=True)
    claude_bridge.parent.mkdir(parents=True)
    codex_bridge.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    claude_bridge.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    codex_bridge.chmod(0o755)
    claude_bridge.chmod(0o755)
    monkeypatch.delenv("AGENT_CREW_HOST", raising=False)
    for name in ("CODEX", "CODEX_CI", "CODEX_THREAD_ID", "CODEX_MANAGED_BY_NPM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_SESSION_ID", "session-1")

    resolution = runtime.resolve_host_bridge(None, home, project)

    assert resolution["command"] == str(claude_bridge)
    assert resolution["source"] == "active_host_env"
    assert resolution["host"] == "claude"


def test_host_bridge_child_output_preview_stays_single_line():
    preview = runtime.host_bridge_child_output_preview("alpha\n" + ("x" * 250), "", limit=80)

    assert "\n" not in preview
    assert "stdout: ...[truncated] " in preview


def test_mark_auto_completed_preserves_bridge_output_in_result(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "result.md").write_text(
        "# Existing Quality Result\n\n"
        "STATUS: completed\n"
        "EVIDENCE: context/review.md\n",
        encoding="utf-8",
    )
    register = _register(task_dir.name)
    pipeline = {"stages": ["backend", "reviewer"], "completed_stages": 2}
    bridge_record = {
        "returncode": 0,
        "stdout": "REVIEW: APPROVED\nREPORT: context/review.md\nQUALITY_METRICS: context/quality-metrics.json\n",
        "stderr": "",
        "timed_out": False,
        "failure_class": "",
        "status": "completed",
    }

    runtime.mark_auto_completed(
        task_dir,
        register,
        pipeline,
        bridge_record,
        "completed by bridge",
        preserve_quality_state=True,
    )

    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    assert "HOST_BRIDGE: auto_completed" in result_text
    assert "## Host Bridge Output" in result_text
    assert "REVIEW: APPROVED" in result_text
    assert "QUALITY_METRICS: context/quality-metrics.json" in result_text


def test_terminate_host_bridge_falls_back_to_process_methods(monkeypatch):
    class Proc:
        pid = 123

        def __init__(self):
            self.calls = 0
            self.terminated = False
            self.killed = False

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("cmd", timeout)
            return "out", "err"

    proc = Proc()
    monkeypatch.setattr(runtime.os, "killpg", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("no group")))

    assert runtime.terminate_host_bridge(proc) == ("out", "err")
    assert proc.terminated is True
    assert proc.killed is True


def test_host_bridge_timeout_before_first_poll(monkeypatch, tmp_path: Path):
    class Proc:
        returncode = None

    task_dir = tmp_path / "task"
    task_dir.mkdir()

    monkeypatch.setenv("AGENT_CREW_BRIDGE_MONITOR_INTERVAL_SECONDS", "10")
    monkeypatch.setenv("AGENT_CREW_BRIDGE_TIMEOUT_SECONDS", "0.001")
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *_args, **_kwargs: Proc())
    monotonic_values = iter([100.0, 100.1])
    monkeypatch.setattr(runtime.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(runtime, "terminate_host_bridge", lambda _proc: ("", ""))

    record = runtime.invoke_host_bridge(
        "bridge-command",
        task_dir=task_dir,
        register=_register(task_dir.name),
        project_root=tmp_path,
    )

    assert record["timed_out"] is True
    assert record["returncode"] == 124


def test_host_bridge_defaults_and_registry_edges(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_CREW_HOST_BRIDGE_ACTIVE", "1")
    assert runtime.default_host_bridge_command(tmp_path / "home", tmp_path / "project") == ""

    monkeypatch.delenv("AGENT_CREW_HOST_BRIDGE_ACTIVE")
    monkeypatch.setenv("AGENT_CREW_HOST_BRIDGE_DISABLE_DEFAULT", "1")
    assert runtime.default_host_bridge_command(tmp_path / "home", tmp_path / "project") == ""

    monkeypatch.delenv("AGENT_CREW_HOST_BRIDGE_DISABLE_DEFAULT")
    home = tmp_path / "home"
    project = tmp_path / "project"
    caps = home / "state" / project.name / "capabilities.json"
    caps.parent.mkdir(parents=True)
    caps.write_text(json.dumps({"host": "codex"}), encoding="utf-8")
    assert runtime.default_host_bridge_command(home, project) == ""

    assert runtime.asset_root(str(tmp_path)) == tmp_path.resolve()
    assert runtime.asset_root() == RUNTIME.parent.parent
    assert runtime.read_agent_registry(tmp_path / "missing") == {}

    root = tmp_path / "root"
    _write_registry(root)
    agents = runtime.read_agent_registry(root)
    assert "short" not in agents
    assert agents["analyst"]["safe"] is True


def test_language_normalization_and_issue_helpers(monkeypatch, tmp_path: Path):
    assert runtime.contains_hangul("한글") is True
    assert runtime.detect_source_language("かな") == "ja"
    assert runtime.detect_source_language("漢字") == "zh"
    assert runtime.detect_source_language("я") == "cyrillic"
    assert runtime.detect_source_language("مرحبا") == "arabic"
    assert runtime.detect_source_language("∑") == "unknown"
    assert "missing-context" in runtime.ambiguous_input_reason("do this")
    assert runtime.needs_input_normalization("ok") is True
    assert "Normalize raw user input" in runtime.korean_normalization_task("진행", next_target="crew run")
    commit_metadata = runtime.input_normalization_metadata("변경사항 커밋해줘", next_target="crew run supervisor")
    assert "vcs.commit.message.compose" in commit_metadata["required_capabilities"]
    assert "vcs.history.local_mutation" in commit_metadata["required_capabilities"]
    negative_remote_metadata = runtime.input_normalization_metadata(
        "성능 개선 반영해줘. Do not push, merge, deploy, or perform remote operations.",
        next_target="crew run supervisor",
    )
    assert negative_remote_metadata["required_capabilities"] == []
    gate_reference_metadata = runtime.input_normalization_metadata(
        "Improve the runtime checker and preserve hard gates for push, merge, and deploy.",
        next_target="crew run supervisor",
    )
    assert gate_reference_metadata["required_capabilities"] == []
    commit_without_remote = runtime.required_capabilities_for_task(
        "Commit local changes without pushing or deploying."
    )
    assert "vcs.commit.message.compose" in commit_without_remote
    assert "vcs.history.local_mutation" in commit_without_remote
    assert "vcs.remote_mutation" not in commit_without_remote
    assert "deployment.mutate" not in commit_without_remote
    issue_resolution_metadata = runtime.input_normalization_metadata("열려있는 이슈 해결", next_target="crew run supervisor")
    assert "tracker.issue.mutate" not in issue_resolution_metadata["required_capabilities"]
    handoff = runtime.korean_normalization_handoff(
        request_id="r1",
        project_root=tmp_path,
        normalized_task="normalize",
        raw_task="진행",
        next_target="crew run",
        status="handoff_ready",
    )
    assert "RAW_TASK: 진행" in handoff

    comments = [{"body": "plain\n- must support x\n* nice to have", "isMinimized": False}]
    assert runtime.extract_comment_requirements(comments) == ["must support x"]

    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    assert runtime.load_issue_payload("1") == (None, "gh executable not found")
    monkeypatch.setattr(
        runtime.subprocess,
        "check_output",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "gh", stderr="bad auth")),
    )
    assert runtime.load_issue_payload("1") == (None, "bad auth")
    monkeypatch.setattr(runtime.subprocess, "check_output", lambda *_args, **_kwargs: "not json")
    issue, error = runtime.load_issue_payload("1")
    assert issue is None
    assert "failed to parse issue payload" in error

    monkeypatch.setattr(runtime, "load_issue_payload", lambda issue_number: (None, "offline"))
    records = runtime.record_issue_ingestion_evidence(tmp_path / "task", "see #123")
    assert records == [{"issue_number": "123", "path": str(tmp_path / "task" / "context" / "issue-123-ingestion.json"), "comments_ingested": False, "comment_count": 0}]


def test_agent_mutating_guard_honors_read_only_overrides():
    """success-case(regression) - TC-004/TC-005 classify read-only and mutating prompts."""
    assert runtime.looks_mutating(
        "Evaluate routing behavior and identify gaps only; do not edit files."
    ) is False
    assert runtime.looks_mutating(
        "검토만 해주세요. 수정하지 말고 부족한 점만 알려주세요."
    ) is False
    assert runtime.looks_mutating(
        "개선 우선순위 항목들을 더 면밀하게 분석 검토하고 구현 계획을 수립해."
    ) is False
    assert runtime.looks_mutating(
        "구현 계획만 수립해. 수정하지 마세요."
    ) is False
    assert runtime.looks_mutating(
        "컨텍스트 관련 개선 작업 이후 뭔가 느려진거같아서 관련해서 딥다이브 해"
    ) is False
    assert runtime.looks_mutating(
        "심층분석해서 구체적인 수정 방안 계획해"
    ) is False
    assert runtime.looks_mutating(
        "ai가 최소구현만 해서 그런지 제대로 구현하는게 아니라 많이 비어있는 구현을 하는 양상을 개선 할 수 있는 방법을 모색해봐"
    ) is False
    assert runtime.looks_mutating(
        "방법을 모색하라고 했는데 구현을 해버리네"
    ) is False
    assert runtime.looks_mutating(
        "왜 구현을 했는지 분석해줘"
    ) is False
    assert runtime.looks_mutating(
        "Read-only review. Output sections: Must Fix, Should Fix."
    ) is False
    assert runtime.looks_mutating(
        "$review 코드리뷰. Must Fix / Should Fix 형식으로 보고."
    ) is False
    assert runtime.looks_mutating("어떤 commit 있어?") is False
    assert runtime.looks_mutating("what is the latest commit?") is False

    assert runtime.looks_mutating("Review and update README.md with the findings.") is True
    assert runtime.looks_mutating("검토 후 README를 수정해주세요.") is True
    assert runtime.looks_mutating("기존 동작을 변경하지 않으면서 새 기능을 만들어주세요.") is True
    assert runtime.looks_mutating("기존 동작을 변경하지 않고 리포트를 작성해주세요.") is True
    assert runtime.looks_mutating("설정을 건드리지 말고 새 파일을 생성해주세요.") is True
    assert runtime.looks_mutating("구현 계획을 수립하고 코드에 반영해.") is True
    assert runtime.looks_mutating("구현 계획대로 진행해") is True
    assert runtime.looks_mutating("구현 계획을 실행해") is True
    assert runtime.looks_mutating("구현 계획을 그대로 진행해") is True
    assert runtime.looks_mutating("구현 계획에 따라 진행해") is True
    assert runtime.looks_mutating("개선 계획대로 진행해") is True
    assert runtime.looks_mutating("개선 계획을 실행해") is True
    assert runtime.looks_mutating("수정 방안대로 반영해") is True
    assert runtime.looks_mutating("해결 전략에 따라 진행해") is True
    assert runtime.looks_mutating("teach me while refactoring this function") is True
    assert runtime.looks_mutating("teach me while removing this file") is True
    assert runtime.looks_mutating("teach me while changing this hook") is True
    assert runtime.looks_mutating("teach me while testing this feature") is True


def test_command_run_current_session_normalization_and_reported_block(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()

    current_session_record = {
        "returncode": 1,
        "stdout": "AGENT_CREW_BRIDGE_STATUS: current_session_required\n",
        "stderr": "",
        "timed_out": False,
        "failure_class": "current_session_required",
        "status": "current_session_required",
    }
    monkeypatch.setattr(runtime, "invoke_host_bridge", lambda *_args, **_kwargs: current_session_record)
    args = argparse.Namespace(
        task="진행해주세요",
        project_root=str(project),
        fake_host_result=None,
        host_bridge_command="bridge",
    )
    assert runtime.command_run(args) == 0
    out = capsys.readouterr().out
    assert "HOST_BRIDGE: current_session_required" in out
    state_info = runtime.resolve_project_state(
        home=tmp_path / "home",
        project_root=project,
        prefer_existing_legacy=True,
    )
    task_dirs = sorted((Path(state_info["state_dir"]) / "tasks").iterdir())
    result_text = (task_dirs[-1] / "result.md").read_text(encoding="utf-8")
    assert "NORMALIZATION_GATE: required" in result_text

    blocked_record = {
        "returncode": 0,
        "stdout": "STATUS: blocked\nBLOCKER: still blocked\n",
        "stderr": "",
        "timed_out": False,
        "failure_class": "",
        "status": "completed",
    }
    monkeypatch.setattr(runtime, "invoke_host_bridge", lambda *_args, **_kwargs: blocked_record)
    args.task = "investigate runtime"
    assert runtime.command_run(args) == 3
    state_info = runtime.resolve_project_state(
        home=tmp_path / "home",
        project_root=project,
        prefer_existing_legacy=True,
    )
    task_dirs = sorted((Path(state_info["state_dir"]) / "tasks").iterdir())
    register = json.loads((task_dirs[-1] / "register.json").read_text(encoding="utf-8"))
    assert register["host_bridge_failure_reason"] == "bridge_reported_blocked"


def test_command_run_normalization_bridge_success_does_not_auto_complete_task(monkeypatch, tmp_path: Path, capsys):
    """failure-case(regression) - input-normalizer bridge success is not whole-task completion."""
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()

    bridge_record = {
        "schema_version": 1,
        "task_id": "task",
        "command": "bridge",
        "command_argv": ["bridge"],
        "command_display": "bridge",
        "bridge_selection_source": "direct_invoke",
        "bridge_selection_host": "codex",
        "bridge_selection_capabilities_path": "",
        "started_at": "2026-07-05T00:00:00Z",
        "finished_at": "2026-07-05T00:00:01Z",
        "returncode": 0,
        "stdout": '{"normalized_task":"Implement the requested feature"}\n',
        "stderr": "",
        "timed_out": False,
        "timeout_seconds": 1800,
        "failure_class": "",
        "status": "completed",
        "direct_agent": False,
        "output_observed": True,
        "output_tail_path": "context/host-bridge-output-tail.txt",
        "stall_class": "",
    }
    monkeypatch.setattr(runtime, "invoke_host_bridge", lambda *_args, **_kwargs: bridge_record)
    args = argparse.Namespace(
        task="기능을 추가해줘",
        project_root=str(project),
        fake_host_result=None,
        host_bridge_command="bridge",
    )

    assert runtime.command_run(args) == 0

    out = capsys.readouterr().out
    state_info = runtime.resolve_project_state(
        home=tmp_path / "home",
        project_root=project,
        prefer_existing_legacy=True,
    )
    task_dirs = sorted((Path(state_info["state_dir"]) / "tasks").iterdir())
    task_dir = task_dirs[-1]
    register = json.loads((task_dir / "register.json").read_text(encoding="utf-8"))
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    normalization_pipeline_path = task_dir / "context" / "normalization-pipeline.json"

    assert "STATUS: handoff_ready" in out
    assert "HOST_BRIDGE: auto_completed" not in out
    assert register["current_phase"] == "handoff_ready"
    assert register["host_bridge_status"] == "internal_handoff_ready"
    assert not (task_dir / "pipeline.json").exists()
    assert register["normalization_pipeline_path"] == str(normalization_pipeline_path)
    normalization_pipeline = json.loads(normalization_pipeline_path.read_text(encoding="utf-8"))
    assert normalization_pipeline["stages"] == ["input-normalizer"]
    assert normalization_pipeline["completed_stages"] == 1
    preflight = subprocess.run(
        ["python3", str(REPO_ROOT / "core" / "scripts" / "pipeline-capability-check.py"),
         "--pipeline", str(normalization_pipeline_path), "--format", "json"],
        text=True,
        capture_output=True,
    )
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    assert "NORMALIZATION_GATE: completed" in result_text
    assert "HOST_BRIDGE: auto_completed" not in result_text
    audit_text = (task_dir / "context" / "normalized_task.md").read_text(encoding="utf-8")
    assert "RAW_INPUT: 기능을 추가해줘" in audit_text
    assert "NORMALIZED_TASK: Implement the requested feature" in audit_text


def test_command_run_normalization_bridge_success_parses_wrapped_result(monkeypatch, tmp_path: Path, capsys):
    """failure-case(regression) - wrapped host bridge result JSON still drives normalized handoff."""
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()

    wrapped_result = {
        "type": "result",
        "result": '```json\n{"normalized_task":"Implement the wrapped feature"}\n```',
    }
    bridge_record = {
        "schema_version": 1,
        "task_id": "task",
        "command": "bridge",
        "command_argv": ["bridge"],
        "command_display": "bridge",
        "bridge_selection_source": "direct_invoke",
        "bridge_selection_host": "claude",
        "bridge_selection_capabilities_path": "",
        "started_at": "2026-07-05T00:00:00Z",
        "finished_at": "2026-07-05T00:00:01Z",
        "returncode": 0,
        "stdout": json.dumps(wrapped_result) + "\n",
        "stderr": "",
        "timed_out": False,
        "timeout_seconds": 1800,
        "failure_class": "",
        "status": "completed",
        "direct_agent": False,
        "output_observed": True,
        "output_tail_path": "context/host-bridge-output-tail.txt",
        "stall_class": "",
    }
    monkeypatch.setattr(runtime, "invoke_host_bridge", lambda *_args, **_kwargs: bridge_record)
    args = argparse.Namespace(
        task="기능을 추가해줘",
        project_root=str(project),
        fake_host_result=None,
        host_bridge_command="bridge",
    )

    assert runtime.command_run(args) == 0

    out = capsys.readouterr().out
    state_info = runtime.resolve_project_state(
        home=tmp_path / "home",
        project_root=project,
        prefer_existing_legacy=True,
    )
    task_dirs = sorted((Path(state_info["state_dir"]) / "tasks").iterdir())
    task_dir = task_dirs[-1]
    register = json.loads((task_dir / "register.json").read_text(encoding="utf-8"))
    handoff_text = (task_dir / "handoff.md").read_text(encoding="utf-8")
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")
    audit_text = (task_dir / "context" / "normalized_task.md").read_text(encoding="utf-8")
    normalization_pipeline = json.loads(
        (task_dir / "context" / "normalization-pipeline.json").read_text(encoding="utf-8")
    )

    assert "STATUS: handoff_ready" in out
    assert register["task"] == "Implement the wrapped feature"
    assert not (task_dir / "pipeline.json").exists()
    assert normalization_pipeline["task"] == "Implement the wrapped feature"
    assert "supervisor" not in normalization_pipeline["stages"]
    assert "TASK: Implement the wrapped feature" in handoff_text
    assert "TASK: 기능을 추가해줘" not in handoff_text
    assert "# Implement the wrapped feature" in result_text
    assert "RAW_INPUT: 기능을 추가해줘" in audit_text
    assert "NORMALIZED_TASK: Implement the wrapped feature" in audit_text


def test_normalization_bridge_parser_rejects_invalid_normalized_task_values():
    """failure-case(validation) - normalized_task must be an English string."""
    # given
    non_english_records = (
        {"stdout": '{"normalized_task":"기능을 추가해줘"}\n'},
        {"stdout": '{"normalized_task":"เพิ่มฟีเจอร์"}\n'},
        {"stdout": '{"normalized_task":"Προσθήκη δυνατότητας"}\n'},
        {"stdout": '{"normalized_task":"הוסף תכונה"}\n'},
        {"stdout": '{"normalized_task":"सुविधा जोड़ें"}\n'},
    )
    non_string_record = {"stdout": '{"normalized_task":["Implement the feature"]}\n'}

    # when / then
    for record in non_english_records:
        assert runtime.normalized_task_from_bridge_record(record) == ""
    assert runtime.normalized_task_from_bridge_record(non_string_record) == ""


def test_normalization_bridge_parser_accepts_english_with_unicode_punctuation():
    """boundary-case(validation) - English normalized_task may contain Unicode punctuation."""
    # given
    record = {"stdout": '{"normalized_task":"Implement the requested feature — keep tests passing"}\n'}

    # when / then
    assert (
        runtime.normalized_task_from_bridge_record(record)
        == "Implement the requested feature — keep tests passing"
    )


def test_command_run_normalization_bridge_success_blocks_non_english_normalized_task(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    """failure-case(validation) - non-English normalized_task cannot complete the normalization gate."""
    # given
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()

    bridge_record = {
        "schema_version": 1,
        "task_id": "task",
        "command": "bridge",
        "command_argv": ["bridge"],
        "command_display": "bridge",
        "bridge_selection_source": "direct_invoke",
        "bridge_selection_host": "claude",
        "bridge_selection_capabilities_path": "",
        "started_at": "2026-07-05T00:00:00Z",
        "finished_at": "2026-07-05T00:00:01Z",
        "returncode": 0,
        "stdout": '{"type":"result","result":"{\\"normalized_task\\":\\"기능을 추가해줘\\"}"}\n',
        "stderr": "",
        "timed_out": False,
        "timeout_seconds": 1800,
        "failure_class": "",
        "status": "completed",
        "direct_agent": False,
        "output_observed": True,
        "output_tail_path": "context/host-bridge-output-tail.txt",
        "stall_class": "",
    }
    monkeypatch.setattr(runtime, "invoke_host_bridge", lambda *_args, **_kwargs: bridge_record)
    args = argparse.Namespace(
        task="기능을 추가해줘",
        project_root=str(project),
        fake_host_result=None,
        host_bridge_command="bridge",
    )

    # when
    result = runtime.command_run(args)

    # then
    assert result == 3
    out = capsys.readouterr().out
    state_info = runtime.resolve_project_state(
        home=tmp_path / "home",
        project_root=project,
        prefer_existing_legacy=True,
    )
    task_dirs = sorted((Path(state_info["state_dir"]) / "tasks").iterdir())
    task_dir = task_dirs[-1]
    register = json.loads((task_dir / "register.json").read_text(encoding="utf-8"))
    handoff_text = (task_dir / "handoff.md").read_text(encoding="utf-8")

    assert "STATUS: blocked" in out
    assert "BLOCKER: missing_normalized_task" in out
    assert register["current_phase"] == "blocked"
    assert register["blocked_by"] == ["missing_normalized_task"]
    assert "NORMALIZATION_GATE: completed" not in handoff_text
    assert "TASK: 기능을 추가해줘" not in handoff_text


def test_command_run_normalization_bridge_success_blocks_missing_normalized_task(monkeypatch, tmp_path: Path, capsys):
    """failure-case(regression) - successful normalization bridge output must include normalized_task."""
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    project.mkdir()

    bridge_record = {
        "schema_version": 1,
        "task_id": "task",
        "command": "bridge",
        "command_argv": ["bridge"],
        "command_display": "bridge",
        "bridge_selection_source": "direct_invoke",
        "bridge_selection_host": "claude",
        "bridge_selection_capabilities_path": "",
        "started_at": "2026-07-05T00:00:00Z",
        "finished_at": "2026-07-05T00:00:01Z",
        "returncode": 0,
        "stdout": '{"type":"result","result":"{}"}\n',
        "stderr": "",
        "timed_out": False,
        "timeout_seconds": 1800,
        "failure_class": "",
        "status": "completed",
        "direct_agent": False,
        "output_observed": True,
        "output_tail_path": "context/host-bridge-output-tail.txt",
        "stall_class": "",
    }
    monkeypatch.setattr(runtime, "invoke_host_bridge", lambda *_args, **_kwargs: bridge_record)
    args = argparse.Namespace(
        task="기능을 추가해줘",
        project_root=str(project),
        fake_host_result=None,
        host_bridge_command="bridge",
    )

    assert runtime.command_run(args) == 3

    out = capsys.readouterr().out
    state_info = runtime.resolve_project_state(
        home=tmp_path / "home",
        project_root=project,
        prefer_existing_legacy=True,
    )
    task_dirs = sorted((Path(state_info["state_dir"]) / "tasks").iterdir())
    task_dir = task_dirs[-1]
    register = json.loads((task_dir / "register.json").read_text(encoding="utf-8"))
    result_text = (task_dir / "result.md").read_text(encoding="utf-8")

    assert "STATUS: blocked" in out
    assert "BLOCKER: missing_normalized_task" in out
    assert register["current_phase"] == "blocked"
    assert register["blocked_by"] == ["missing_normalized_task"]
    assert register["host_bridge_status"] == "failed"
    assert "STATUS: blocked" in result_text
    assert "BLOCKER: missing_normalized_task" in result_text
    assert "TASK: 기능을 추가해줘" not in (task_dir / "handoff.md").read_text(encoding="utf-8")


def test_command_agent_error_paths(monkeypatch, tmp_path: Path, capsys):
    """failure-case(regression) - direct-agent routing rejects only mutating tasks."""
    root = tmp_path / "runtime-root"
    _write_registry(root)
    (root / "project").mkdir()
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))

    assert runtime.command_agent(_agent_args(root)) == 0
    assert "usage: crew-runtime.py agent" in capsys.readouterr().out

    assert runtime.command_agent(_agent_args(root, routing=True)) == 0
    assert "Auto-Routing Rules" in capsys.readouterr().out

    assert runtime.command_agent(_agent_args(root, "analyst")) == 2
    assert "task description is required" in capsys.readouterr().err

    assert runtime.command_agent(_agent_args(root, "unmatched read only question")) == 2
    assert "cannot auto-route" in capsys.readouterr().err

    monkeypatch.setattr(runtime, "auto_route_agent", lambda _task, _agents: ("ghost", "forced"))
    assert runtime.command_agent(_agent_args(root, "plain read only question")) == 2
    assert "unknown agent 'ghost'" in capsys.readouterr().err

    assert runtime.command_agent(_agent_args(root, "unsafe", "read only")) == 2
    assert "cannot be invoked directly" in capsys.readouterr().err

    assert runtime.command_agent(
        _agent_args(root, "analyst", "$review 코드리뷰. Must Fix / Should Fix 형식으로 보고.")
    ) == 0
    assert "STATUS: handoff_ready" in capsys.readouterr().out

    review_context = (
        "---\n"
        "description: 독립 코드 리뷰 패스 (작성자≠리뷰어, read-only)\n"
        "---\n"
        "구현 컨텍스트와 분리된 독립 리뷰 패스(read-only 서브에이전트)로 "
        "현재 브랜치 변경분에 대한 코드 리뷰를 수행해줘.\n\n"
        "1. base 브랜치 감지 후 최근 커밋/변경 범위 확인\n\n"
        "## 출력 형식\n"
        "```markdown\n"
        "## Code Review Summary\n\n"
        "### Must Fix (머지 차단)\n"
        "- `file:line` 문제 → 수정 제안\n\n"
        "```\n\n"
        "## 다음 액션 제안\n"
        "- Must Fix 있으면 /fix <대상> 또는 직접 수정 후 재실행\n"
        "- 에이전트가 코드를 수정하지 않도록 프롬프트에 read-only 리뷰임을 명시.\n\n"
        "## 사용 예시\n"
        "```bash\n"
        "/review\n"
        "```\n\n"
        "## 주의\n"
        "- 에이전트가 코드를 수정하지 않도록 read-only 리뷰임을 명시.\n"
        "- 비정상 결과는 성공으로 바꾸지 않고 그대로 노출."
    )
    assert runtime.command_agent(_agent_args(root, "analyst", review_context)) == 0
    assert "STATUS: handoff_ready" in capsys.readouterr().out

    assert runtime.command_agent(
        _agent_args(
            root,
            "analyst",
            "Read-only review of commit 7decdd1. Do not modify files.",
        )
    ) == 0
    assert "STATUS: handoff_ready" in capsys.readouterr().out

    assert runtime.command_agent(
        _agent_args(
            root,
            "analyst",
            f"{review_context}\n\n사용자 요청: README를 수정해",
        )
    ) == 2
    assert "direct invocation is read-only" in capsys.readouterr().err

    mutating_variants = (
        f"{review_context}\n\nPlease review and fix it.",
        f"{review_context}\n\nI want you to fix the implementation.",
        f"{review_context}\n\nI want you to push main.",
        f"{review_context}\n\n사용자 요청: 변경분 수정 진행",
        "Could you amend this?",
        "git push origin main",
        "git cherry-pick abc123",
        "Could you git revert abc123?",
        "Review commit 7decdd1 and apply it.",
        "Review commit 7decdd1 and push main.",
        "Commit review changes.",
        "Please review, then commit review changes.",
        "Review whether to fix issues, then fix them.",
        "Please review and explain how I can fix it, then fix it.",
        "Could you push this branch?",
        "Push this branch.",
        "Apply these changes.",
        "Review commit 7decdd1 and apply these changes.",
        "Please push to origin main.",
        "Review the changes and push the branch to origin.",
        "Review commit abc123, then amend with updated tests.",
        "Inspect commit abc123 and revert due to the regression.",
        "Review commit abc123 and cherry-pick onto develop.",
        "git push origin main; do not push it, then push this branch.",
        "Read-only review. You should fix it.",
        "Read-only review. Please apply the migration.",
        "Read-only review. Execute git push origin main.",
        "Read-only review. Please review and test it.",
        "Read-only review. Then test it.",
    )
    for task in mutating_variants:
        assert runtime.command_agent(_agent_args(root, "analyst", task)) == 2
        assert "direct invocation is read-only" in capsys.readouterr().err

    read_only_variants = (
        "Could you explain how to amend this?",
        "Could you explain git revert behavior?",
        "Revert is a Git command; explain what it does.",
        "Amend is a confusing Git term; explain it.",
        "Read-only code review: verify commit review plus branch push remains mutating without changing files.",
        "Explain what commit review means.",
        "Review whether to fix issues.",
        "Review commit 7decdd1 and do not apply it.",
        "Please review and explain how I can fix it.",
        "Please review and explain how we can update it.",
        "git push origin main; do not push it.",
        "git push origin main is shown here for analysis; do not run it.",
        "Read-only review. Explain why you should fix it.",
        "Read-only review. Explain how to apply the migration.",
        "Read-only review. Show how to execute git push origin main.",
        "Read-only review. Explain whether to test it.",
    )
    for task in read_only_variants:
        assert runtime.command_agent(_agent_args(root, "analyst", task)) == 0
        assert "STATUS: handoff_ready" in capsys.readouterr().out


def test_command_agent_accepts_korean_self_evolution_complaint(
    monkeypatch, tmp_path: Path, capsys
):
    root = tmp_path / "runtime-root"
    _write_registry(root)
    (root / "project").mkdir()
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))

    task = (
        "에이전트크루에서 알아서 서브에이전트나 스킬을 보강하거나 만들어서 "
        "지속적으로 성장하도록 했는데 제대로 안되는거같아"
    )

    assert runtime.command_agent(_agent_args(root, "analyst", task)) == 0
    assert "STATUS: handoff_ready" in capsys.readouterr().out


def test_command_agent_accepts_korean_analysis_complaint_about_accidental_mutation(
    monkeypatch, tmp_path: Path, capsys
):
    root = tmp_path / "runtime-root"
    _write_registry(root)
    (root / "project").mkdir()
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))

    task = "분석하라고 하는데 코드를 고쳐버리는 문제가 있음"

    assert runtime.command_agent(_agent_args(root, "analyst", task)) == 0
    assert "STATUS: handoff_ready" in capsys.readouterr().out


def test_command_agent_routes_bare_push_and_cross_verb_false_negatives(
    monkeypatch, tmp_path: Path, capsys
):
    """failure-case(regression) - direct-agent routing rejects the two classifier false-negatives while preservation prose stays read-only (mirrors test_quality_loop_gate.py; AC-001..AC-003)."""
    # given
    root = tmp_path / "runtime-root"
    _write_registry(root)
    (root / "project").mkdir()
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))

    # cross-verb negation (#1) plus bare "push <remote> <branch>" (#2) must all
    # route as mutation, so direct read-only invocation is rejected (exit 2).
    mutating_variants = (
        "Cherry-pick this, do not push it.",
        "Apply this patch, do not push.",
        "Revert this, do not push.",
        "Amend this, do not push.",
        "push origin main",
        "push origin master",
        "push origin develop",
        "push origin feature/login",
        "push upstream main",
    )
    # narrowness locks: off-set branch token and advisory prose stay read-only.
    read_only_variants = (
        "push origin scratch-notes",
        "the team should push to origin main",
    )

    # when / then
    for task in mutating_variants:
        assert runtime.command_agent(_agent_args(root, "analyst", task)) == 2
        assert "direct invocation is read-only" in capsys.readouterr().err

    for task in read_only_variants:
        assert runtime.command_agent(_agent_args(root, "analyst", task)) == 0
        assert "STATUS: handoff_ready" in capsys.readouterr().out


def test_command_issue_ingest_error_and_output(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr(runtime, "load_issue_payload", lambda *_args, **_kwargs: (None, "offline"))
    args = argparse.Namespace(
        issue_number="9",
        repo="repo/name",
        task_id="",
        output="",
        format="text",
        project_root=str(tmp_path / "project"),
    )
    assert runtime.command_issue_ingest(args) == 1
    assert "offline" in capsys.readouterr().err

    issue = {
        "number": 9,
        "url": "https://example.test/9",
        "title": "Issue title",
        "body": "body",
        "labels": [{"name": "bug"}],
        "comments": [{"body": "- must test", "createdAt": "2026-01-01T00:00:00Z", "url": "u"}],
    }
    monkeypatch.setattr(runtime, "load_issue_payload", lambda *_args, **_kwargs: (issue, ""))
    output = tmp_path / "issue.json"
    args.output = str(output)
    assert runtime.command_issue_ingest(args) == 0
    out = capsys.readouterr().out
    assert "ISSUE: 9" in out
    assert f"EVIDENCE: {output}" in out
    assert json.loads(output.read_text(encoding="utf-8"))["comment_count"] == 1
