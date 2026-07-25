"""Focused coverage for the crew relay command."""

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


runtime = _load_module(RUNTIME, "crew_runtime_relay")


def _args(project: Path, *prompt: str, **overrides) -> argparse.Namespace:
    values = {
        "project_root": str(project),
        "to": "claude",
        "mode": "ask",
        "from_task": "",
        "paths": [],
        "copy": False,
        "prompt": list(prompt),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _single_relay_dir(home: Path) -> Path:
    relay_dirs = list((home / "state").glob("*/relays/*"))
    assert len(relay_dirs) == 1
    return relay_dirs[0]


def test_success_case_relay_writes_local_prompt_package(monkeypatch, tmp_path: Path, capsys):
    """success-case - relay packages a target prompt locally without launching another host."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AGENT_CREW_HOME", str(home))

    exit_code = runtime.command_relay(
        _args(
            project,
            "Investigate hook latency",
            to="claude",
            mode="debug",
            paths=["core/hooks/auto-route.sh"],
        )
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    relay_dir = _single_relay_dir(home)
    manifest = json.loads((relay_dir / "manifest.json").read_text(encoding="utf-8"))
    context = json.loads((relay_dir / "context.json").read_text(encoding="utf-8"))
    prompt = (relay_dir / "prompt.md").read_text(encoding="utf-8")

    assert "STATUS: completed" in out
    assert manifest["target_host"] == "claude"
    assert manifest["mode"] == "debug"
    assert manifest["copy_requested"] is False
    assert context["paths"] == ["core/hooks/auto-route.sh"]
    assert "TARGET_HOST: claude" in prompt
    assert "Investigate hook latency" in prompt
    assert "Do not execute remote, push, deploy, merge, or destructive actions" in prompt


def test_success_case_relay_from_task_embeds_existing_task_context(monkeypatch, tmp_path: Path):
    """success-case - relay can package handoff/result context from an existing task."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AGENT_CREW_HOME", str(home))
    state_info = runtime.resolve_project_state(home=home, project_root=project, ensure=True, migrate_legacy=True)
    task_dir = Path(state_info["state_dir"]) / "tasks" / "20260725-010203-0"
    task_dir.mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({"task_id": task_dir.name, "task": "Original task body"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (task_dir / "handoff.md").write_text("HANDOFF: keep this context", encoding="utf-8")
    (task_dir / "result.md").write_text("RESULT: previous finding", encoding="utf-8")

    exit_code = runtime.command_relay(_args(project, to="codex", from_task=task_dir.name))

    assert exit_code == 0
    relay_dir = _single_relay_dir(home)
    manifest = json.loads((relay_dir / "manifest.json").read_text(encoding="utf-8"))
    prompt = (relay_dir / "prompt.md").read_text(encoding="utf-8")

    assert manifest["from_task"] == task_dir.name
    assert "Original task body" in prompt
    assert "HANDOFF: keep this context" in prompt
    assert "RESULT: previous finding" in prompt


def test_success_case_relay_copy_uses_clipboard_only(monkeypatch, tmp_path: Path):
    """success-case - --copy sends the packaged prompt to pbcopy, not another AI session."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    calls: list[dict] = []
    monkeypatch.setenv("AGENT_CREW_HOME", str(home))
    monkeypatch.setattr(runtime, "clipboard_available", lambda: True)

    def fake_run(argv, **kwargs):
        calls.append({"argv": argv, "kwargs": kwargs})

        class Completed:
            returncode = 0

        return Completed()

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)

    exit_code = runtime.command_relay(_args(project, "Send this prompt", copy=True))

    assert exit_code == 0
    pbcopy_calls = [call for call in calls if call["argv"] == ["pbcopy"]]
    assert len(pbcopy_calls) == 1
    assert "Send this prompt" in pbcopy_calls[0]["kwargs"]["input"]
    assert all("claude-host-bridge" not in " ".join(call["argv"]) for call in calls)
    assert all("codex-host-bridge" not in " ".join(call["argv"]) for call in calls)


def test_success_case_parser_accepts_relay_command():
    """success-case - runtime parser exposes the relay subcommand."""
    parser = runtime.build_parser()

    args = parser.parse_args(["relay", "--to", "gemini", "--mode", "review", "--paths", "a.py", "Review this"])

    assert args.func is runtime.command_relay
    assert args.to == "gemini"
    assert args.mode == "review"
    assert args.paths == ["a.py"]
    assert args.prompt == ["Review this"]


def test_e2e_case_crew_bin_relay_writes_package(tmp_path: Path):
    """e2e-case - core/bin/crew dispatches relay and writes the package files."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "AGENT_CREW_HOME": str(home),
            "PROJECT_ROOT": str(project),
        }
    )

    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "core" / "bin" / "crew"),
            "relay",
            "--to",
            "claude",
            "--mode",
            "review",
            "--paths",
            "core/bin/crew",
            "Review relay package e2e",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS: completed" in result.stdout
    prompt_line = next(line for line in result.stdout.splitlines() if line.startswith("PROMPT: "))
    prompt_path = Path(prompt_line.removeprefix("PROMPT: "))
    relay_dir = prompt_path.parent
    manifest = json.loads((relay_dir / "manifest.json").read_text(encoding="utf-8"))
    context = json.loads((relay_dir / "context.json").read_text(encoding="utf-8"))
    prompt = prompt_path.read_text(encoding="utf-8")

    assert relay_dir.is_relative_to(home / "state")
    assert manifest["target_host"] == "claude"
    assert manifest["mode"] == "review"
    assert manifest["auto_execute"] is False
    assert context["paths"] == ["core/bin/crew"]
    assert "TARGET_HOST: claude" in prompt
    assert "Review relay package e2e" in prompt
    assert (relay_dir / "copy.txt").read_text(encoding="utf-8") == prompt
