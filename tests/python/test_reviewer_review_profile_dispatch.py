"""Regression coverage for reviewer review-profile dispatch (#137)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REVIEWER_MD = REPO_ROOT / "core" / "agents" / "reviewer.md"
DISPATCH_RULE = REPO_ROOT / "core" / "rules" / "agent-tool-dispatch.md"
DISPATCH_SCRIPT = REPO_ROOT / "core" / "scripts" / "review-profile-dispatch.py"
UPDATE_DRY_RUN = REPO_ROOT / "core" / "scripts" / "verify-update-dry-run.sh"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def reviewer_md_text() -> str:
    assert REVIEWER_MD.is_file(), f"reviewer.md missing at {REVIEWER_MD}"
    return REVIEWER_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dispatch_rule_text() -> str:
    assert DISPATCH_RULE.is_file(), f"agent-tool-dispatch.md missing at {DISPATCH_RULE}"
    return DISPATCH_RULE.read_text(encoding="utf-8")


def write_skill(path: Path, *, loaded_by: str, detection: str, axis: str = "") -> None:
    path.write_text(
        f"""---
name: {path.stem}
description: User-owned review skill fixture.
loaded_by: {loaded_by}
axis: {axis}
detection: {detection}
---

# {path.stem}

Review policy fixture.
""",
        encoding="utf-8",
    )


def test_reviewer_md_uses_generic_review_profile_dispatch(reviewer_md_text: str) -> None:
    assert "review-profile-dispatch.py" in reviewer_md_text
    assert "loaded_by: reviewer" in reviewer_md_text
    assert "generic review skills" in reviewer_md_text
    assert "[crew] DEGRADED" in reviewer_md_text


def test_reviewer_md_does_not_reference_concrete_user_profile_names(
    reviewer_md_text: str,
) -> None:
    forbidden = ("dobby-review-heuristics", "Dobby", "DobbyBot", "Danawa")

    for term in forbidden:
        assert term not in reviewer_md_text


def test_dispatch_rule_documents_review_profile_contract(
    dispatch_rule_text: str,
) -> None:
    assert "Metadata-driven review-profile dispatch" in dispatch_rule_text
    assert "loaded_by: reviewer" in dispatch_rule_text
    assert "profile_type: review-policy" in dispatch_rule_text
    assert "review-profile-dispatch.py" in dispatch_rule_text
    assert "| `reviewer` | Opted in" in dispatch_rule_text

    excluded_section = dispatch_rule_text.split("## Agents not subject to dispatch", 1)[1]
    assert "`reviewer`" not in excluded_section


def test_dispatcher_discovers_dobby_profile_by_metadata_without_filename_contract(
    tmp_path: Path,
) -> None:
    module = _load_module(DISPATCH_SCRIPT, "review_profile_dispatch")
    skills_dir = tmp_path / "skills"
    project_root = tmp_path / "work" / "danawa" / "shopping"
    skills_dir.mkdir()
    project_root.mkdir(parents=True)
    skill_path = skills_dir / "dobby-review-heuristics.md"
    write_skill(
        skill_path,
        loaded_by="backend,frontend,reviewer",
        axis="danawa-review-heuristics",
        detection=(
            "Danawa shopping repository OR user requests DobbyBot-like review "
            "OR task touches GraphQL/Fixity/Proxy/domain review-sensitive behavior"
        ),
    )

    matches = module.discover_review_profiles(
        [skills_dir],
        project_root=project_root,
        task="Review GraphQL resolver changes with policy rigor.",
        changed_files=[],
    )

    assert [match["name"] for match in matches] == ["dobby-review-heuristics"]
    assert matches[0]["path"] == str(skill_path)
    assert matches[0]["loaded_by"] == ["backend", "frontend", "reviewer"]


def test_dispatcher_excludes_non_reviewer_or_non_matching_profiles(tmp_path: Path) -> None:
    module = _load_module(DISPATCH_SCRIPT, "review_profile_dispatch")
    skills_dir = tmp_path / "skills"
    project_root = tmp_path / "agent-crew"
    skills_dir.mkdir()
    project_root.mkdir()
    write_skill(
        skills_dir / "backend-only-review.md",
        loaded_by="backend",
        axis="backend-review",
        detection="agent-crew repository",
    )
    write_skill(
        skills_dir / "reviewer-unmatched.md",
        loaded_by="reviewer",
        axis="external-review",
        detection="unrelated legacy repository",
    )

    matches = module.discover_review_profiles(
        [skills_dir],
        project_root=project_root,
        task="Review local changes.",
        changed_files=[],
    )

    assert matches == []


def test_cli_reports_generic_fallback_when_no_profile_matches(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    project_root = tmp_path / "project"
    skills_dir.mkdir()
    project_root.mkdir()

    result = subprocess.run(
        [
            "python3",
            str(DISPATCH_SCRIPT),
            "--skills-dir",
            str(skills_dir),
            "--project-root",
            str(project_root),
            "--task",
            "Review plain repository changes.",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["matched"] == []
    assert payload["fallback"] is True
    assert payload["fallback_policy"] == "generic-review-skills"


def test_update_dry_run_preserves_user_review_profile_skill() -> None:
    text = UPDATE_DRY_RUN.read_text(encoding="utf-8")

    assert "dobby-review-heuristics.md" in text
    assert "loaded_by: reviewer" in text
    assert 'assert_exists "${AGENT_CREW_HOME}/user/skills/dobby-review-heuristics.md"' in text
    assert 'assert_exists "${AGENT_CREW_HOME}/skills/dobby-review-heuristics.md"' in text
