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


def test_update_docs_define_provider_neutral_layered_reference_policy():
    text = read(UPDATE_DOC)

    assert "project > user > system" in text
    assert "AGENT_CREW_PROJECT_LOCAL_ONLY=1" in text
    assert "provider-neutral asset reference" in text
    assert "symlink fallback" in text
    assert "AGENTS.md" in text
    assert "must not be symlinked" in text
