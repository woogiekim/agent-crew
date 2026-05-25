"""Tests for AGENT_CREW_HOST_BRIDGE_COMMAND diagnostic helper."""

from __future__ import annotations

import importlib.util
import os
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
