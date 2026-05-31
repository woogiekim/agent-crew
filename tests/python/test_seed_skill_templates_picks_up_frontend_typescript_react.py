"""Wave C exemplar (#131) — seed-skill-templates.sh picks up frontend-typescript-react.

Verifies that the existing Wave A seed flow (`core/setup/seed-skill-templates.sh`)
discovers the new Channel B template `frontend-typescript-react.md` and honors
the copy-if-absent contract: NEVER overwrites a user-edited file.

These tests are scoped to the new Wave C template specifically. General
seed-helper behavior is already covered by
`tests/shell/test_skill_templates_seed.bash` (and the Wave B
`test_seed_skill_templates_picks_up_backend_kotlin_spring.py`); these tests
are additive.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEED_SCRIPT = REPO_ROOT / "core" / "setup" / "seed-skill-templates.sh"
RECONCILE_SCRIPT = REPO_ROOT / "core" / "setup" / "reconcile-skill-templates.sh"
TEMPLATE_SRC = (
    REPO_ROOT
    / "core"
    / "agents"
    / "skills"
    / "templates"
    / "frontend-typescript-react.md"
)


@pytest.fixture
def isolated_templates_dir(tmp_path: Path) -> Path:
    """Copy the real frontend-typescript-react.md into an isolated templates dir."""
    assert SEED_SCRIPT.is_file(), f"seed-skill-templates.sh missing at {SEED_SCRIPT}"
    assert TEMPLATE_SRC.is_file(), (
        f"frontend-typescript-react.md missing at {TEMPLATE_SRC}; "
        "Wave C requires this file to ship."
    )
    src = tmp_path / "templates"
    src.mkdir()
    shutil.copy(TEMPLATE_SRC, src / "frontend-typescript-react.md")
    return src


@pytest.fixture
def empty_user_skills_dir(tmp_path: Path) -> Path:
    user = tmp_path / "user-skills"
    user.mkdir()
    return user


def _run_seed(src: Path, user: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SEED_SCRIPT), str(src), str(user)],
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------------- #
# First run: frontend-typescript-react.md must be seeded                      #
# --------------------------------------------------------------------------- #


def test_first_run_seeds_frontend_typescript_react(
    isolated_templates_dir: Path,
    empty_user_skills_dir: Path,
) -> None:
    result = _run_seed(isolated_templates_dir, empty_user_skills_dir)

    assert result.returncode == 0, (
        f"seed-skill-templates.sh failed (rc={result.returncode}): "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    user_path = empty_user_skills_dir / "frontend-typescript-react.md"
    assert user_path.is_file(), (
        f"frontend-typescript-react.md was not seeded into {empty_user_skills_dir}; "
        f"seed stdout was: {result.stdout!r}"
    )

    assert "seeded user skill: frontend-typescript-react.md" in result.stdout, (
        f"Expected 'seeded user skill: frontend-typescript-react.md' in stdout; "
        f"got: {result.stdout!r}"
    )
    assert "seeded=1" in result.stdout


def test_first_run_user_layer_bytes_match_template(
    isolated_templates_dir: Path,
    empty_user_skills_dir: Path,
) -> None:
    """The seeded file must be byte-identical to the source template."""
    _run_seed(isolated_templates_dir, empty_user_skills_dir)

    src_bytes = (isolated_templates_dir / "frontend-typescript-react.md").read_bytes()
    user_bytes = (empty_user_skills_dir / "frontend-typescript-react.md").read_bytes()
    assert src_bytes == user_bytes, (
        "Seeded user-layer file must be byte-identical to the source template "
        "on first run."
    )


# --------------------------------------------------------------------------- #
# Second run: user-edited file is preserved (NEVER overwritten)               #
# --------------------------------------------------------------------------- #


def test_second_run_preserves_user_edited_file(
    isolated_templates_dir: Path,
    empty_user_skills_dir: Path,
) -> None:
    """The seed script MUST refuse to overwrite a user-edited file (commit 1f89c02)."""
    user_path = empty_user_skills_dir / "frontend-typescript-react.md"
    custom_content = (
        "# user-edited frontend-typescript-react\n"
        "USER CUSTOM CONTENT — must NEVER be overwritten by seed-skill-templates.sh\n"
    )
    user_path.write_text(custom_content, encoding="utf-8")

    result = _run_seed(isolated_templates_dir, empty_user_skills_dir)

    assert result.returncode == 0
    assert user_path.read_text(encoding="utf-8") == custom_content, (
        "User-layer frontend-typescript-react.md was overwritten — this VIOLATES the "
        "user-layer-only policy from commit 1f89c02."
    )
    assert (
        "user skill already present, template not applied: frontend-typescript-react.md"
        in result.stdout
    )
    assert "seeded=0" in result.stdout
    assert "skipped=1" in result.stdout


def test_idempotent_re_run(
    isolated_templates_dir: Path,
    empty_user_skills_dir: Path,
) -> None:
    """Two consecutive runs: second run reports skipped=1 (idempotent)."""
    first = _run_seed(isolated_templates_dir, empty_user_skills_dir)
    assert first.returncode == 0
    assert "seeded=1" in first.stdout

    second = _run_seed(isolated_templates_dir, empty_user_skills_dir)
    assert second.returncode == 0
    assert "seeded=0" in second.stdout
    assert "skipped=1" in second.stdout


# --------------------------------------------------------------------------- #
# Reconcile (advisory mode) must NOT mutate the user-layer file              #
# --------------------------------------------------------------------------- #


def test_reconcile_advisory_does_not_write_user_layer(
    isolated_templates_dir: Path,
    empty_user_skills_dir: Path,
) -> None:
    """When user-layer content diverges from the template, reconcile is advisory only."""
    assert RECONCILE_SCRIPT.is_file()

    user_path = empty_user_skills_dir / "frontend-typescript-react.md"
    diverged_content = "# diverged user-layer content (NOT the template)\n"
    user_path.write_text(diverged_content, encoding="utf-8")

    result = subprocess.run(
        [
            "bash",
            str(RECONCILE_SCRIPT),
            str(isolated_templates_dir),
            str(empty_user_skills_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"reconcile-skill-templates.sh failed (rc={result.returncode}): "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    assert user_path.read_text(encoding="utf-8") == diverged_content, (
        "reconcile (advisory mode) mutated the user-layer file — this VIOLATES "
        "the 'No automatic write to the user layer ever happens' contract."
    )

    assert "diverged" in result.stdout
    assert "frontend-typescript-react" in result.stdout
