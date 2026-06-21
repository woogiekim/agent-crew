"""Regression coverage for the generalized metadata-driven skill dispatcher (#186).

The dispatcher (`core/scripts/review-profile-dispatch.py`) is parametrized by
`--agent`. These tests assert:

1. The default `--agent reviewer` behavior remains backward compatible (#137).
2. `--agent backend` returns skills with `loaded_by: backend` (e.g.
   `dead-code-elimination.md`).
3. `--agent frontend` returns the same shared capability skill.
4. The `dead-code-elimination.md` example skill ships with the expected
   frontmatter slots.
5. The agent-tool-dispatch rule and `SKILL-TEMPLATE.md` document the
   generalized contract.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DISPATCH_SCRIPT = REPO_ROOT / "core" / "scripts" / "review-profile-dispatch.py"
DEAD_CODE_SKILL = REPO_ROOT / "core" / "agents" / "skills" / "dead-code-elimination.md"
SKILL_TEMPLATE = REPO_ROOT / "core" / "agents" / "skills" / "SKILL-TEMPLATE.md"
DISPATCH_RULE = REPO_ROOT / "core" / "rules" / "agent-tool-dispatch.md"

# Agents whose `.md` files carry a Capability Dispatch block with the
# agent-specific `context/capability-skills-<name>.json` output path and an
# explicit `--agent <name>` flag. This excludes `reviewer`, which adopted
# the dispatcher first (#137) with a legacy `context/review-profiles.json`
# path and keeps that path for backward compatibility.
#
# MAINTENANCE NOTE: This list is a third hardcoded copy of the enrollment
# roster — the other two are the catalog table in
# `core/rules/agent-tool-dispatch.md` and the 13 individual agent `.md`
# files under `core/agents/`. When agents are added to or removed from
# metadata-driven dispatch, all three locations must stay in sync. See
# Findings 8/10 in the review tracker for the long-term consolidation
# plan (introduce a single canonical source).
DISPATCH_AGENTS = [
    "analyst",
    "backend",
    "designer",
    "devops",
    "documenter",
    "frontend",
    "issuer",
    "planner",
    "qa-owner",
    "requirements",
    "resolver",
    "test-writer",
]

# All agents that have opted in to metadata-driven dispatch, including
# `reviewer`. Used by the rule-doc catalog assertion only (the catalog
# row's prose is uniform across all 13 agents).
ALL_OPTED_IN_AGENTS = DISPATCH_AGENTS + ["reviewer"]


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_cli(*args: str) -> dict:
    result = subprocess.run(
        ["python3", str(DISPATCH_SCRIPT), *args],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _write_skill(
    path: Path,
    *,
    loaded_by: str,
    detection: str,
    axis: str = "code-cleanup",
) -> None:
    path.write_text(
        f"""---
name: {path.stem}
description: Fixture skill for dispatch tests.
loaded_by: {loaded_by}
axis: {axis}
detection: {detection}
---

# {path.stem}

