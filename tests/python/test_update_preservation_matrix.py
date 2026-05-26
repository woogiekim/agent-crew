"""Fixture matrix for update preservation of user-owned customizations."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRESERVATION = REPO_ROOT / "core" / "scripts" / "update-preservation-manifest.py"


def load_preservation_module():
    spec = importlib.util.spec_from_file_location("update_preservation_manifest", PRESERVATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def run_manifest(tmp_path: Path, files: dict[str, str], *, mutate=None) -> dict:
    agent_home = tmp_path / "agent-home"
    project = tmp_path / "project"
    codex_home = tmp_path / "codex-home"
    claude_dir = tmp_path / "claude"
    project.mkdir(parents=True)

    for rel, content in files.items():
        root_name, path = rel.split("/", 1)
        roots = {
            "agent": agent_home,
            "project": project,
            "codex": codex_home,
            "claude": claude_dir,
        }
        write(roots[root_name] / path, content)

    env = os.environ.copy()
    env.update({"CODEX_HOME": str(codex_home), "CLAUDE_DIR": str(claude_dir)})
    begin = subprocess.run(
        [
            "python3",
            str(PRESERVATION),
            "begin",
            "--agent-crew-home",
            str(agent_home),
            "--project-root",
            str(project),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    assert begin.returncode == 0, begin.stdout + begin.stderr
    manifest = Path(begin.stdout.strip())

    if mutate:
        mutate(agent_home, project, codex_home, claude_dir)

    finish = subprocess.run(
        [
            "python3",
            str(PRESERVATION),
            "finish",
            "--manifest",
            str(manifest),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    payload = json.loads(finish.stdout)
    return payload


def test_preservation_matrix_keeps_realistic_customization_cases(tmp_path: Path):
    cases = {
        "user agent": {
            "agent/user/agents/custom-agent.md": "---\nname: custom-agent\n---\ncustom\n",
        },
        "user skill": {
            "agent/user/skills/custom-skill.md": "# custom skill\n",
        },
        "conflicting user agent name": {
            "agent/user/agents/backend.md": "---\nname: backend\n---\nuser backend\n",
        },
        "conflicting user skill name": {
            "agent/user/skills/tdd.md": "# user tdd override\n",
        },
        "modified scribe user agent": {
            "agent/user/agents/scribe.md": "---\nname: scribe\n---\nuser modified scribe\n",
        },
        "project codex custom toml": {
            "project/.codex/agents/custom.toml": 'name = "custom"\n',
        },
        "project codex conflicting toml": {
            "project/.codex/agents/backend.toml": 'name = "backend"\ndeveloper_instructions = """user custom backend"""\n',
        },
        "global codex config": {
            "codex/config.toml": "model = \"gpt-test\"\n",
        },
        "project codex config": {
            "project/.codex/config.toml": "sandbox_mode = \"workspace-write\"\n",
        },
        "project codex hooks": {
            "project/.codex/hooks.json": '{"hooks":{"UserPromptSubmit":[]}}\n',
        },
        "claude settings": {
            "claude/settings.json": '{"permissions":{"allow":[]}}\n',
        },
        "agent crew instructions": {
            "agent/AGENTS.md": "# custom global instructions\n",
        },
    }

    for index, (name, files) in enumerate(cases.items()):
        payload = run_manifest(tmp_path / f"case-{index}", files)
        assert payload["passed"] is True, name
        assert payload["deleted_custom_files"] == {
            "user_agents": [],
            "user_skills": [],
            "project_codex_agents": [],
        }
        assert payload["changed_settings"] == []


def test_preservation_matrix_reports_deleted_project_codex_custom_agent(tmp_path: Path):
    def mutate(_agent_home: Path, project: Path, _codex_home: Path, _claude_dir: Path) -> None:
        (project / ".codex" / "agents" / "custom.toml").unlink()

    payload = run_manifest(
        tmp_path,
        {"project/.codex/agents/custom.toml": 'name = "custom"\n'},
        mutate=mutate,
    )

    assert payload["passed"] is False
    assert payload["deleted_custom_files"]["project_codex_agents"] == ["custom.toml"]


def test_preservation_matrix_reports_changed_settings(tmp_path: Path):
    def mutate(_agent_home: Path, project: Path, _codex_home: Path, _claude_dir: Path) -> None:
        (project / ".codex" / "config.toml").write_text("model = \"changed\"\n", encoding="utf-8")

    payload = run_manifest(
        tmp_path,
        {"project/.codex/config.toml": "model = \"original\"\n"},
        mutate=mutate,
    )

    assert payload["passed"] is True
    assert payload["changed_settings"] == [str(tmp_path / "project" / ".codex" / "config.toml")]


def test_preservation_matrix_text_reports_deleted_files_and_changed_settings(tmp_path: Path):
    agent_home = tmp_path / "agent-home"
    project = tmp_path / "project"
    codex_home = tmp_path / "codex-home"
    claude_dir = tmp_path / "claude"
    custom_agent = write(project / ".codex" / "agents" / "custom.toml", 'name = "custom"\n')
    config = write(project / ".codex" / "config.toml", "model = \"original\"\n")
    project.mkdir(exist_ok=True)

    env = os.environ.copy()
    env.update({"CODEX_HOME": str(codex_home), "CLAUDE_DIR": str(claude_dir)})
    begin = subprocess.run(
        [
            "python3",
            str(PRESERVATION),
            "begin",
            "--agent-crew-home",
            str(agent_home),
            "--project-root",
            str(project),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    assert begin.returncode == 0, begin.stdout + begin.stderr
    manifest = Path(begin.stdout.strip())
    custom_agent.unlink()
    config.write_text("model = \"changed\"\n", encoding="utf-8")

    finish = subprocess.run(
        ["python3", str(PRESERVATION), "finish", "--manifest", str(manifest)],
        text=True,
        capture_output=True,
        env=env,
    )

    assert finish.returncode == 1
    assert "deleted_custom_files:" in finish.stdout
    assert "changed_settings:" in finish.stdout


def test_preservation_helpers_filter_generated_codex_agents(tmp_path: Path):
    module = load_preservation_module()
    agents = tmp_path / "agents"
    custom = write(agents / "custom.toml", 'name = "custom"\n')
    generated = write(agents / "supervisor.toml", module.CODEX_SYSTEM_AGENT_MARKER)
    legacy = write(agents / "backend.toml", "Agent-crew system agent: backend\n")

    snapshot = module.filtered_file_snapshot(agents, module.protected_project_codex_agent)

    assert snapshot["files"] == {
        "custom.toml": {
            "sha256": module.sha256_file(custom),
            "bytes": custom.stat().st_size,
        }
    }
    assert module.protected_project_codex_agent(generated) is False
    assert module.protected_project_codex_agent(legacy) is False


def test_preservation_changed_settings_reports_existence_changes(tmp_path: Path):
    module = load_preservation_module()
    settings = str(tmp_path / "config.toml")

    changed = module.changed_settings(
        {"settings": {settings: {"exists": True, "sha256": "old"}}},
        {"settings": {settings: {"exists": False}}},
    )

    assert changed == [settings]


def test_preservation_main_returns_two_for_unknown_command(monkeypatch):
    module = load_preservation_module()

    class Parser:
        def add_subparsers(self, **_kwargs):
            return self

        def add_parser(self, *_args, **_kwargs):
            return self

        def add_argument(self, *_args, **_kwargs):
            return None

        def parse_args(self):
            return argparse.Namespace(command="unknown")

    monkeypatch.setattr(module.argparse, "ArgumentParser", lambda **_kwargs: Parser())

    assert module.main() == 2
