"""Runtime tests for changed-file-driven language skill selection."""

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "core" / "scripts" / "language-skill-select.py"
REVIEWER = (REPO_ROOT / "core" / "agents" / "reviewer.md").read_text(
    encoding="utf-8"
)


def _select(*paths: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--agent", "reviewer"],
        check=True,
        capture_output=True,
        input="".join(f"{path}\n" for path in paths),
        text=True,
    )
    return result.stdout.splitlines()


def test_boundary_case_contract_docs_only_change_selects_no_language_skill():
    assert _select("README.md", "docs/runtime.md") == []


def test_success_case_contract_kotlin_source_selects_only_effective_kotlin():
    selected = _select("src/main/kotlin/example/App.kt", "README.md")

    assert [Path(path).name for path in selected] == ["effective-kotlin.md"]


def test_regression_case_contract_manifest_does_not_imply_unrelated_languages():
    assert _select("build.gradle.kts", "settings.gradle.kts") == []


def test_boundary_case_contract_changed_path_with_spaces_is_not_split():
    selected = _select("src/main/kotlin/example dir/App.kt")

    assert [Path(path).name for path in selected] == ["effective-kotlin.md"]


def test_regression_case_reviewer_includes_worktree_and_untracked_changes():
    assert 'git -C "${PROJECT_ROOT}" diff --name-only "${TASK_START_HEAD:-HEAD}" --' in REVIEWER
    assert "ls-files --others --exclude-standard" in REVIEWER
    assert "sort -u" in REVIEWER
    assert '${TASK_START_HEAD:-HEAD~5}..HEAD' not in REVIEWER
