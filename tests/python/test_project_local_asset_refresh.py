"""Project-local update mode and layered asset reference contract tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CREW = REPO_ROOT / "core" / "bin" / "crew"
COMMON = REPO_ROOT / "core" / "setup" / "common.sh"
CODEX_SETUP = REPO_ROOT / "adapters" / "codex" / "setup.sh"
CLAUDE_SETUP = REPO_ROOT / "adapters" / "claude" / "setup.sh"
GENERIC_SETUP = REPO_ROOT / "adapters" / "generic" / "setup.sh"
UPDATE_DOC = REPO_ROOT / "core" / "commands" / "update.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_all_projects_uses_project_local_only_mode_for_registered_project_fanout():
    text = read(CREW)

    assert "AGENT_CREW_PROJECT_LOCAL_ONLY=1" in text
    assert 'bash "${setup_script}" "${project_resolved}"' in text


def test_adapter_setups_have_project_local_only_guardrails():
    for setup in (CODEX_SETUP, CLAUDE_SETUP, GENERIC_SETUP):
        text = read(setup)
        assert "AGENT_CREW_PROJECT_LOCAL_ONLY" in text, setup

    codex = read(CODEX_SETUP)
    assert 'if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "0" ]' in codex
    assert "install_codex_skills" in codex
    assert "install_system_agents_codex" in codex
    assert "install_user_agents_codex" in codex

    claude = read(CLAUDE_SETUP)
    assert 'if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "1" ]' in claude
    assert "project-local-only" in claude
    assert 'merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${CLAUDE_DIR}/CLAUDE.md"' in claude
    assert claude.index('if [ "${AGENT_CREW_PROJECT_LOCAL_ONLY}" = "1" ]') < claude.index('merge_agent_crew_section "${AGENT_CREW_HOME}/AGENTS.md" "${CLAUDE_DIR}/CLAUDE.md"')


def test_common_helper_supports_symlink_with_copy_fallback_and_never_overwrites_project_owned_dirs():
    text = read(COMMON)

    assert "link_or_copy_shared_dir" in text
    assert "AGENT_CREW_DISABLE_SYMLINKS" in text
    assert "project_owned_existing_dir" in text
    assert "fallback=copy" in text


def test_generic_adapter_uses_layered_links_without_replacing_project_overrides():
    text = read(GENERIC_SETUP)

    assert ".agent-crew/project/commands" in text
    assert ".agent-crew/project/agents" in text
    assert ".agent-crew/project/skills" in text
    assert ".agent-crew/links/user-commands" in text
    assert ".agent-crew/links/system-commands" in text
    assert '".agent-crew/commands -> ~/.agent-crew/commands"' not in text
    assert "merge_agent_crew_section" in text


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


def test_link_helper_prunes_stale_files_for_managed_existing_dirs(tmp_path):
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    env = os.environ | {"COMMON": str(COMMON), "SRC": str(src), "DEST": str(dest)}

    src.mkdir()
    dest.mkdir()
    (src / "new.sh").write_text("new\n", encoding="utf-8")
    (dest / "old.sh").write_text("old\n", encoding="utf-8")
    script = r'''
set -euo pipefail
. "${COMMON}"
link_or_copy_shared_dir "${SRC}" "${DEST}" "managed-case" prune >/dev/null
[ ! -L "${DEST}" ]
[ -f "${DEST}/new.sh" ]
[ ! -e "${DEST}/old.sh" ]
'''

    subprocess.run(["bash", "-c", script], check=True, env=env)


def test_generic_project_local_only_does_not_scaffold_global_user_skill_files(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    project.mkdir()
    (agent_crew_home / "setup").mkdir(parents=True)
    (agent_crew_home / "commands").mkdir()
    (agent_crew_home / "hooks").mkdir()
    (agent_crew_home / "skills").mkdir()
    (agent_crew_home / "system" / "agents").mkdir(parents=True)
    (agent_crew_home / "user" / "agents").mkdir(parents=True)
    (agent_crew_home / "adapters" / "generic").mkdir(parents=True)
    (agent_crew_home / "AGENTS.md").write_text(
        "<!-- agent-crew-start -->\nmanaged\n<!-- agent-crew-end -->\n",
        encoding="utf-8",
    )
    (agent_crew_home / "adapters" / "generic" / "invocation.md").write_text(
        "invoke\n",
        encoding="utf-8",
    )
    (agent_crew_home / "setup" / "common.sh").symlink_to(COMMON)
    env = os.environ | {
        "AGENT_CREW_HOME": str(agent_crew_home),
        "AGENT_CREW_MODE": "update",
        "AGENT_CREW_PROJECT_LOCAL_ONLY": "1",
        "AGENT_CREW_DISABLE_SYMLINKS": "1",
    }

    subprocess.run(
        ["bash", str(GENERIC_SETUP), str(project)],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert not (agent_crew_home / "user" / "skills" / "README.md").exists()
    assert (project / ".agent-crew" / "project" / "commands").is_dir()
    assert not (project / ".agent-crew" / "project" / "commands").is_symlink()


def test_generic_same_name_agents_are_not_silently_overwritten(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    project.mkdir()
    (agent_crew_home / "setup").mkdir(parents=True)
    (agent_crew_home / "commands").mkdir()
    (agent_crew_home / "hooks").mkdir()
    (agent_crew_home / "skills").mkdir()
    (agent_crew_home / "system" / "agents").mkdir(parents=True)
    (agent_crew_home / "user" / "agents").mkdir(parents=True)
    (agent_crew_home / "adapters" / "generic").mkdir(parents=True)
    (agent_crew_home / "AGENTS.md").write_text(
        "<!-- agent-crew-start -->\nmanaged\n<!-- agent-crew-end -->\n",
        encoding="utf-8",
    )
    (agent_crew_home / "adapters" / "generic" / "invocation.md").write_text(
        "invoke\n",
        encoding="utf-8",
    )
    (agent_crew_home / "setup" / "common.sh").symlink_to(COMMON)
    (agent_crew_home / "system" / "agents" / "same.md").write_text("system\n", encoding="utf-8")
    (agent_crew_home / "user" / "agents" / "same.md").write_text("user\n", encoding="utf-8")
    (agent_crew_home / "user" / "agents" / "user-only.md").write_text("user-only\n", encoding="utf-8")
    (project / ".agent-crew" / "project" / "agents").mkdir(parents=True)
    (project / ".agent-crew" / "project" / "agents" / "same.md").write_text("project\n", encoding="utf-8")
    (project / ".agent-crew" / "project" / "agents" / "project-only.md").write_text("project-only\n", encoding="utf-8")
    env = os.environ | {
        "AGENT_CREW_HOME": str(agent_crew_home),
        "AGENT_CREW_MODE": "update",
        "AGENT_CREW_PROJECT_LOCAL_ONLY": "1",
        "AGENT_CREW_DISABLE_SYMLINKS": "1",
    }

    result = subprocess.run(
        ["bash", str(GENERIC_SETUP), str(project)],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert (
        project / ".agent-crew" / "agents" / "same.md"
    ).read_text(encoding="utf-8") == "system\n"
    assert (
        project / ".agent-crew" / "agents" / "user-only.md"
    ).read_text(encoding="utf-8") == "user-only\n"
    assert (
        project / ".agent-crew" / "agents" / "project-only.md"
    ).read_text(encoding="utf-8") == "project-only\n"
    assert "same.md exists in project/agents and an earlier agent layer" in result.stderr


def test_codex_setup_preserves_project_owned_same_name_agent_toml(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    project_agent = project / ".codex" / "agents" / "backend.toml"
    project.mkdir()
    (agent_crew_home / "setup").mkdir(parents=True)
    (agent_crew_home / "commands").mkdir()
    (agent_crew_home / "hooks").mkdir()
    (agent_crew_home / "skills").mkdir()
    (agent_crew_home / "system" / "agents").mkdir(parents=True)
    (agent_crew_home / "system" / "scripts").mkdir(parents=True)
    (agent_crew_home / "user" / "agents").mkdir(parents=True)
    (agent_crew_home / "adapters" / "codex").mkdir(parents=True)
    (agent_crew_home / "AGENTS.md").write_text(
        "<!-- agent-crew-start -->\nmanaged\n<!-- agent-crew-end -->\n",
        encoding="utf-8",
    )
    (agent_crew_home / "adapters" / "codex" / "invocation.md").write_text(
        "invoke\n",
        encoding="utf-8",
    )
    (agent_crew_home / "setup" / "common.sh").symlink_to(COMMON)
    (agent_crew_home / "system" / "scripts" / "generate-codex-system-agents.py").write_text(
        (REPO_ROOT / "core" / "scripts" / "generate-codex-system-agents.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (agent_crew_home / "system" / "agents" / "backend.md").write_text(
        "---\nname: backend\ndescription: system backend\n---\n# Backend\n",
        encoding="utf-8",
    )
    project_agent.parent.mkdir(parents=True)
    project_agent.write_text(
        'name = "backend"\ndeveloper_instructions = """project custom backend"""\n',
        encoding="utf-8",
    )
    env = os.environ | {
        "AGENT_CREW_HOME": str(agent_crew_home),
        "AGENT_CREW_MODE": "update",
        "AGENT_CREW_PROJECT_LOCAL_ONLY": "1",
        "AGENT_CREW_DISABLE_SYMLINKS": "1",
    }

    result = subprocess.run(
        ["bash", str(CODEX_SETUP), str(project)],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert project_agent.read_text(encoding="utf-8") == (
        'name = "backend"\ndeveloper_instructions = """project custom backend"""\n'
    )
    assert "backend.toml exists in project .codex/agents and generated system agents" in result.stderr


def test_codex_setup_preserves_project_owned_same_name_user_agent_toml(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    agent_crew_home = home / ".agent-crew"
    project_agent = project / ".codex" / "agents" / "custom.toml"
    project.mkdir()
    (agent_crew_home / "setup").mkdir(parents=True)
    (agent_crew_home / "commands").mkdir()
    (agent_crew_home / "hooks").mkdir()
    (agent_crew_home / "skills").mkdir()
    (agent_crew_home / "system" / "agents").mkdir(parents=True)
    (agent_crew_home / "system" / "scripts").mkdir(parents=True)
    (agent_crew_home / "user" / "agents").mkdir(parents=True)
    (agent_crew_home / "adapters" / "codex").mkdir(parents=True)
    (agent_crew_home / "AGENTS.md").write_text(
        "<!-- agent-crew-start -->\nmanaged\n<!-- agent-crew-end -->\n",
        encoding="utf-8",
    )
    (agent_crew_home / "adapters" / "codex" / "invocation.md").write_text(
        "invoke\n",
        encoding="utf-8",
    )
    (agent_crew_home / "setup" / "common.sh").symlink_to(COMMON)
    (agent_crew_home / "system" / "scripts" / "generate-codex-system-agents.py").write_text(
        (REPO_ROOT / "core" / "scripts" / "generate-codex-system-agents.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (agent_crew_home / "user" / "agents" / "custom.md").write_text(
        "---\nname: custom\ndescription: user custom\n---\n# User Custom\n",
        encoding="utf-8",
    )
    project_agent.parent.mkdir(parents=True)
    project_agent.write_text(
        'name = "custom"\ndeveloper_instructions = """project native custom"""\n',
        encoding="utf-8",
    )
    env = os.environ | {
        "AGENT_CREW_HOME": str(agent_crew_home),
        "AGENT_CREW_MODE": "update",
        "AGENT_CREW_PROJECT_LOCAL_ONLY": "1",
        "AGENT_CREW_DISABLE_SYMLINKS": "1",
    }

    result = subprocess.run(
        ["bash", str(CODEX_SETUP), str(project)],
        check=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert project_agent.read_text(encoding="utf-8") == (
        'name = "custom"\ndeveloper_instructions = """project native custom"""\n'
    )
    assert "custom.toml exists in project .codex/agents and generated user agents" in result.stderr


def test_project_local_only_uses_prune_fallback_for_codex_hooks():
    text = read(CODEX_SETUP)

    assert 'link_or_copy_shared_dir "${AGENT_CREW_HOME}/hooks" "${PROJECT_ROOT}/.codex/hooks" "codex-hooks" prune' in text


def test_update_docs_define_provider_neutral_layered_reference_policy():
    text = read(UPDATE_DOC)

    assert "same-name agent files are not auto-selected" in text
    assert "AGENT_CREW_PROJECT_LOCAL_ONLY=1" in text
    assert "provider-neutral asset reference" in text
    assert "symlink fallback" in text
    assert "Managed mirror paths such as `.codex/hooks` use" in text
    assert "prune fallback semantics" in text
    assert "reserved override surfaces" in text
    assert "AGENTS.md" in text
    assert "must not be symlinked" in text
