"""Contract tests for the three methodology skills (stage 1, implementer: backend).

Derived purely from the planner spec (`context/prd.md` F1-F7, AC-1…AC-7 and the
F5 detection contract) and the approved test checklist — NOT from the
implementer's skill files, which are authored in parallel. These tests fail
(red) until `messaging-integration-patterns.md`, `refactoring-catalog.md`,
`legacy-code-seams.md` and the Channel A / Channel B wiring exist.

Coverage principle: domain behavior coverage, not line coverage. The behavior
under test is:
  (a) Channel B dispatcher match / no-match for `messaging-integration-patterns`
      (TC-001…TC-010), exercised by copying the REAL authored skill into a
      tmp skills-dir and running the unchanged dispatcher CLI — the same
      pattern the existing suite uses for `dead-code-elimination.md` and the
      stack-adapter templates;
  (b) structural / frontmatter / content contracts of the three skill files
      (TC-011…TC-016);
  (c) Channel A Open/Closed registry declarations in the agent files and the
      agent-to-skill matrix (TC-017…TC-022).

The messaging detection tests deliberately load the skill from `--skills-dir`
(the real file copied in) rather than a hand-authored `_write_skill` fixture,
so they assert the deliverable's own `detection:` expression, not a stand-in.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DISPATCH_SCRIPT = REPO_ROOT / "core" / "scripts" / "review-profile-dispatch.py"
SKILLS_DIR = REPO_ROOT / "core" / "agents" / "skills"

MESSAGING_SKILL = SKILLS_DIR / "messaging-integration-patterns.md"
REFACTORING_SKILL = SKILLS_DIR / "refactoring-catalog.md"
LEGACY_SEAMS_SKILL = SKILLS_DIR / "legacy-code-seams.md"

NEW_SKILLS = (REFACTORING_SKILL, LEGACY_SEAMS_SKILL, MESSAGING_SKILL)

LOADING_RULE = REPO_ROOT / "core" / "rules" / "agent-skill-loading.md"

AGENT_FILES = {
    "backend": REPO_ROOT / "core" / "agents" / "backend.md",
    "frontend": REPO_ROOT / "core" / "agents" / "frontend.md",
    "reviewer": REPO_ROOT / "core" / "agents" / "reviewer.md",
    "test-writer": REPO_ROOT / "core" / "agents" / "test-writer.md",
}

MESSAGING_SKILL_NAME = "messaging-integration-patterns"

REQUIRED_SECTIONS = (
    "## Source",
    "## When to Apply",
    "## Core Rules",
    "## Anti-Patterns",
    "## References",
)

# Host-/vendor-specific tool-invocation tokens that must NEVER appear in a
# provider-neutral methodology skill body. kafka/amqp are explicitly permitted
# by PRD F3 as detection evidence / illustrative examples, so they are NOT here.
FORBIDDEN_HOST_TOKENS = (
    "mnemos",          # host memory CLI
    "crew:run",        # host workflow command
    "crew:agent",      # host workflow command
    "AGENT_CREW_HOME",  # host env var / bin invocation
)


# ---------------------------------------------------------------------------
# Helpers (mirror the existing test_skill_dispatch.py conventions)
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> dict:
    result = subprocess.run(
        ["python3", str(DISPATCH_SCRIPT), *args],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _matched_names(payload: dict) -> list[str]:
    return [m["name"] for m in payload["matched"]]


def _core_rules_count(text: str) -> int:
    """Count `### Rule N` headings inside the `## Core Rules` section.

    Mirrors the established `### Rule [0-9]` convention enforced for peer
    skills by tests/shell/test_skill_loading_open_closed.bash (Test 8),
    but scopes the count to the Core Rules section so a stray heading
    elsewhere cannot inflate it.
    """
    lines = text.splitlines()
    in_core = False
    count = 0
    for line in lines:
        if re.match(r"^## Core Rules\b", line):
            in_core = True
            continue
        if in_core and line.startswith("## "):
            break
        if in_core and re.match(r"^### Rule\s+\d", line):
            count += 1
    return count


def _extract_upfront_skill_names(agent_path: Path) -> set[str]:
    """Return skill basenames declared in an agent's
    '## Skills (Loaded Upfront)' section.

    Python analogue of the bash `extract_skill_paths` helper: collect
    backticked paths containing `skills/` between the upfront-section
    header and the next `## ` header.
    """
    text = agent_path.read_text(encoding="utf-8")
    in_section = False
    names: set[str] = set()
    backticked = re.compile(r"`([^`]*skills/[^`]+)`")
    for line in text.splitlines():
        if re.match(r"^## Skills \(Loaded Upfront\)\s*$", line):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            in_section = False
        if in_section:
            for match in backticked.finditer(line):
                names.add(Path(match.group(1)).name)
    return names


def _matrix_rows(text: str) -> list[list[str]]:
    """Split every markdown table row into stripped, backtick-free cells."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip().strip("`").strip() for c in stripped.strip("|").split("|")]
        rows.append(cells)
    return rows


def _matrix_cell(text: str, skill_name: str, agent: str) -> str | None:
    """Return the Agent-to-Skill matrix cell for (skill_name, agent).

    Locates the header row dynamically (the row carrying both `backend` and
    `reviewer` as cells) so the assertion is robust to column order, then
    returns the skill row's cell under the agent's column. Returns None when
    the skill has no matrix row.
    """
    rows = _matrix_rows(text)
    header: list[str] | None = None
    for cells in rows:
        if "backend" in cells and "reviewer" in cells:
            header = cells
            break
    assert header is not None, "could not locate Agent-to-Skill matrix header row"
    assert agent in header, f"agent column '{agent}' missing from matrix header {header}"
    idx = header.index(agent)
    for cells in rows:
        if not cells:
            continue
        if cells[0] == skill_name:
            return cells[idx] if idx < len(cells) else None
    return None


# ---------------------------------------------------------------------------
# TC-001…TC-007 — Channel B positive detection (manifest-bound + keyword)
# ---------------------------------------------------------------------------


def _skills_dir_with_messaging(tmp_path: Path) -> Path:
    """Copy the REAL authored messaging skill into an isolated tmp skills dir."""
    assert MESSAGING_SKILL.is_file(), (
        f"missing authored skill at {MESSAGING_SKILL}"
    )
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    shutil.copy(MESSAGING_SKILL, skills_dir / "messaging-integration-patterns.md")
    return skills_dir


def _dispatch_messaging(
    tmp_path: Path,
    *,
    manifest: tuple[str, str] | None = None,
    task: str = "Implement a service.",
) -> list[str]:
    skills_dir = _skills_dir_with_messaging(tmp_path)
    project_root = tmp_path / "work" / "svc"
    project_root.mkdir(parents=True)
    if manifest is not None:
        name, content = manifest
        (project_root / name).write_text(content, encoding="utf-8")
    payload = _run_cli(
        "--agent", "backend",
        "--skills-dir", str(skills_dir),
        "--project-root", str(project_root),
        "--task", task,
        "--format", "json",
    )
    return _matched_names(payload)


def test_gradle_spring_kafka_manifest_matches_messaging(tmp_path: Path) -> None:
    """TC-001 (MUST, AC-3): build.gradle with spring-kafka matches for backend."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=(
            "build.gradle",
            "dependencies {\n"
            "    implementation 'org.springframework.kafka:spring-kafka'\n"
            "}\n",
        ),
    )
    assert MESSAGING_SKILL_NAME in names


def test_gradle_kts_spring_kafka_manifest_matches_messaging(tmp_path: Path) -> None:
    """TC-002 (SHOULD, AC-3): the build.gradle.kts variant binds too."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=(
            "build.gradle.kts",
            "dependencies {\n"
            '    implementation("org.springframework.kafka:spring-kafka")\n'
            "}\n",
        ),
    )
    assert MESSAGING_SKILL_NAME in names


def test_pom_xml_spring_kafka_manifest_matches_messaging(tmp_path: Path) -> None:
    """TC-003 (SHOULD, AC-3): pom.xml carries the kafka clause."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=(
            "pom.xml",
            "<dependencies>\n"
            "  <dependency>\n"
            "    <groupId>org.springframework.kafka</groupId>\n"
            "    <artifactId>spring-kafka</artifactId>\n"
            "  </dependency>\n"
            "</dependencies>\n",
        ),
    )
    assert MESSAGING_SKILL_NAME in names


def test_package_json_amqplib_matches_messaging(tmp_path: Path) -> None:
    """TC-004 (MUST, F5/F6): package.json with amqplib matches."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=(
            "package.json",
            json.dumps({"dependencies": {"amqplib": "^0.10.0"}}),
        ),
    )
    assert MESSAGING_SKILL_NAME in names


def test_package_json_kafkajs_matches_messaging(tmp_path: Path) -> None:
    """TC-005 (SHOULD, F5): the kafkajs alternative of the npm binding matches."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=(
            "package.json",
            json.dumps({"dependencies": {"kafkajs": "^2.2.0"}}),
        ),
    )
    assert MESSAGING_SKILL_NAME in names


def test_python_requirements_kafka_matches_messaging(tmp_path: Path) -> None:
    """TC-006 (SHOULD, F5): a Python manifest carrying kafka matches."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=("requirements.txt", "kafka-python==2.0.2\n"),
    )
    assert MESSAGING_SKILL_NAME in names


def test_pyproject_pika_matches_messaging(tmp_path: Path) -> None:
    """TC-006 (SHOULD, F5): pyproject.toml carrying pika matches (amqp variant)."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=(
            "pyproject.toml",
            "[project]\ndependencies = [\"pika>=1.3\"]\n",
        ),
    )
    assert MESSAGING_SKILL_NAME in names


def test_messaging_task_keyword_matches_without_manifest(tmp_path: Path) -> None:
    """TC-007 (SHOULD, F5): task keywords drive dispatch with no manifest."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=None,
        task="Design an outbox relay for event-driven kafka processing.",
    )
    assert MESSAGING_SKILL_NAME in names


# ---------------------------------------------------------------------------
# TC-008…TC-010 — Channel B negative detection (over-broad guards)
# ---------------------------------------------------------------------------


def test_plain_java_gradle_project_does_not_match_messaging(tmp_path: Path) -> None:
    """TC-008 (MUST, AC-4): plain Java Gradle + non-messaging task must NOT match."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=("build.gradle", "plugins {\n    id 'java'\n}\n"),
        task="Refactor the Java library.",
    )
    assert MESSAGING_SKILL_NAME not in names


def test_plain_npm_project_does_not_match_messaging(tmp_path: Path) -> None:
    """TC-009 (SHOULD, F5): plain npm (no kafkajs/amqplib) must NOT match."""
    names = _dispatch_messaging(
        tmp_path,
        manifest=(
            "package.json",
            json.dumps({"dependencies": {"react": "^18.0.0"}}),
        ),
        task="Implement a new button.",
    )
    assert MESSAGING_SKILL_NAME not in names


def test_unbound_incidental_kafka_keyword_does_not_match_messaging(
    tmp_path: Path,
) -> None:
    """TC-010 (MUST, F5 + binding rule at test_skill_dispatch.py:990/:1079).

    A `kafka` token that appears only as an unbound incidental hit — here a
    package.json *scripts* name, not a kafkajs/amqplib dependency — with a
    non-messaging task must NOT match. Guards against false positives from
    manifest-content keywords that are not bound to the named manifest fragment.
    """
    names = _dispatch_messaging(
        tmp_path,
        manifest=(
            "package.json",
            json.dumps({"scripts": {"kafka": "echo kafka"}}),
        ),
        task="Implement a new button.",
    )
    assert MESSAGING_SKILL_NAME not in names


# ---------------------------------------------------------------------------
# TC-011 — messaging frontmatter (Channel B dispatch contract)
# ---------------------------------------------------------------------------


def test_messaging_skill_ships_with_required_frontmatter() -> None:
    """TC-011 (MUST, AC-1/AC-5, F5): loaded_by/axis/detection frontmatter.

    Modeled on test_dead_code_skill_ships_with_required_frontmatter
    (tests/python/test_skill_dispatch.py:170).
    """
    assert MESSAGING_SKILL.is_file(), f"missing skill at {MESSAGING_SKILL}"
    text = MESSAGING_SKILL.read_text(encoding="utf-8")
    assert "loaded_by: backend" in text
    assert re.search(r"^axis:\s*\S", text, re.MULTILINE), "missing axis: field"
    assert re.search(r"^detection:\s*\S", text, re.MULTILINE), "missing detection: field"


# ---------------------------------------------------------------------------
# TC-012…TC-014 — structural section contract for all three skills
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "skill_path",
    NEW_SKILLS,
    ids=[p.name for p in NEW_SKILLS],
)
def test_new_skill_contains_required_template_sections(skill_path: Path) -> None:
    """TC-012/013/014 (MUST, AC-5): each new skill carries the template sections."""
    assert skill_path.is_file(), f"missing skill at {skill_path}"
    text = skill_path.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS:
        assert section in text, f"{skill_path.name} missing section '{section}'"


# ---------------------------------------------------------------------------
# TC-015 — >= 10 imperative Core Rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "skill_path",
    NEW_SKILLS,
    ids=[p.name for p in NEW_SKILLS],
)
def test_new_skill_declares_at_least_ten_core_rules(skill_path: Path) -> None:
    """TC-015 (SHOULD, AC-5/NFR): >= 10 `### Rule N` entries in Core Rules."""
    assert skill_path.is_file(), f"missing skill at {skill_path}"
    count = _core_rules_count(skill_path.read_text(encoding="utf-8"))
    assert count >= 10, f"{skill_path.name} has only {count} Core Rules (>= 10 required)"


