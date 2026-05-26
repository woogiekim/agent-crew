"""Tests for Codex system-agent TOML generation."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "generate-codex-system-agents.py"


def load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_codex_system_agents", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_frontmatter_returns_empty_for_plain_markdown():
    module = load_generator_module()

    assert module.parse_frontmatter("# Plain Agent\n\nNo frontmatter.\n") == {}


def test_generate_codex_system_agents_rejects_missing_source_dir(tmp_path: Path):
    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            str(tmp_path / "missing-source"),
            str(tmp_path / "out"),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "source_dir not found" in result.stderr
