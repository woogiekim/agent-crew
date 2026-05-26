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
    task_dirs = sorted((tmp_path / "home" / "state" / project.name / "tasks").iterdir())
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
    task_dirs = sorted((tmp_path / "home" / "state" / project.name / "tasks").iterdir())
    register = json.loads((task_dirs[-1] / "register.json").read_text(encoding="utf-8"))
    assert register["host_bridge_failure_reason"] == "bridge_reported_blocked"


def test_command_agent_error_paths(monkeypatch, tmp_path: Path, capsys):
    root = tmp_path / "runtime-root"
    _write_registry(root)
    (root / "project").mkdir()

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
