"""Tests for the memory GC provider delegation shim."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "memory-gc.py"


def _write_fake_mnemos(path: Path) -> Path:
    binary = path / "mnemos"
    binary.write_text(
        """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${MNEMOS_CALL_LOG}"
if [ "${1:-}" = "gc" ]; then
  printf '{"status":"ok","delegated":true}\\n'
  exit 0
fi
exit 9
""",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    return binary


def test_memory_gc_script_delegates_to_mnemos_provider(tmp_path: Path):
    call_log = tmp_path / "calls.log"
    mnemos = _write_fake_mnemos(tmp_path)
    env = {**os.environ, "MNEMOS_BIN": str(mnemos), "MNEMOS_CALL_LOG": str(call_log)}

    result = subprocess.run(
        ["python3", str(SCRIPT), "--format", "json", "--apply"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert '"delegated":true' in result.stdout
    assert call_log.read_text(encoding="utf-8").strip() == "gc --format json --apply"


def test_memory_gc_script_does_not_accept_direct_fts_options(tmp_path: Path):
    result = subprocess.run(
        ["python3", str(SCRIPT), "--fts-db", str(tmp_path / "fts.db")],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_memory_gc_source_has_no_direct_sqlite_or_fts_access():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "sqlite3" not in text
    assert ".agent/state/fts.db" not in text