# ---------------------------------------------------------------------------
# TC-016 — provider neutrality (no host-/vendor-specific tool invocations)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "skill_path",
    NEW_SKILLS,
    ids=[p.name for p in NEW_SKILLS],
)
def test_new_skill_is_provider_neutral(skill_path: Path) -> None:
    """TC-016 (SHOULD, AC-5/NFR): no host-specific tool invocations in the body."""
    assert skill_path.is_file(), f"missing skill at {skill_path}"
    text = skill_path.read_text(encoding="utf-8")
    for token in FORBIDDEN_HOST_TOKENS:
        assert token not in text, (
            f"{skill_path.name} contains host-specific token '{token}' "
            "(skill bodies must be provider-neutral)"
        )


# ---------------------------------------------------------------------------
# TC-017…TC-019 — Channel A upfront declarations in agent files
# ---------------------------------------------------------------------------


def test_refactoring_catalog_declared_upfront_by_backend_frontend_reviewer() -> None:
    """TC-017 (MUST, AC-2, F4/F6): refactoring-catalog is upfront for these agents."""
    for agent in ("backend", "frontend", "reviewer"):
        declared = _extract_upfront_skill_names(AGENT_FILES[agent])
        assert "refactoring-catalog.md" in declared, (
            f"{agent}.md upfront section must declare refactoring-catalog.md"
        )


