"""Tests for update fingerprint fast-path diagnostics."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "update-fingerprint.py"


def _make_checkout(root: Path) -> None:
    for rel in (
        "core/commands",
        "core/rules",
        "core/hooks",
        "core/scripts",
        "core/evaluations",
        "core/schemas",
        "core/policies",
        "core/setup",
        "core/agents",
        "core/bin",
        "adapters",
    ):
        (root / rel).mkdir(parents=True)
    (root / "core" / "commands" / "run.md").write_text("run\n", encoding="utf-8")
    (root / "core" / "bin" / "crew").write_text(
        "# deterministic shell entrypoint for agent-crew\n",
        encoding="utf-8",
    )


def _run(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    source = tmp_path / "source"
    project = tmp_path / "project"
    home = tmp_path / "home" / ".agent-crew"
    codex = tmp_path / "home" / ".codex"
    claude = tmp_path / "home" / ".claude"
    path_bin = tmp_path / "home" / ".local" / "bin"
    project.mkdir(exist_ok=True)
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source),
            "--project-root",
            str(project),
            "--agent-crew-home",
            str(home),
            "--codex-home",
            str(codex),
            "--claude-dir",
            str(claude),
            "--path-bin",
            str(path_bin),
            "--fingerprint",
            str(home / "state" / "project" / "update-fingerprint.json"),
            *extra,
        ],
        text=True,
        capture_output=True,
    )


def test_update_fingerprint_explains_missing_previous(tmp_path: Path):
    source = tmp_path / "source"
    _make_checkout(source)

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "no previous fingerprint" in result.stdout


def test_update_fingerprint_reports_changed_categories(tmp_path: Path):
    source = tmp_path / "source"
    _make_checkout(source)
    write = _run(tmp_path, "--write")
    assert write.returncode == 0, write.stdout + write.stderr
    (source / "core" / "commands" / "run.md").write_text("changed\n", encoding="utf-8")

    result = _run(tmp_path, "--format", "json")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["matched"] is False
    assert payload["diff"]["changed"] == 1
    assert payload["diff"]["changed_categories"] == [
        {"category": "source/core", "count": 1}
    ]
