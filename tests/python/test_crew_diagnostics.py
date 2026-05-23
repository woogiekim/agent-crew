"""Tests for crew diagnostics runtime probes."""

from __future__ import annotations

import importlib.util
import json
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


def test_auto_issue_reporting_blocker_probe_exercises_hook_path(tmp_path: Path):
    ok, detail = diagnostics.auto_issue_reporting_blocker_probe(
        REPO_ROOT / "core",
        tmp_path / "missing-agent-crew-home",
        REPO_ROOT,
    )

    assert ok is True
    assert "native blocker report" in detail


def test_host_bridge_blocker_probe_exercises_cleanup_script(tmp_path: Path):
    state_dir = tmp_path / "home" / "state" / "agent-crew" / "tasks"
    task_id = "20260101-120000-0"
    task_dir = state_dir / task_id
    task_dir.mkdir(parents=True)
    register = {
        "current_phase": "blocked",
        "blocked_by": ["host_bridge_not_invoked"],
    }
    (task_dir / "register.json").write_text(json.dumps(register), encoding="utf-8")
    (task_dir / "progress.buffer.jsonl").write_text(
        json.dumps({
            "ts": "2024-01-01T00:00:00Z",
            "event": "STARTED",
            "agent": "",
            "status": "started",
            "detail": "task started",
        }) + "\n",
        encoding="utf-8",
    )

    ok, detail, matches = diagnostics.host_bridge_blocker_probe(
        state_dir.parent,
        0,
    )

    assert ok is False
    assert matches == 1
    assert task_id in detail


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


def test_stale_state_summary_counts_markers(tmp_path: Path):
    state_dir = tmp_path / "home" / "state" / "project"
    tasks = state_dir / "tasks"
    task_dir = tasks / "20260101-120000-0"
    task_dir.mkdir(parents=True)
    (tasks / "active.20260101-120000-0").write_text("active\n", encoding="utf-8")
    (task_dir / "supervisor-pending.txt").write_text("pending\n", encoding="utf-8")

    summary = diagnostics.stale_state_summary(REPO_ROOT / "core", state_dir)

    assert summary["status"] == "warn"
    assert summary["summary"]["stale_active_markers"] == 1
    assert summary["summary"]["stale_supervisor_pending_sentinels"] == 1
    assert "crew cleanup-state --apply" in summary["recommendation"]


def test_stale_state_summary_passes_when_no_cleanup_targets(tmp_path: Path):
    state_dir = tmp_path / "home" / "state" / "project"
    (state_dir / "tasks").mkdir(parents=True)

    summary = diagnostics.stale_state_summary(REPO_ROOT / "core", state_dir)

    assert summary["status"] == "pass"
    assert summary["summary"]["planned_archival_targets"] == 0
    assert summary["recommendation"] == ""


def test_host_bridge_command_probe_is_reflected_in_diagnostics(monkeypatch):
    monkeypatch.delenv("AGENT_CREW_HOST_BRIDGE_COMMAND", raising=False)

    args = type("Args", (), {
        "project_root": str(Path(__file__).resolve().parent.parent.parent),
        "asset_root": str(Path(__file__).resolve().parent.parent.parent / "core"),
        "agent_crew_home": str(Path(__file__).resolve().parent.parent.parent),
        "format": "text",
    })()
    findings = diagnostics.doctor_host(args)
    status_line = [item for item in findings if item["label"] == "host bridge command readiness"][0]
    assert status_line["status"] == "pass"
    assert "internal handoff fallback" in status_line["detail"]


def test_host_bridge_command_probe_prefers_env_var(tmp_path: Path):
    tmp_bridge = tmp_path / "bridge.sh"
    tmp_bridge.write_text("#!/bin/sh\necho bridge\n", encoding="utf-8")
    tmp_bridge.chmod(0o755)

    ok, detail = diagnostics.host_bridge_command_probe(
        Path(__file__).resolve().parent.parent.parent / "core",
        env={
            "AGENT_CREW_HOST_BRIDGE_COMMAND": str(tmp_bridge),
        },
    )
    assert ok is True
    assert "host bridge ready" in detail