def test_legacy_code_seams_declared_upfront_by_backend_frontend_test_writer() -> None:
    """TC-018 (MUST, AC-2, F4/F6): legacy-code-seams is upfront for these agents."""
    for agent in ("backend", "frontend", "test-writer"):
        declared = _extract_upfront_skill_names(AGENT_FILES[agent])
        assert "legacy-code-seams.md" in declared, (
            f"{agent}.md upfront section must declare legacy-code-seams.md"
        )


def test_messaging_skill_never_declared_in_any_upfront_section() -> None:
    """TC-019 (MUST, AC-2, F3/F6 hard constraint): Channel B skill is never upfront."""
    for agent, path in AGENT_FILES.items():
        declared = _extract_upfront_skill_names(path)
        assert "messaging-integration-patterns.md" not in declared, (
            f"{agent}.md upfront section must NOT declare "
            "messaging-integration-patterns.md (Channel B only)"
        )


# ---------------------------------------------------------------------------
# TC-021…TC-022 — Agent-to-Skill matrix consistent with the agent files
# ---------------------------------------------------------------------------

_MATRIX_AGENTS = ("backend", "frontend", "test-writer", "reviewer")


def test_refactoring_catalog_matrix_row_consistent_with_upfront() -> None:
    """TC-021 (MUST, AC-6, F4): matrix yes-cells match the agents declaring it.

    Spec (F4): backend yes, frontend yes, test-writer —, reviewer yes.
    """
    matrix_text = LOADING_RULE.read_text(encoding="utf-8")
    declared = {
        agent
        for agent in _MATRIX_AGENTS
        if "refactoring-catalog.md" in _extract_upfront_skill_names(AGENT_FILES[agent])
    }
    assert declared == {"backend", "frontend", "reviewer"}
    for agent in _MATRIX_AGENTS:
        cell = _matrix_cell(matrix_text, "refactoring-catalog.md", agent)
        assert cell is not None, f"no refactoring-catalog.md matrix cell for {agent}"
        if agent in declared:
            assert cell == "yes", f"{agent} column must be 'yes', got '{cell}'"
        else:
            assert cell != "yes", f"{agent} column must not be 'yes', got '{cell}'"


