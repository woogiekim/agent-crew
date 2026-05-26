"""Tests for AGENT_CREW_HOST_BRIDGE_COMMAND diagnostic helper."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "core" / "scripts" / "check-host-bridge.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_host_bridge", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # noqa: S102
    return mod


def test_missing_command_is_warning():
    checker = _load_checker()
    result = checker.inspect_bridge_command("")
    assert result["status"] == "missing"
    assert result["ready"] is False
    assert checker._resolve_executable("")[2] == "missing"


def test_unbalanced_quote_is_parse_error(script_runner):
    env = os.environ.copy()
    env.pop("AGENT_CREW_HOST_BRIDGE_COMMAND", None)
    env["AGENT_CREW_HOST_BRIDGE_COMMAND"] = 'echo "unterminated'
    cp = script_runner("check-host-bridge.py", "--json", env=env)
    assert cp.returncode == 2
    payload = {"status": "parse_error", "ready": False}
    import json

    decoded = json.loads(cp.stdout)
    assert decoded["status"] == payload["status"]
    assert decoded["ready"] == payload["ready"]


def test_absolute_path_command_report_ready(tmp_path, script_runner):
    checker_script = tmp_path / "host-bridge.sh"
    checker_script.write_text("#!/bin/sh\necho bridge-hit \"$AGENT_CREW_TASK_ID\" \"$AGENT_CREW_TASK_DIR\" >/dev/null\n", encoding="utf-8")
    checker_script.chmod(0o755)

    env = os.environ.copy()
    env.pop("AGENT_CREW_HOST_BRIDGE_COMMAND", None)
    env["AGENT_CREW_HOST_BRIDGE_COMMAND"] = str(checker_script)
    cp = script_runner("check-host-bridge.py", "--json", env=env)
    assert cp.returncode == 0

    import json
    decoded = json.loads(cp.stdout)
    assert decoded["status"] == "ready"
    assert decoded["ready"] is True
    assert decoded["executable"] == str(checker_script)


def test_path_executable_validation_failures(tmp_path: Path):
    checker = _load_checker()
    missing = tmp_path / "missing-bridge"
    assert checker._resolve_executable(str(missing))[2] == "not_found"
    assert checker._resolve_executable(str(tmp_path))[2] == "not_file"

    not_executable = tmp_path / "bridge.sh"
    not_executable.write_text("#!/bin/sh\n", encoding="utf-8")
    not_executable.chmod(0o644)
    assert checker._resolve_executable(str(not_executable))[2] == "not_executable"
    assert checker._resolve_executable("definitely-not-on-path-agent-bridge")[2] == "not_found"

    relative = Path("relative") / "missing-bridge"
    resolved, _reason, status = checker._resolve_executable(str(relative))
    assert status == "not_found"
    assert resolved.endswith(str(relative))


def test_lookup_in_path_is_ready(tmp_path, script_runner):
    bridge_bin = tmp_path / "bin"
    bridge_bin.mkdir()
    bridge_exe = bridge_bin / "agent-bridge"
    bridge_exe.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    bridge_exe.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bridge_bin}:{env.get('PATH', '')}"
    env.pop("AGENT_CREW_HOST_BRIDGE_COMMAND", None)
    env["AGENT_CREW_HOST_BRIDGE_COMMAND"] = "agent-bridge --json"

    cp = script_runner("check-host-bridge.py", "--json", env=env)
    assert cp.returncode == 0
    import json

    decoded = json.loads(cp.stdout)
    assert decoded["status"] == "ready"
    assert decoded["ready"] is True
    assert decoded["command_head"] == "agent-bridge"


def test_missing_command_uses_installed_adapter_default(tmp_path: Path):
    checker = _load_checker()
    home = tmp_path / "home"
    project = tmp_path / "project"
    bridge = home / "adapters" / "codex" / "bin" / "codex-host-bridge"
    caps = home / "state" / project.name / "capabilities.json"
    bridge.parent.mkdir(parents=True)
    caps.parent.mkdir(parents=True)
    bridge.write_text("#!/bin/sh\necho bridge\n", encoding="utf-8")
    bridge.chmod(0o755)
    caps.write_text('{"host":"codex"}', encoding="utf-8")

    default = checker.default_bridge_command(agent_crew_home=home, project_root=project)
    result = checker.inspect_bridge_command("", default_command=default)

    assert result["ready"] is True
    assert result["defaulted"] is True
    assert result["command_effective"] == str(bridge)
    assert result["status"] == "ready"


def test_default_bridge_can_be_disabled(monkeypatch, tmp_path: Path):
    checker = _load_checker()
    monkeypatch.setenv("AGENT_CREW_HOST_BRIDGE_DISABLE_DEFAULT", "1")

    assert checker.default_bridge_command(agent_crew_home=tmp_path, project_root=tmp_path, host="codex") == ""


def test_default_bridge_handles_invalid_capabilities_and_unknown_hosts(tmp_path: Path):
    checker = _load_checker()
    home = tmp_path / "home"
    project = tmp_path / "project"
    caps = home / "state" / project.name / "capabilities.json"
    caps.parent.mkdir(parents=True)
    caps.write_text("{not json", encoding="utf-8")

    assert checker.default_bridge_command(agent_crew_home=home, project_root=project) == ""
    assert checker.default_bridge_command(agent_crew_home=home, project_root=project, host="unknown") == ""
    assert checker.default_bridge_command(agent_crew_home=home, project_root=project, host="codex") == ""


def test_defaulted_parse_error_and_empty_argv_are_reported(monkeypatch):
    checker = _load_checker()

    defaulted = checker.inspect_bridge_command("", default_command="'unterminated")
    assert defaulted["status"] == "parse_error"
    assert "default host bridge command" in defaulted["reason"]

    monkeypatch.setattr(checker.shlex, "split", lambda _command: [])
    empty = checker.inspect_bridge_command("agent-bridge")
    assert empty["status"] == "empty"


def test_main_returns_one_for_empty_split(monkeypatch, capsys):
    checker = _load_checker()
    monkeypatch.setattr(checker.shlex, "split", lambda _command: [])
    monkeypatch.setattr(checker.sys, "argv", ["check-host-bridge.py", "--command", "agent-bridge"])

    assert checker.main() == 1
    assert "NOT READY: empty" in capsys.readouterr().out


def test_text_output_includes_default_argv_and_exec(tmp_path: Path):
    bridge = tmp_path / "bridge.sh"
    bridge.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    bridge.chmod(0o755)

    result = subprocess.run(
        ["python3", str(SCRIPT_PATH), "--command", f"{bridge} --flag"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "READY: ready" in result.stdout
    assert "ARGV:" in result.stdout
    assert f"EXEC: {bridge}" in result.stdout
    assert "REASON:" in result.stdout


def test_text_output_includes_default_command(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    bridge = home / "adapters" / "codex" / "bin" / "codex-host-bridge"
    bridge.parent.mkdir(parents=True)
    project.mkdir()
    bridge.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    bridge.chmod(0o755)

    env = os.environ.copy()
    env["AGENT_CREW_HOME"] = str(home)
    env["AGENT_CREW_HOST"] = "codex"
    env["PROJECT_ROOT"] = str(project)
    env.pop("AGENT_CREW_HOST_BRIDGE_COMMAND", None)

    result = subprocess.run(
        ["python3", str(SCRIPT_PATH)],
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 0
    assert "DEFAULT:" in result.stdout
    assert str(bridge) in result.stdout