Fixture body.
""",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Frontmatter / documentation contract
# ---------------------------------------------------------------------------


def test_dead_code_skill_ships_with_required_frontmatter() -> None:
    assert DEAD_CODE_SKILL.is_file(), f"missing example skill at {DEAD_CODE_SKILL}"
    text = DEAD_CODE_SKILL.read_text(encoding="utf-8")
    assert "loaded_by: backend,frontend" in text
    assert "axis: code-cleanup" in text
    assert "detection: cleanup|refactor|dead.code|unused" in text


def test_skill_template_documents_dispatcher_slots() -> None:
    text = SKILL_TEMPLATE.read_text(encoding="utf-8")
    assert "loaded_by:" in text
    assert "axis:" in text
    assert "detection:" in text


def test_dispatch_rule_marks_all_opted_in_agents() -> None:
    """Every agent enrolled in metadata-driven capability-skill dispatch
    (ALL_OPTED_IN_AGENTS — including the legacy reviewer adopter) must
    appear in the catalog table of `core/rules/agent-tool-dispatch.md`
    with an "Opted in" status row.

    The row may carry either the bare label (`| <agent> | Opted in`) or the
    metadata-driven variant (`| <agent> | Opted in (metadata-driven`), since
    different waves were enrolled with slightly different prose."""
    text = DISPATCH_RULE.read_text(encoding="utf-8")
    for agent in ALL_OPTED_IN_AGENTS:
        opted_in_bare = f"| `{agent}` | Opted in"
        opted_in_metadata = f"| `{agent}` | Opted in (metadata-driven"
        assert opted_in_bare in text or opted_in_metadata in text, (
            f"agent `{agent}` must appear as 'Opted in' (or "
            "'Opted in (metadata-driven…') in agent-tool-dispatch.md catalog"
        )
    # Ensure the old Wave-B / Wave-C labels no longer appear for backend/frontend.
    assert "| `backend` | Wave-B candidate" not in text
    assert "| `frontend` | Wave-C candidate" not in text


@pytest.fixture(scope="module")
def dispatch_agent_texts() -> dict[str, tuple[Path, str]]:
    """Read each enrolled agent's `.md` file once per test session.

    Previously, three separate tests each opened and read all 12+ agent
    files individually (36+ disk reads). This fixture reads each file
    once and returns a mapping of `agent_name -> (path, text)` shared
    across all three tests.
    """
    texts: dict[str, tuple[Path, str]] = {}
    for agent in DISPATCH_AGENTS:
        agent_file = REPO_ROOT / "core" / "agents" / f"{agent}.md"
        texts[agent] = (agent_file, agent_file.read_text(encoding="utf-8"))
    return texts


def test_agent_files_reference_metadata_dispatch_for_capability_skills(
    dispatch_agent_texts: dict[str, tuple[Path, str]],
) -> None:
    for agent in DISPATCH_AGENTS:
        agent_file, text = dispatch_agent_texts[agent]
        lowered = text.lower()
        assert "review-profile-dispatch.py" in text, agent_file
        # Accept either phrasing — backend/frontend say "metadata dispatch",
        # the agents enrolled in later waves say "metadata-driven … dispatch".
        assert "metadata dispatch" in lowered or "metadata-driven" in lowered, (
            agent_file
        )


def test_dispatch_agents_use_agent_specific_output_path(
    dispatch_agent_texts: dict[str, tuple[Path, str]],
) -> None:
    """Each enrolled agent must write its dispatch report to an agent-specific
    output path (`capability-skills-<name>.json`) so parallel stages can run
    without clobbering each other's report files."""
    for agent in DISPATCH_AGENTS:
        agent_file, text = dispatch_agent_texts[agent]
        expected = f"context/capability-skills-{agent}.json"
        assert expected in text, (
            f"{agent_file} must reference {expected} in its dispatch block"
        )
        # Must not still use the generic, non-namespaced path.
        assert "context/capability-skills.json" not in text, (
            f"{agent_file} still references the generic path "
            "context/capability-skills.json — switch to "
            f"{expected}"
        )


def test_dispatch_agents_pass_explicit_agent_flag(
    dispatch_agent_texts: dict[str, tuple[Path, str]],
) -> None:
    """Each enrolled agent must pass `--agent <name>` explicitly to the
    dispatcher rather than relying on the default (reviewer)."""
    for agent in DISPATCH_AGENTS:
        agent_file, text = dispatch_agent_texts[agent]
        expected_flag = f"--agent {agent}"
        assert expected_flag in text, (
            f"{agent_file} must pass `{expected_flag}` to "
            "review-profile-dispatch.py in its dispatch block"
        )


# ---------------------------------------------------------------------------
# Programmatic discovery (in-process)
# ---------------------------------------------------------------------------


def test_discover_skills_for_agent_backend_returns_dead_code_skill(
    tmp_path: Path,
) -> None:
    module = _load_module(DISPATCH_SCRIPT, "review_profile_dispatch_module")
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "dead-code-elimination.md"
    _write_skill(
        skill,
        loaded_by="backend,frontend",
        detection="cleanup|refactor|dead.code|unused",
    )

    matches = module.discover_skills_for_agent(
        [skills_dir],
        agent_name="backend",
        project_root=tmp_path,
        task="Refactor module to remove unused helpers.",
        changed_files=[],
    )

    assert [m["name"] for m in matches] == ["dead-code-elimination"]
    assert matches[0]["path"] == str(skill)
    assert matches[0]["loaded_by"] == ["backend", "frontend"]


