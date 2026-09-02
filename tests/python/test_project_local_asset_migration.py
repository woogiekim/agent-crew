"""Automatic fail-closed migration for legacy project-local assets."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "core" / "scripts" / "project-local-asset-migration.py"
GENERATOR = (
    REPO_ROOT / "core" / "scripts" / "generate-project-local-asset-fingerprints.py"
)


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def git_blob_sha(content: bytes) -> str:
    prefix = b"blob " + str(len(content)).encode("ascii") + b"\0"
    return hashlib.sha1(prefix + content).hexdigest()


def load_migration_module():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("project_local_asset_migration", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_moves_only_owned_assets_and_writes_restore_manifest(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    codex_home = home / ".codex"
    claude_dir = home / ".claude"
    project.mkdir()
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)

    global_skill = write(
        agent_crew_home / "system" / "skills" / "tdd.md",
        "# Current global TDD skill\n",
    )
    global_readme = write(codex_home / "README.md", "# Global Codex README\n")
    global_config = write(
        agent_crew_home / "adapters" / "codex" / "template" / "config.toml",
        "[agents]\nmax_threads = 6\nmax_depth = 1\n",
    )
    legacy_invocation = b"# Legacy generated invocation\n"
    project_skill = write(
        project / ".agent-crew" / "agents" / "skills" / "tdd.md",
        global_skill.read_text(encoding="utf-8"),
    )
    project_invocation = project / ".agent-crew" / "invocation.md"
    project_invocation.parent.mkdir(parents=True, exist_ok=True)
    project_invocation.write_bytes(legacy_invocation)
    project_link = project / ".agent-crew" / "links" / "system-skills"
    project_link.parent.mkdir(parents=True, exist_ok=True)
    project_link.symlink_to(agent_crew_home / "system" / "skills")
    project_readme = write(
        project / ".codex" / "README.md",
        global_readme.read_text(encoding="utf-8"),
    )

    custom_agent = write(
        project / ".codex" / "agents" / "custom.toml",
        'name = "custom"\nowner = "project"\n',
    )
    modified_skill = write(
        project / ".agent-crew" / "agents" / "skills" / "custom.md",
        "# Project-owned custom skill\n",
    )
    tracked_config = write(
        project / ".codex" / "config.toml",
        global_config.read_text(encoding="utf-8"),
    )
    subprocess.run(
        ["git", "-C", str(project), "add", "-f", ".codex/config.toml"],
        check=True,
    )

    fingerprints = tmp_path / "fingerprints.json"
    fingerprints.write_text(
        json.dumps(
            {
                "version": 1,
                "paths": {
                    ".agent-crew/invocation.md": [
                        git_blob_sha(legacy_invocation),
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--agent-crew-home",
            str(agent_crew_home),
            "--codex-home",
            str(codex_home),
            "--claude-dir",
            str(claude_dir),
            "--fingerprints",
            str(fingerprints),
            "--mode",
            "setup",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "project_asset_migration: moved=4 preserved=3" in result.stdout
    assert not project_skill.exists()
    assert not project_invocation.exists()
    assert not project_link.exists()
    assert not project_readme.exists()
    assert custom_agent.read_text(encoding="utf-8") == 'name = "custom"\nowner = "project"\n'
    assert modified_skill.read_text(encoding="utf-8") == "# Project-owned custom skill\n"
    assert tracked_config.read_text(encoding="utf-8") == global_config.read_text(encoding="utf-8")

    backup_roots = list(
        (agent_crew_home / "backups" / "project-assets").glob("project-*/*")
    )
    assert len(backup_roots) == 1
    backup_root = backup_roots[0]
    restore = json.loads(
        (backup_root / "restore-manifest.json").read_text(encoding="utf-8")
    )
    result_payload = json.loads(
        (backup_root / "result.json").read_text(encoding="utf-8")
    )
    journal = json.loads(
        (backup_root / "journal.json").read_text(encoding="utf-8")
    )
    assert restore["status"] == "ready"
    assert len(restore["entries"]) == 4
    assert journal["status"] == "completed"
    assert [entry["status"] for entry in journal["entries"]] == ["moved"] * 4
    assert result_payload["status"] == "completed"
    assert result_payload["moved_count"] == 4
    assert result_payload["preserved_count"] == 3
    assert all(Path(entry["backup_path"]).exists() for entry in restore["entries"])

    repeated = subprocess.run(
        result.args,
        check=False,
        capture_output=True,
        text=True,
    )

    assert repeated.returncode == 0, repeated.stderr
    assert "project_asset_migration: moved=0 preserved=3 backup=none" in repeated.stdout
    assert len(
        list((agent_crew_home / "backups" / "project-assets").glob("project-*/*"))
    ) == 1


def test_migration_fails_closed_when_git_status_is_unavailable(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "not-a-git-project"
    agent_crew_home = home / ".agent-crew"
    codex_home = home / ".codex"
    claude_dir = home / ".claude"
    project.mkdir()
    global_skill = write(
        agent_crew_home / "system" / "skills" / "tdd.md",
        "# Current global TDD skill\n",
    )
    project_skill = write(
        project / ".agent-crew" / "agents" / "skills" / "tdd.md",
        global_skill.read_text(encoding="utf-8"),
    )
    fingerprints = write(tmp_path / "fingerprints.json", '{"version":1,"paths":{}}\n')

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--agent-crew-home",
            str(agent_crew_home),
            "--codex-home",
            str(codex_home),
            "--claude-dir",
            str(claude_dir),
            "--fingerprints",
            str(fingerprints),
            "--mode",
            "update",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "moved=0 preserved=1 skipped=git_status_unavailable" in result.stdout
    assert project_skill.is_file()
    assert not (agent_crew_home / "backups" / "project-assets").exists()


def test_migration_rolls_back_files_moved_before_a_failure(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_migration_module()
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    codex_home = home / ".codex"
    claude_dir = home / ".claude"
    project.mkdir()
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)

    global_skill = write(agent_crew_home / "system/skills/tdd.md", "skill\n")
    global_readme = write(codex_home / "README.md", "readme\n")
    project_skill = write(
        project / ".agent-crew/agents/skills/tdd.md",
        global_skill.read_text(encoding="utf-8"),
    )
    project_readme = write(
        project / ".codex/README.md",
        global_readme.read_text(encoding="utf-8"),
    )
    fingerprints = write(tmp_path / "fingerprints.json", '{"version":1,"paths":{}}\n')

    original_move = module.shutil.move
    source_moves = 0

    def fail_second_source_move(source: str, destination: str):
        nonlocal source_moves
        if Path(source).is_relative_to(project):
            source_moves += 1
            if source_moves == 2:
                raise OSError("simulated second move failure")
        return original_move(source, destination)

    monkeypatch.setattr(module.shutil, "move", fail_second_source_move)

    return_code = module.migrate(
        SimpleNamespace(
            project_root=str(project),
            agent_crew_home=str(agent_crew_home),
            codex_home=str(codex_home),
            claude_dir=str(claude_dir),
            fingerprints=str(fingerprints),
            mode="update",
        )
    )

    assert return_code == 1
    assert project_skill.read_text(encoding="utf-8") == "skill\n"
    assert project_readme.read_text(encoding="utf-8") == "readme\n"
    backup_roots = list(
        (agent_crew_home / "backups/project-assets").glob("project-*/*")
    )
    assert len(backup_roots) == 1
    result = json.loads((backup_roots[0] / "result.json").read_text(encoding="utf-8"))
    journal = json.loads((backup_roots[0] / "journal.json").read_text(encoding="utf-8"))
    assert result["status"] == "rolled_back"
    assert journal["status"] == "rolled_back"


def test_migration_recognizes_strict_codex_managed_markers(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    codex_home = home / ".codex"
    claude_dir = home / ".claude"
    project.mkdir()
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
    write(agent_crew_home / "hooks/auto-route.sh", "#!/usr/bin/env bash\n")

    managed_agent = write(
        project / ".codex/agents/backend.toml",
        'developer_instructions = """\n'
        "This is a Codex adapter bootstrap for the agent-crew system agent.\n"
        '"""\n',
    )
    managed_hooks = write(
        project / ".codex/hooks.json",
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"bash '{agent_crew_home}/hooks/auto-route.sh'",
                                    "timeout": 15,
                                }
                            ]
                        }
                    ]
                }
            }
        )
        + "\n",
    )
    fingerprints = write(tmp_path / "fingerprints.json", '{"version":1,"paths":{}}\n')

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--agent-crew-home",
            str(agent_crew_home),
            "--codex-home",
            str(codex_home),
            "--claude-dir",
            str(claude_dir),
            "--fingerprints",
            str(fingerprints),
            "--mode",
            "setup",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "moved=2 preserved=0" in result.stdout
    assert not managed_agent.exists()
    assert not managed_hooks.exists()


