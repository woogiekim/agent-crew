"""Tests for crew diagnostics runtime probes."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DIAGNOSTICS = REPO_ROOT / "core" / "scripts" / "crew-diagnostics.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


diagnostics = _load_module(DIAGNOSTICS, "crew_diagnostics")


def test_auto_issue_reporting_probe_exercises_hook_path(tmp_path: Path):
    ok, detail = diagnostics.auto_issue_reporting_probe(
        REPO_ROOT / "core",
        tmp_path / "missing-agent-crew-home",
        REPO_ROOT,
    )

    assert ok is True
    assert "hook smoke created native report" in detail
