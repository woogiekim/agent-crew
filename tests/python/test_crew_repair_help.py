"""Regression coverage for user-facing crew repair help text."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CREW_BIN = REPO_ROOT / "core" / "bin" / "crew"


def test_crew_repair_help_describes_skill_notes_as_advisory() -> None:
    result = subprocess.run(
        ["bash", str(CREW_BIN), "repair", "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    compact = " ".join(result.stdout.split())
    assert "Skill-use and skill-understanding notes are optional diagnostic coverage" in compact
    assert "advisory gaps rather than completion blockers" in compact
    assert "skill-use plus skill-understanding evidence for loaded non-TDD skills" not in compact