def test_migration_preserves_current_generic_invocation_reference(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    codex_home = home / ".codex"
    claude_dir = home / ".claude"
    project.mkdir()
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
    content = b"# Current minimal generic project reference\n"
    global_invocation = agent_crew_home / "adapters/generic/invocation.md"
    global_invocation.parent.mkdir(parents=True)
    global_invocation.write_bytes(content)
    project_invocation = project / ".agent-crew/invocation.md"
    project_invocation.parent.mkdir(parents=True)
    project_invocation.write_bytes(content)
    fingerprints = write(
        tmp_path / "fingerprints.json",
        json.dumps(
            {
                "version": 1,
                "paths": {
                    ".agent-crew/invocation.md": [git_blob_sha(content)]
                },
            }
        )
        + "\n",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--agent-crew-home",
            str(agent_crew_home),
            "--codex-home",
            str(codex_home),
            "--claude-dir",
            str(claude_dir),
            "--fingerprints",
            str(fingerprints),
            "--mode",
            "setup",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "moved=0 preserved=1 backup=none" in result.stdout
    assert project_invocation.read_bytes() == content


def test_fingerprint_generator_maps_historical_system_assets_by_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "-C", str(source), "init", "-q"], check=True)
    skill = write(source / "core/agents/skills/tdd.md", "version one\n")
    invocation = write(
        source / "adapters/generic/invocation.md", "legacy invocation\n"
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "add",
            ".",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "first",
        ],
        check=True,
    )
    first_skill_sha = git_blob_sha(skill.read_bytes())
    invocation_sha = git_blob_sha(invocation.read_bytes())
    skill.write_text("version two\n", encoding="utf-8")
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qam",
            "second",
        ],
        check=True,
    )
    second_skill_sha = git_blob_sha(skill.read_bytes())
    output = tmp_path / "fingerprints.json"

    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--source-root",
            str(source),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    expected_skill_shas = sorted([first_skill_sha, second_skill_sha])
    assert payload["paths"][".agent-crew/agents/skills/tdd.md"] == expected_skill_shas
    assert payload["paths"][".agent-crew/skills/tdd.md"] == expected_skill_shas
    assert payload["paths"][".agent-crew/invocation.md"] == [invocation_sha]


def test_migration_preserves_codex_hooks_with_user_owned_content(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    codex_home = home / ".codex"
    claude_dir = home / ".claude"
    project.mkdir()
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
    content = json.dumps(
        {
            "custom_top": {"keep": True},
            "hooks": {
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "bash /tmp/project-stop.sh",
                            }
                        ]
                    }
                ]
            },
        }
    ) + "\n"
    write(codex_home / "hooks.json", content)
    project_hooks = write(project / ".codex/hooks.json", content)
    custom_config = 'model = "project-choice"\n[agents]\ncustom_mode = "keep"\n'
    write(codex_home / "config.toml", custom_config)
    project_config = write(project / ".codex/config.toml", custom_config)
    fingerprints = write(tmp_path / "fingerprints.json", '{"version":1,"paths":{}}\n')

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project-root",
            str(project),
            "--agent-crew-home",
            str(agent_crew_home),
            "--codex-home",
            str(codex_home),
            "--claude-dir",
            str(claude_dir),
            "--fingerprints",
            str(fingerprints),
            "--mode",
            "update",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "moved=0 preserved=2 backup=none" in result.stdout
    assert project_hooks.read_text(encoding="utf-8") == content
    assert project_config.read_text(encoding="utf-8") == custom_config
