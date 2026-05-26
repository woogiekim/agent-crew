"""Tests for install drift verification helpers."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "verify-install-drift.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_install_drift", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load_module()


def test_compare_tree_handles_missing_roots_and_prunes_extra_files(tmp_path: Path):
    missing = module.compare_tree(tmp_path / "missing-src", tmp_path / "missing-dest", prune_extra=False)
    assert missing["passed"] is True
    assert missing["missing"] == []

    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    (dest / "extra.txt").write_text("extra", encoding="utf-8")

    result = module.compare_tree(src, dest, prune_extra=True)

    assert result["passed"] is True
    assert result["extra"] == ["extra.txt"]
    assert not (dest / "extra.txt").exists()


def test_compare_file_reports_source_missing_dest_missing_and_mismatch(tmp_path: Path):
    assert module.compare_file(tmp_path / "missing-src", tmp_path / "dest")["missing"] == [
        str(tmp_path / "missing-src")
    ]

    src = tmp_path / "src.txt"
    src.write_text("source", encoding="utf-8")
    assert module.compare_file(src, tmp_path / "missing-dest")["missing"] == [
        str(tmp_path / "missing-dest")
    ]

    dest = tmp_path / "dest.txt"
    dest.write_text("different", encoding="utf-8")
    result = module.compare_file(src, dest)
    assert result["passed"] is False
    assert result["mismatched"] == [str(dest)]


def test_verify_install_drift_json_output_accepts_empty_source(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    home = tmp_path / "home"

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--agent-crew-home",
            str(home),
            "--skip-path-bin",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True


def test_verify_install_drift_text_reports_missing_mismatched_and_extra(tmp_path: Path):
    source_root = tmp_path / "source"
    commands_src = source_root / "core" / "commands"
    commands_src.mkdir(parents=True)
    (commands_src / "update.md").write_text("source", encoding="utf-8")

    home = tmp_path / "home"
    system_commands = home / "system" / "commands"
    system_commands.mkdir(parents=True)
    (system_commands / "update.md").write_text("different", encoding="utf-8")
    (system_commands / "extra.md").write_text("extra", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--source-root",
            str(source_root),
            "--agent-crew-home",
            str(home),
            "--skip-path-bin",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: install drift check" in result.stdout
    assert "missing: update.md" in result.stdout
    assert "mismatched: update.md" in result.stdout
    assert "extra: extra.md" in result.stdout
