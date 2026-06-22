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
# Finding [1]: the dead-code-elimination capability skill ships as a
# copy-if-absent SEED under `core/agents/skills/templates/` to prevent
# framework-wide auto-loading. The top-of-discovery-dir location is
# explicitly guarded against in test_skill_locations.py.
DEAD_CODE_SKILL = REPO_ROOT / "core" / "agents" / "skills" / "templates" / "dead-code-elimination.md"
SKILL_TEMPLATE = REPO_ROOT / "core" / "agents" / "skills" / "SKILL-TEMPLATE.md"
DISPATCH_RULE = REPO_ROOT / "core" / "rules" / "agent-tool-dispatch.md"

# Agents whose `.md` files carry a Capability Dispatch block with the
# agent-specific `context/capability-skills-<name>.json` output path and an
# explicit `--agent <name>` flag. `reviewer` is excluded from this list
# because the rule-doc catalog test below asserts it separately; it now
# writes to `context/capability-skills-reviewer.json` like every other
# enrolled agent — the legacy `context/review-profiles.json` path was
# retired during the dispatch consolidation.
#
# Derived from disk (finding [10]): glob `core/agents/*.md` for any file
# carrying a `--agent <name>` invocation. This removes the third
# hardcoded copy of the enrollment roster (the other two are the
# catalog table in `core/rules/agent-tool-dispatch.md` and the
# individual agent `.md` files). `reviewer` is intentionally excluded
# from this roster — it is appended separately into
# `ALL_OPTED_IN_AGENTS` below.
def _derive_dispatch_agents_from_disk() -> list[str]:
    """Scan core/agents/*.md for `--agent <name>` invocations.

    Returns the sorted list of agent names that pass the explicit
    `--agent <name>` flag to `review-profile-dispatch.py`, EXCLUDING
    `reviewer` (which is the dispatcher's default and is asserted
    separately by the catalog-row test).
    """
    import re

    agents_dir = REPO_ROOT / "core" / "agents"
    pattern = re.compile(r"--agent\s+([a-z][a-z0-9-]*)")
    found: set[str] = set()
    for md in agents_dir.glob("*.md"):
        text = md.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            name = match.group(1)
            # The file's own basename must match the --agent argument
            # to count as an enrollment (otherwise a doc file that
            # merely references another agent's name would inflate
            # the roster).
            if md.stem == name:
                found.add(name)
    found.discard("reviewer")
    return sorted(found)


DISPATCH_AGENTS = _derive_dispatch_agents_from_disk()

# Self-check: the derived roster MUST match the canonical set of
# enrolled agents (finding [10]). If a future contributor adds a new
# agent enrollment, the disk-derived list will pick it up automatically
# and this assertion will continue to hold without manual maintenance.
_EXPECTED_DISPATCH_AGENTS = sorted([
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
])
assert DISPATCH_AGENTS == _EXPECTED_DISPATCH_AGENTS, (
    f"DISPATCH_AGENTS derived from disk does not match the expected "
    f"enrollment roster.\n  derived: {DISPATCH_AGENTS}\n  expected: "
    f"{_EXPECTED_DISPATCH_AGENTS}"
)

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
    # Ensure the old Wave-B / Wave-C labels no longer appear for any
    # agent that has since been enrolled in metadata-driven dispatch.
    assert "| `backend` | Wave-B candidate" not in text
    assert "| `frontend` | Wave-C candidate" not in text
    assert "| `devops` | Wave-C candidate" not in text
    assert "| `designer` | Wave-C candidate" not in text
    assert "| `documenter` | Wave-C candidate" not in text


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
    # Finding [13]: reviewer fallback policy normalized to the uniform
    # `generic-<agent>-skills` rule. The previous asymmetric value
    # `generic-review-skills` (singular) is intentionally retired.
    assert payload["fallback_policy"] == "generic-reviewer-skills"
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
    # Finding [13]: reviewer fallback policy normalized to the uniform
    # `generic-<agent>-skills` rule (was `generic-review-skills`).
    assert payload["fallback_policy"] == "generic-reviewer-skills"
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