def test_discover_skills_for_agent_frontend_returns_dead_code_skill(
    tmp_path: Path,
) -> None:
    module = _load_module(DISPATCH_SCRIPT, "review_profile_dispatch_module_fe")
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "dead-code-elimination.md"
    _write_skill(
        skill,
        loaded_by="backend,frontend",
        detection="cleanup|refactor|dead.code|unused",
    )

    matches = module.discover_skills_for_agent(
        [skills_dir],
        agent_name="frontend",
        project_root=tmp_path,
        task="Cleanup of dead code in legacy UI module.",
        changed_files=[],
    )

    assert [m["name"] for m in matches] == ["dead-code-elimination"]


def test_discover_skills_for_agent_excludes_non_matching_agent(tmp_path: Path) -> None:
    module = _load_module(DISPATCH_SCRIPT, "review_profile_dispatch_module_excl")
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(
        skills_dir / "backend-only.md",
        loaded_by="backend",
        detection="cleanup|refactor",
    )

    matches = module.discover_skills_for_agent(
        [skills_dir],
        agent_name="frontend",
        project_root=tmp_path,
        task="Refactor cleanup pass.",
        changed_files=[],
    )

    assert matches == []


def test_reviewer_discovery_backward_compatible(tmp_path: Path) -> None:
    """The legacy `discover_review_profiles` helper still works."""
    module = _load_module(DISPATCH_SCRIPT, "review_profile_dispatch_module_compat")
    skills_dir = tmp_path / "skills"
    project_root = tmp_path / "work" / "danawa"
    skills_dir.mkdir()
    project_root.mkdir(parents=True)
    skill = skills_dir / "dobby-review-heuristics.md"
    _write_skill(
        skill,
        loaded_by="backend,frontend,reviewer",
        detection="Danawa shopping repository OR user requests DobbyBot-like review",
        axis="danawa-review-heuristics",
    )

    matches = module.discover_review_profiles(
        [skills_dir],
        project_root=project_root,
        task="Review GraphQL changes for Danawa shopping.",
        changed_files=[],
    )

    assert [m["name"] for m in matches] == ["dobby-review-heuristics"]


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def _setup_skill_fixture(tmp_path: Path) -> Path:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(
        skills_dir / "dead-code-elimination.md",
        loaded_by="backend,frontend",
        detection="cleanup|refactor|dead.code|unused",
    )
    return skills_dir


def test_cli_agent_backend_returns_dead_code_path(tmp_path: Path) -> None:
    skills_dir = _setup_skill_fixture(tmp_path)
    payload = _run_cli(
        "--agent", "backend",
        "--skills-dir", str(skills_dir),
        "--project-root", str(tmp_path),
        "--task", "Refactor module to remove unused helpers.",
        "--format", "json",
    )

    assert payload["agent"] == "backend"
    assert payload["fallback"] is False
    assert payload["fallback_policy"] == "generic-backend-skills"
    matched_paths = [m["path"] for m in payload["matched"]]
    assert any(p.endswith("dead-code-elimination.md") for p in matched_paths)


def test_cli_agent_frontend_returns_dead_code_path(tmp_path: Path) -> None:
    skills_dir = _setup_skill_fixture(tmp_path)
    payload = _run_cli(
        "--agent", "frontend",
        "--skills-dir", str(skills_dir),
        "--project-root", str(tmp_path),
        "--task", "Cleanup of dead code in legacy UI module.",
        "--format", "json",
    )

    assert payload["agent"] == "frontend"
    assert payload["fallback"] is False
    assert payload["fallback_policy"] == "generic-frontend-skills"
    matched_paths = [m["path"] for m in payload["matched"]]
    assert any(p.endswith("dead-code-elimination.md") for p in matched_paths)


