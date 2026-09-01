"""Regression coverage for global-only update and Codex hook ownership."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CREW = REPO_ROOT / "core" / "bin" / "crew"
CODEX_SETUP = REPO_ROOT / "adapters" / "codex" / "setup.sh"


def test_all_projects_is_deprecated_noop_without_project_fanout():
    text = CREW.read_text(encoding="utf-8")

    assert "--all-projects is deprecated" in text
    assert "global-only" in text
    assert "update_registered_projects" not in text
    assert "AGENT_CREW_PROJECT_LOCAL_ONLY=1" not in text


def test_codex_setup_writes_global_hooks_not_project_hooks():
    text = CODEX_SETUP.read_text(encoding="utf-8")

    assert 'write_codex_hooks_json "${CODEX_HOME}/hooks.json"' in text
    assert 'link_or_copy_shared_dir "${AGENT_CREW_HOME}/hooks" "${PROJECT_ROOT}/.codex/hooks"' not in text
    assert 'write_codex_hooks_json "${PROJECT_ROOT}/.codex/hooks.json"' not in text