def test_shipped_dead_code_skill_lives_under_templates_not_discovery_dir() -> None:
    """Finding [1] — the dead-code-elimination capability skill MUST NOT
    ship at the top of `core/agents/skills/` (the dispatcher discovery
    dir). Auto-loading framework-wide on every backend/frontend refactor
    task was the original HIGH-severity finding.

    Post-fix contract: the skill lives as a copy-if-absent SEED under
    `core/agents/skills/templates/dead-code-elimination.md`, and the
    dispatcher pointed at the discovery dir MUST NOT match it.
    """
    skills_dir = REPO_ROOT / "core" / "agents" / "skills"
    templates_path = skills_dir / "templates" / "dead-code-elimination.md"
    discovery_path = skills_dir / "dead-code-elimination.md"

    # Seed exists under templates/ — opt-in flow.
    assert templates_path.is_file(), (
        f"dead-code-elimination must ship as a seed under {templates_path}"
    )
    # Discovery dir does not auto-load it.
    assert not discovery_path.exists(), (
        f"dead-code-elimination must NOT exist at {discovery_path} — that "
        "would auto-load framework-wide (finding [1] HIGH)."
    )

    # Sanity check: running the dispatcher against the discovery dir
    # must report zero matches for the skill (since it lives under the
    # templates subtree which the dispatcher does not scan recursively
    # by default).
    for agent in ("backend", "frontend"):
        payload = _run_cli(
            "--agent", agent,
            "--skills-dir", str(skills_dir),
            "--project-root", str(REPO_ROOT),
            "--task", "Cleanup pass: remove dead code and unused imports.",
            "--format", "json",
        )
        names = [m["name"] for m in payload["matched"]]
        assert "dead-code-elimination" not in names, (
            f"dead-code-elimination must NOT be auto-discovered for "
            f"--agent {agent} when it lives only under templates/: "
            f"matched={names}"
        )


# ---------------------------------------------------------------------------
# Finding [2] — reviewer matched_by legacy #137 token
# ---------------------------------------------------------------------------


def test_failure_case_reviewer_no_detection_matched_by_legacy_token(
    tmp_path: Path,
) -> None:
    """Finding [2] — when `--agent reviewer` runs with NO detection
    signals (empty task body, no changed files, no project marker),
    `matched_by` MUST emit the documented #137 legacy token
    `global-review-profile` — NOT the generalized
    `global-reviewer-skill` token that broke the contract.

    Setup uses a reviewer skill that has no `detection` regex so the
    match is purely on `loaded_by: reviewer`. That is exactly the
    no-detection path #137 documents.
    """
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    # Reviewer skill with NO detection clause (empty string).
    skill_path = skills_dir / "reviewer-baseline.md"
    skill_path.write_text(
        """---
name: reviewer-baseline
description: Baseline reviewer skill used to exercise the no-detection path.
loaded_by: reviewer
axis: review-baseline
detection:
---

# reviewer-baseline

Fixture body.
""",
        encoding="utf-8",
    )

    payload = _run_cli(
        "--agent", "reviewer",
        "--skills-dir", str(skills_dir),
        "--project-root", str(tmp_path),
        "--task", "",
        "--format", "json",
    )

    assert payload["agent"] == "reviewer"
    matched = payload["matched"]
    assert matched, "expected the reviewer-baseline skill to match on loaded_by"
    matched_by_values = {m.get("matched_by") for m in matched}
    assert "global-review-profile" in matched_by_values, (
        "Finding [2]: reviewer no-detection case MUST emit the legacy "
        "`global-review-profile` matched_by token (per #137 contract). "
        f"Got matched_by values: {matched_by_values}"
    )
    assert "global-reviewer-skill" not in matched_by_values, (
        "Finding [2]: the generalized `global-reviewer-skill` token broke "
        "the documented #137 contract — reviewer must keep its legacy "
        "token."
    )


# ---------------------------------------------------------------------------
# Finding [6] — zero-match emits NORMAL, not DEGRADED
# ---------------------------------------------------------------------------