def test_legacy_code_seams_matrix_row_consistent_with_upfront() -> None:
    """TC-022 (MUST, AC-6, F4): matrix yes-cells match the agents declaring it.

    Spec (F4): backend yes, frontend yes, test-writer yes, reviewer —.
    """
    matrix_text = LOADING_RULE.read_text(encoding="utf-8")
    declared = {
        agent
        for agent in _MATRIX_AGENTS
        if "legacy-code-seams.md" in _extract_upfront_skill_names(AGENT_FILES[agent])
    }
    assert declared == {"backend", "frontend", "test-writer"}
    for agent in _MATRIX_AGENTS:
        cell = _matrix_cell(matrix_text, "legacy-code-seams.md", agent)
        assert cell is not None, f"no legacy-code-seams.md matrix cell for {agent}"
        if agent in declared:
            assert cell == "yes", f"{agent} column must be 'yes', got '{cell}'"
        else:
            assert cell != "yes", f"{agent} column must not be 'yes', got '{cell}'"


def test_messaging_skill_absent_from_matrix_consumer_columns() -> None:
    """TC-019/TC-021 support (MUST, F5): the Channel B skill has no yes matrix cell.

    Complements the upfront-section negative: messaging-integration-patterns must
    not appear as a consumer 'yes' in the Agent-to-Skill matrix either.
    """
    matrix_text = LOADING_RULE.read_text(encoding="utf-8")
    for cells in _matrix_rows(matrix_text):
        if cells and cells[0] == "messaging-integration-patterns.md":
            assert "yes" not in cells, (
                "messaging-integration-patterns.md must not be marked 'yes' "
                "in any matrix consumer column (Channel B only)"
            )
