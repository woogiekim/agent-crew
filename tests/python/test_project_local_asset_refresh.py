"""Global asset setup/update contract tests."""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CREW = REPO_ROOT / "core" / "bin" / "crew"
COMMON = REPO_ROOT / "core" / "setup" / "common.sh"
CODEX_SETUP = REPO_ROOT / "adapters" / "codex" / "setup.sh"
GENERIC_SETUP = REPO_ROOT / "adapters" / "generic" / "setup.sh"
SYNC_LOCAL_INSTALL = REPO_ROOT / "core" / "scripts" / "sync-local-install.sh"
UPDATE_DOC = REPO_ROOT / "core" / "commands" / "update.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def bootstrap_codex_install(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    codex_home = home / ".codex"
    project.mkdir()

    (agent_crew_home / "setup").mkdir(parents=True)
    (agent_crew_home / "commands").mkdir()
    (agent_crew_home / "hooks").mkdir()
    (agent_crew_home / "skills").mkdir()
    (agent_crew_home / "system" / "agents").mkdir(parents=True)
    (agent_crew_home / "system" / "scripts").mkdir(parents=True)
    (agent_crew_home / "user" / "agents").mkdir(parents=True)
    (agent_crew_home / "adapters" / "codex").mkdir(parents=True)
    (agent_crew_home / "adapters" / "codex" / "template").mkdir(parents=True)
    (agent_crew_home / "AGENTS.md").write_text(
        "<!-- agent-crew-start -->\nmanaged\n<!-- agent-crew-end -->\n",
        encoding="utf-8",
    )
    (agent_crew_home / "setup" / "common.sh").symlink_to(COMMON)
    (agent_crew_home / "adapters" / "codex" / "invocation.md").write_text(
        "invoke\n",
        encoding="utf-8",
    )
    (agent_crew_home / "adapters" / "codex" / "template" / "config.toml").write_text(
        "[agents]\nmax_threads = 6\nmax_depth = 1\n",
        encoding="utf-8",
    )
    (agent_crew_home / "system" / "scripts" / "generate-codex-system-agents.py").write_text(
        (REPO_ROOT / "core" / "scripts" / "generate-codex-system-agents.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (agent_crew_home / "system" / "agents" / "backend.md").write_text(
        "---\nname: backend\ndescription: system backend\n---\n# Backend\n",
        encoding="utf-8",
    )
    (agent_crew_home / "user" / "agents" / "custom.md").write_text(
        "---\nname: custom\ndescription: user custom\n---\n# User Custom\n",
        encoding="utf-8",
    )
    for hook_name in (
        "guard-dangerous-commands.sh",
        "post-tool-use-dispatcher.sh",
        "auto-issue-report.sh",
        "auto-route.sh",
    ):
        (agent_crew_home / "hooks" / hook_name).write_text(
            "#!/usr/bin/env bash\nexit 0\n",
            encoding="utf-8",
        )

    env = os.environ | {
        "AGENT_CREW_HOME": str(agent_crew_home),
        "CODEX_HOME": str(codex_home),
        "HOME": str(home),
        "AGENT_CREW_DISABLE_SYMLINKS": "1",
    }

    return agent_crew_home, codex_home, project, env


def test_setup_host_deprecates_registered_project_fanout():
    text = read(CREW)

    assert "AGENT_CREW_PROJECT_LOCAL_ONLY=1" not in text
    assert "update_registered_projects" not in text
    assert "--all-projects is deprecated" in text


def test_generic_adapter_keeps_only_minimal_project_reference():
    text = read(GENERIC_SETUP)

    assert ".agent-crew/project/commands" not in text
    assert ".agent-crew/links/user-commands" not in text
    assert "merge_agents_to_discovery" not in text
    assert 'copy_file_if_changed "${AGENT_CREW_HOME}/adapters/generic/invocation.md"' in text
    assert "merge_agent_crew_section" not in text


def test_common_helper_supports_symlink_with_copy_fallback_and_never_overwrites_project_owned_dirs():
    text = read(COMMON)

    assert "link_or_copy_shared_dir" in text
    assert "AGENT_CREW_DISABLE_SYMLINKS" in text
    assert "project_owned_existing_dir" in text
    assert "fallback=copy" in text


def test_link_helper_links_new_dirs_and_falls_back_for_project_owned_dirs(tmp_path):
    src = tmp_path / "src"
    linked = tmp_path / "linked"
    copied = tmp_path / "copied"
    disabled = tmp_path / "disabled"
    env = os.environ | {"COMMON": str(COMMON), "SRC": str(src), "LINKED": str(linked), "COPIED": str(copied), "DISABLED": str(disabled)}

    src.mkdir()
    (src / "shared.md").write_text("shared\n", encoding="utf-8")
    copied.mkdir()
    (copied / "project-owned.md").write_text("keep\n", encoding="utf-8")
    script = r'''
set -euo pipefail
. "${COMMON}"
link_or_copy_shared_dir "${SRC}" "${LINKED}" "linked-case" >/dev/null
[ -L "${LINKED}" ]
link_or_copy_shared_dir "${SRC}" "${COPIED}" "owned-case" >/dev/null
[ ! -L "${COPIED}" ]
[ -f "${COPIED}/project-owned.md" ]
[ -f "${COPIED}/shared.md" ]
AGENT_CREW_DISABLE_SYMLINKS=1 link_or_copy_shared_dir "${SRC}" "${DISABLED}" "disabled-case" >/dev/null
[ ! -L "${DISABLED}" ]
[ -f "${DISABLED}/shared.md" ]
'''

    subprocess.run(["bash", "-c", script], check=True, env=env)


def test_codex_setup_installs_agents_and_hooks_globally_without_project_mirrors(tmp_path: Path):
    agent_crew_home, codex_home, project, env = bootstrap_codex_install(tmp_path)

    result = subprocess.run(
        ["bash", str(CODEX_SETUP), str(project)],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert (codex_home / "agents" / "backend.toml").is_file()
    assert (codex_home / "agents" / "custom.toml").is_file()
    assert (codex_home / "hooks.json").is_file()
    assert (codex_home / "config.toml").is_file()
    assert not (project / ".codex" / "agents").exists()
    assert not (project / ".codex" / "hooks").exists()
    assert not (project / ".codex" / "hooks.json").exists()
    assert not (project / "AGENTS.md").exists()
    assert "INSTALLED:" in result.stdout
    assert str(codex_home) in result.stdout
    assert (agent_crew_home / "state").is_dir()


def test_codex_setup_preserves_existing_project_override_without_refreshing_it(tmp_path: Path):
    _agent_crew_home, codex_home, project, env = bootstrap_codex_install(tmp_path)
    project_agent = project / ".codex" / "agents" / "backend.toml"
    project_agent.parent.mkdir(parents=True)
    project_content = 'name = "backend"\ndeveloper_instructions = """project override"""\n'
    project_agent.write_text(project_content, encoding="utf-8")

    subprocess.run(
        ["bash", str(CODEX_SETUP), str(project)],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert project_agent.read_text(encoding="utf-8") == project_content
    assert (codex_home / "agents" / "backend.toml").is_file()
    assert "project override" not in (codex_home / "agents" / "backend.toml").read_text(encoding="utf-8")


def test_codex_setup_preserves_global_user_owned_codex_assets(tmp_path: Path):
    agent_crew_home, codex_home, project, env = bootstrap_codex_install(tmp_path)
    custom_agent = codex_home / "agents" / "my-custom.toml"
    custom_agent.parent.mkdir(parents=True)
    custom_agent.write_text('name = "my-custom"\n', encoding="utf-8")
    known_name_custom_agent = codex_home / "agents" / "task-runner.toml"
    known_name_custom_agent.write_text('name = "task-runner"\nowner = "user"\n', encoding="utf-8")
    stale_managed_agent = codex_home / "agents" / "input-normalizer.toml"
    stale_managed_agent.write_text(
        'developer_instructions = """This is a Codex adapter bootstrap for the agent-crew system agent."""\n',
        encoding="utf-8",
    )
    (codex_home / "hooks.json").write_text(
        json.dumps(
            {
                "custom_top": {"keep": True},
                "hooks": {
                    "UserPromptSubmit": [
                        {
                            "matcher": "custom",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "bash /tmp/user/hooks/auto-route.sh",
                                    "timeout": 3,
                                },
                                {
                                    "type": "command",
                                    "command": f"bash '{agent_crew_home}/hooks/auto-route.sh'",
                                    "timeout": 1,
                                }
                            ],
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "bash /tmp/custom-stop.sh",
                                    "timeout": 4,
                                }
                            ]
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (codex_home / "config.toml").write_text(
        'model = "gpt-test"\n\n[agents]\nmax_threads = 2\ncustom_mode = "keep"\n',
        encoding="utf-8",
    )

    subprocess.run(
        ["bash", str(CODEX_SETUP), str(project)],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert custom_agent.read_text(encoding="utf-8") == 'name = "my-custom"\n'
    assert known_name_custom_agent.read_text(encoding="utf-8") == 'name = "task-runner"\nowner = "user"\n'
    assert not stale_managed_agent.exists()
    hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["custom_top"] == {"keep": True}
    assert "bash /tmp/user/hooks/auto-route.sh" in json.dumps(hooks)
    assert "bash /tmp/custom-stop.sh" in json.dumps(hooks)
    assert json.dumps(hooks).count(f"{agent_crew_home}/hooks/auto-route.sh") == 1
    config = (codex_home / "config.toml").read_text(encoding="utf-8")
    assert 'custom_mode = "keep"' in config
    assert "max_threads = 6" in config
    assert "max_depth = 1" in config


def test_codex_setup_refuses_to_overwrite_malformed_global_hooks_json(tmp_path: Path):
    _agent_crew_home, codex_home, project, env = bootstrap_codex_install(tmp_path)
    hooks_json = codex_home / "hooks.json"
    hooks_json.parent.mkdir(parents=True)
    hooks_json.write_text("{not-json\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(CODEX_SETUP), str(project)],
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode != 0
    assert hooks_json.read_text(encoding="utf-8") == "{not-json\n"
    assert "Refusing to overwrite non-object or malformed Codex hooks.json" in result.stderr


def test_codex_setup_refuses_to_overwrite_non_object_global_hooks_schema(tmp_path: Path):
    _agent_crew_home, codex_home, project, env = bootstrap_codex_install(tmp_path)
    hooks_json = codex_home / "hooks.json"
    hooks_json.parent.mkdir(parents=True)
    hooks_json.write_text('{"hooks": []}\n', encoding="utf-8")

    result = subprocess.run(
        ["bash", str(CODEX_SETUP), str(project)],
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode != 0
    assert hooks_json.read_text(encoding="utf-8") == '{"hooks": []}\n'
    assert "Refusing to overwrite unsupported Codex hooks.json schema" in result.stderr


def test_codex_setup_refuses_to_overwrite_malformed_required_hook_block(tmp_path: Path):
    _agent_crew_home, codex_home, project, env = bootstrap_codex_install(tmp_path)
    hooks_json = codex_home / "hooks.json"
    hooks_json.parent.mkdir(parents=True)
    original = '{"hooks": {"UserPromptSubmit": [{"hooks": ["not-object"]}]}}\n'
    hooks_json.write_text(original, encoding="utf-8")

    result = subprocess.run(
        ["bash", str(CODEX_SETUP), str(project)],
        check=False,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode != 0
    assert hooks_json.read_text(encoding="utf-8") == original
    assert "Refusing to overwrite unsupported Codex hooks.json schema" in result.stderr


def test_sync_local_install_does_not_refresh_project_adapter_files(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    codex_home = home / ".codex"
    claude_dir = home / ".claude"
    path_bin = home / ".local" / "bin"
    project.mkdir()
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)

    env = os.environ | {
        "HOME": str(home),
        "AGENT_CREW_HOME": str(agent_crew_home),
        "CODEX_HOME": str(codex_home),
        "CLAUDE_DIR": str(claude_dir),
        "AGENT_CREW_PATH_BIN": str(path_bin),
        "AGENT_CREW_DISABLE_FAST_NOOP_UPDATE": "1",
        "AGENT_CREW_WRITE_INSTALL_MANIFEST": "0",
    }

    subprocess.run(
        ["bash", str(SYNC_LOCAL_INSTALL), str(REPO_ROOT), str(project)],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert (agent_crew_home / "system" / "agents" / "supervisor.md").is_file()
    assert (codex_home / "agents" / "supervisor.toml").is_file()
    assert not (project / ".agent-crew").exists()
    assert not (project / ".codex").exists()
    assert not (project / "AGENTS.md").exists()


def test_update_docs_define_global_only_refresh_policy():
    text = read(UPDATE_DOC)

    assert "global-only" in text
    assert "--all-projects is deprecated" in text
    assert "does not refresh project-local mirrors" in text
    assert "project overrides" in text
