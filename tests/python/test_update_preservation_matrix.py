"""Fixture matrix for update preservation of user-owned customizations."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRESERVATION = REPO_ROOT / "core" / "scripts" / "update-preservation-manifest.py"


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