def test_cli_default_agent_is_reviewer_backward_compatible(tmp_path: Path) -> None:
    """No --agent flag MUST behave exactly as pre-#186 (reviewer default)."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(
        skills_dir / "dobby-review-heuristics.md",
        loaded_by="reviewer",
        detection=(
            "Danawa shopping repository OR user requests DobbyBot-like review "
            "OR task touches GraphQL/Fixity/Proxy/domain review-sensitive behavior"
        ),
        axis="danawa-review-heuristics",
    )
    project_root = tmp_path / "work" / "danawa"
    project_root.mkdir(parents=True)

    payload = _run_cli(
        "--skills-dir", str(skills_dir),
        "--project-root", str(project_root),
        "--task", "Review GraphQL Danawa changes.",
        "--format", "json",
    )

    assert payload["agent"] == "reviewer"
    assert payload["fallback_policy"] == "generic-review-skills"
    assert payload["fallback"] is False
    assert [m["name"] for m in payload["matched"]] == ["dobby-review-heuristics"]


def test_cli_explicit_reviewer_matches_default(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    _write_skill(
        skills_dir / "dobby-review-heuristics.md",
        loaded_by="reviewer",
        detection=(
            "Danawa shopping repository OR user requests DobbyBot-like review "
            "OR task touches GraphQL/Fixity/Proxy/domain review-sensitive behavior"
        ),
        axis="danawa-review-heuristics",
    )
    project_root = tmp_path / "work" / "danawa"
    project_root.mkdir(parents=True)

    payload = _run_cli(
        "--agent", "reviewer",
        "--skills-dir", str(skills_dir),
        "--project-root", str(project_root),
        "--task", "Review GraphQL Danawa changes.",
        "--format", "json",
    )

    assert payload["agent"] == "reviewer"
    assert payload["fallback_policy"] == "generic-review-skills"
    assert [m["name"] for m in payload["matched"]] == ["dobby-review-heuristics"]


def test_cli_agent_with_no_match(tmp_path: Path) -> None:
    """Zero-match is NORMAL per the 3-state dispatch result spec
    (`core/rules/agent-tool-dispatch.md` § "Metadata-driven skill dispatch"):
    the script succeeded and simply found no user-owned capability skills.
    That is NOT a degraded/fallback condition — `fallback` must be False
    and the CLI must exit 0 with an empty `matched` array."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    # No skill that loads for backend.
    _write_skill(
        skills_dir / "frontend-only.md",
        loaded_by="frontend",
        detection="cleanup|refactor",
    )

    payload = _run_cli(
        "--agent", "backend",
        "--skills-dir", str(skills_dir),
        "--project-root", str(tmp_path),
        "--task", "Add new feature.",
        "--format", "json",
    )

    assert payload["agent"] == "backend"
    assert payload["matched"] == []
    assert payload["fallback"] is False
    assert payload["fallback_policy"] == "generic-backend-skills"


def test_cli_text_format_for_backend(tmp_path: Path) -> None:
    skills_dir = _setup_skill_fixture(tmp_path)
    result = subprocess.run(
        [
            "python3", str(DISPATCH_SCRIPT),
            "--agent", "backend",
            "--skills-dir", str(skills_dir),
            "--project-root", str(tmp_path),
            "--task", "Refactor and remove unused functions.",
            "--format", "text",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "backend_skill:" in result.stdout
    assert "dead-code-elimination" in result.stdout


# ---------------------------------------------------------------------------
# End-to-end: dispatcher actually discovers the shipped example skill
# ---------------------------------------------------------------------------


def test_shipped_dead_code_skill_is_discovered_by_dispatcher() -> None:
    """The shipped `core/agents/skills/dead-code-elimination.md` must be picked up
    by `--agent backend` and `--agent frontend` when the dispatcher is pointed at
    the source `core/agents/skills/` directory."""
    skills_dir = REPO_ROOT / "core" / "agents" / "skills"

    for agent in ("backend", "frontend"):
        payload = _run_cli(
            "--agent", agent,
            "--skills-dir", str(skills_dir),
            "--project-root", str(REPO_ROOT),
            "--task", "Cleanup pass: remove dead code and unused imports.",
            "--format", "json",
        )
        names = [m["name"] for m in payload["matched"]]
        assert "dead-code-elimination" in names, (
            f"dead-code-elimination not picked up for --agent {agent}: "
            f"matched={names}"
        )
