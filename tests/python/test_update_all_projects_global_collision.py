"""Regression coverage for global Codex hook ownership during all-project update."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CREW = REPO_ROOT / "core" / "bin" / "crew"
CODEX_SETUP = REPO_ROOT / "adapters" / "codex" / "setup.sh"


def test_all_projects_skips_roots_whose_codex_dir_is_global_home():
    text = CREW.read_text(encoding="utf-8")

    assert "global_codex_dir" in text
    assert "project_codex_dir" in text
    assert "codex_global_home_collision" in text
    assert 'if [ "${project_codex_dir}" = "${global_codex_dir}" ]' in text


def test_codex_setup_skips_project_hook_writes_on_global_home_collision():
    text = CODEX_SETUP.read_text(encoding="utf-8")

    assert 'PROJECT_CODEX_DIR=' in text
    assert 'GLOBAL_CODEX_DIR=' in text
    assert 'CODEX_GLOBAL_HOME_COLLISION=1' in text
    assert 'if [ "${CODEX_GLOBAL_HOME_COLLISION}" = "0" ]' in text
    assert 'write_codex_hooks_json "${PROJECT_ROOT}/.codex/hooks.json"' in text
