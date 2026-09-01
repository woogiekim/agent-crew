import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "core" / "scripts" / "project-agent-mirror-inventory.py"
SYSTEM_MARKER = "This is a Codex adapter bootstrap for the agent-crew system agent."
USER_MARKER = "# This is a Codex adapter bootstrap for an agent-crew user agent."


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_inventory_classifies_managed_duplicates_without_deleting_files(tmp_path: Path):
    agent_crew_home = tmp_path / "home" / ".agent-crew"
    codex_home = tmp_path / "home" / ".codex"
    claude_dir = tmp_path / "home" / ".claude"
    projects = tmp_path / "projects"
    manifest = tmp_path / "manifest.json"

    backend_md = "---\nname: backend\n---\nSystem backend instructions.\n"
    scout_md = "---\nname: scout\n---\nUser scout instructions.\n"
    write(agent_crew_home / "system" / "agents" / "backend.md", backend_md)
    write(agent_crew_home / "user" / "agents" / "scout.md", scout_md)
    write(
        codex_home / "agents" / "backend.toml",
        f'developer_instructions = """{SYSTEM_MARKER}"""\n',
    )
    global_scout = (
        f"{USER_MARKER}\n"
        'name = "scout"\n'
        'description = "User scout"\n'
        'developer_instructions = """\nUser scout instructions.\n"""\n'
    )
    write(codex_home / "agents" / "scout.toml", global_scout)
    write(claude_dir / "agents" / "scout.md", scout_md)

    managed_codex = write(
        projects / "alpha" / ".codex" / "agents" / "backend.toml",
        f'developer_instructions = """{SYSTEM_MARKER}"""\n',
    )
    stale_managed_codex = write(
        projects / "alpha" / ".codex" / "agents" / "retired-system.toml",
        f'developer_instructions = """{SYSTEM_MARKER}"""\n',
    )
    legacy_user_codex = write(
        projects / "alpha" / ".codex" / "agents" / "scout.toml",
        global_scout.removeprefix(USER_MARKER + "\n"),
    )
    project_override = write(
        projects / "alpha" / ".codex" / "agents" / "local-custom.toml",
        'name = "local-custom"\n',
    )
    missing_global_user = write(
        agent_crew_home / "user" / "agents" / "missing-global.md",
        "---\nname: missing-global\n---\nMissing global source.\n",
    )
    missing_global_toml = write(
        projects / "alpha" / ".codex" / "agents" / "missing-global.toml",
        'name = "missing-global"\n',
    )
    duplicate_md = write(
        projects / "alpha" / ".agent-crew" / "agents" / "backend.md",
        backend_md,
    )
    modified_md = write(
        projects / "beta" / ".agent-crew" / "agents" / "backend.md",
        backend_md + "Project modification.\n",
    )
    claude_duplicate = write(
        projects / "alpha" / ".claude" / "agents" / "scout.md",
        scout_md,
    )
    claude_override = write(
        projects / "alpha" / ".claude" / "agents" / "local-reviewer.md",
        "Project-only Claude agent.\n",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(projects),
            "--agent-crew-home",
            str(agent_crew_home),
            "--codex-home",
            str(codex_home),
            "--claude-dir",
            str(claude_dir),
            "--output",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    actions = {entry["path"]: entry["action"] for entry in payload["entries"]}
    assert payload["mode"] == "dry-run"
    assert actions[str(managed_codex)] == "quarantine_managed"
    assert actions[str(stale_managed_codex)] == "quarantine_stale_managed"
    assert actions[str(legacy_user_codex)] == "quarantine_after_global"
    assert actions[str(project_override)] == "preserve_project_override"
    assert actions[str(missing_global_toml)] == "block_missing_global"
    assert actions[str(duplicate_md)] == "quarantine_duplicate"
    assert actions[str(modified_md)] == "review_modified_or_stale"
    assert actions[str(claude_duplicate)] == "quarantine_after_global"
    assert actions[str(claude_override)] == "preserve_project_override"
    assert missing_global_user.exists()

    for path in (
        managed_codex,
        stale_managed_codex,
        legacy_user_codex,
        project_override,
        missing_global_toml,
        duplicate_md,
        modified_md,
        claude_duplicate,
        claude_override,
    ):
        assert path.exists()