def test_failure_case_text_format_zero_match_emits_normal_token(
    tmp_path: Path,
) -> None:
    """Finding [6] — when zero skills match, `print_text()` MUST emit
    the canonical NORMAL token `CAPABILITY_SKILLS: none`, NOT a
    `DEGRADED ...=none` token. Zero-match is NORMAL state per the
    3-state dispatch model in `core/rules/agent-tool-dispatch.md`.
    """
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    # No backend-loadable skill; deliberate zero-match condition.
    _write_skill(
        skills_dir / "frontend-only.md",
        loaded_by="frontend",
        detection="cleanup|refactor",
    )

    result = subprocess.run(
        [
            "python3", str(DISPATCH_SCRIPT),
            "--agent", "backend",
            "--skills-dir", str(skills_dir),
            "--project-root", str(tmp_path),
            "--task", "Add new feature.",
            "--format", "text",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # NORMAL token must be present.
    assert "CAPABILITY_SKILLS: none" in result.stdout, (
        "Finding [6]: zero-match text output MUST emit "
        "`CAPABILITY_SKILLS: none` (NORMAL state). Got:\n"
        f"{result.stdout}"
    )
    # DEGRADED ...=none token MUST be absent — zero-match is NORMAL.
    assert "=none" not in result.stdout.replace("CAPABILITY_SKILLS: none", ""), (
        "Finding [6]: zero-match MUST NOT emit `...=none` after stripping "
        "the canonical NORMAL token — any residual `=none` would conflate "
        f"zero-match with the script_failed DEGRADED state. Got:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# Finding [11] — discover_skills_for_agent calls loaded_by() once
# ---------------------------------------------------------------------------


def test_success_case_discover_skills_for_agent_returns_loaded_by_list(
    tmp_path: Path,
) -> None:
    """Finding [11] — `discover_skills_for_agent()` must return matches
    with the parsed `loaded_by` list populated. This test exercises the
    function end-to-end so that the implementer's refactor (collapsing
    the duplicate `loaded_by()` parse call) cannot regress behavior.

    Uses the same detection vocabulary as the existing
    `test_discover_skills_for_agent_backend_returns_dead_code_skill`
    fixture (proven to exercise the detection path) but expands
    `loaded_by` to span all three primary roles — backend, frontend,
    AND reviewer — so the test exercises the full parsed list that
    the [11] refactor must preserve.
    """
    module = _load_module(
        DISPATCH_SCRIPT, "review_profile_dispatch_module_finding11"
    )
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "shared-skill.md"
    _write_skill(
        skill,
        loaded_by="backend,frontend,reviewer",
        detection="cleanup|refactor|dead.code|unused",
    )

    matches = module.discover_skills_for_agent(
        [skills_dir],
        agent_name="backend",
        project_root=tmp_path,
        task="Refactor module to remove unused helpers.",
        changed_files=[],
    )

    assert len(matches) == 1
    sut = matches[0]
    # The collapsed single-parse implementation must still surface the
    # full loaded_by list — the refactor is BEHAVIOR-PRESERVING.
    assert sut["name"] == "shared-skill"
    assert sut["loaded_by"] == ["backend", "frontend", "reviewer"]
    # And the matched_by token must use the detection form (since the
    # task body matches the detection regex). Finding [2] specifically
    # reserves the legacy `global-review-profile` token for the
    # no-detection reviewer path only.
    assert sut.get("matched_by") == "detection"


# ---------------------------------------------------------------------------
# Finding [13] — uniform fallback_policy_for() rule
# ---------------------------------------------------------------------------


def test_success_case_fallback_policy_for_reviewer_is_uniform() -> None:
    """Finding [13] — `fallback_policy_for('reviewer')` MUST return the
    uniform `generic-reviewer-skills` form, eliminating the previous
    asymmetric `generic-review-skills` (singular) special case.
    """
    module = _load_module(
        DISPATCH_SCRIPT, "review_profile_dispatch_module_finding13"
    )
    assert module.fallback_policy_for("reviewer") == "generic-reviewer-skills", (
        "Finding [13]: reviewer must follow the uniform "
        "`generic-<agent>-skills` rule like every other agent."
    )
    # Sanity: the rule is uniform across the roster.
    for agent in ("backend", "frontend", "designer", "devops"):
        assert (
            module.fallback_policy_for(agent) == f"generic-{agent}-skills"
        ), f"fallback_policy_for({agent!r}) drifted from the uniform rule"
