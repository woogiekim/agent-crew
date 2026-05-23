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


def test_codex_false_capabilities_are_reported_as_policy_only(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    state = home / "state" / project.name
    state.mkdir(parents=True)
    (state / "capabilities.json").write_text(
        '{"adapter":"codex","task_tools":false,"cost_tracking":false}\n',
        encoding="utf-8",
    )
    args = type("Args", (), {
        "project_root": str(project),
        "asset_root": str(REPO_ROOT / "core"),
        "agent_crew_home": str(home),
    })()

    cfg = diagnostics.effective_config(args)

    reports = {item["name"]: item for item in cfg["capability_reports"]}
    assert reports["task_tools"]["status"] == "policy-only"
    assert reports["cost_tracking"]["status"] == "policy-only"
