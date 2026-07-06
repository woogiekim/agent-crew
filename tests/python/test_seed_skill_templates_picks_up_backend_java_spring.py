"""backend-java-spring template seeding contract."""
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
    / "backend-java-spring.md"
)


@pytest.fixture
def isolated_templates_dir(tmp_path: Path) -> Path:
    assert SEED_SCRIPT.is_file(), f"seed-skill-templates.sh missing at {SEED_SCRIPT}"
    assert TEMPLATE_SRC.is_file(), (
        f"backend-java-spring.md missing at {TEMPLATE_SRC}; "
        "Java Spring backend work requires this file to ship."
    )
    src = tmp_path / "templates"
    src.mkdir()
    shutil.copy(TEMPLATE_SRC, src / "backend-java-spring.md")
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


def test_first_run_seeds_backend_java_spring(
    isolated_templates_dir: Path,
    empty_user_skills_dir: Path,
) -> None:
    result = _run_seed(isolated_templates_dir, empty_user_skills_dir)

    assert result.returncode == 0, (
        f"seed-skill-templates.sh failed (rc={result.returncode}): "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    user_path = empty_user_skills_dir / "backend-java-spring.md"
    assert user_path.is_file()
    assert "seeded user skill: backend-java-spring.md" in result.stdout
    assert "seeded=1" in result.stdout


def test_first_run_user_layer_bytes_match_template(
    isolated_templates_dir: Path,
    empty_user_skills_dir: Path,
) -> None:
    _run_seed(isolated_templates_dir, empty_user_skills_dir)

    src_bytes = (isolated_templates_dir / "backend-java-spring.md").read_bytes()
    user_bytes = (empty_user_skills_dir / "backend-java-spring.md").read_bytes()
    assert src_bytes == user_bytes


def test_second_run_preserves_user_edited_file(
    isolated_templates_dir: Path,
    empty_user_skills_dir: Path,
) -> None:
    user_path = empty_user_skills_dir / "backend-java-spring.md"
    custom_content = (
        "# user-edited backend-java-spring\n"
        "USER CUSTOM CONTENT - must NEVER be overwritten by seed-skill-templates.sh\n"
    )
    user_path.write_text(custom_content, encoding="utf-8")

    result = _run_seed(isolated_templates_dir, empty_user_skills_dir)

    assert result.returncode == 0
    assert user_path.read_text(encoding="utf-8") == custom_content
    assert (
        "user skill already present, template not applied: backend-java-spring.md"
        in result.stdout
    )
    assert "seeded=0" in result.stdout
    assert "skipped=1" in result.stdout


def test_reconcile_advisory_does_not_write_user_layer(
    isolated_templates_dir: Path,
    empty_user_skills_dir: Path,
) -> None:
    assert RECONCILE_SCRIPT.is_file()

    user_path = empty_user_skills_dir / "backend-java-spring.md"
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
    assert result.returncode == 0
    assert user_path.read_text(encoding="utf-8") == diverged_content
    assert "diverged" in result.stdout
    assert "backend-java-spring" in result.stdout

