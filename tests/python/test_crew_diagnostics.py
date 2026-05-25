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
    assert reports["task_tools"]["severity"] == "info"
    assert reports["task_tools"]["non_blocking"] is True
    assert reports["cost_tracking"]["status"] == "policy-only"
    assert reports["cost_tracking"]["severity"] == "info"
    assert cfg["core_objective"]["status"] == "host_limited_policy_fallback"
    assert cfg["core_objective"]["host_native_runtime_capability_rate"] < 1.0


def test_codex_plan_mode_question_surface_is_reported_conditional(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    state = home / "state" / project.name
    state.mkdir(parents=True)
    (state / "capabilities.json").write_text(
        json.dumps({
            "adapter": "codex",
            "interactive_question": False,
            "interactive_question_mode": "codex_plan_mode_conditional",
            "interactive_question_surface": "request_user_input",
            "task_tools": False,
        }),
        encoding="utf-8",
    )
    args = type("Args", (), {
        "project_root": str(project),
        "asset_root": str(REPO_ROOT / "core"),
        "agent_crew_home": str(home),
    })()

    cfg = diagnostics.effective_config(args)

    reports = {item["name"]: item for item in cfg["capability_reports"]}
    assert reports["interactive_question"]["status"] == "conditional-native"
    assert reports["interactive_question"]["severity"] == "info"
    assert "interactive_question" in cfg["core_objective"]["conditional_capabilities"]
    assert "interactive_question" not in cfg["core_objective"]["policy_only_capabilities"]


def test_doctor_host_reports_codex_policy_only_capabilities_as_info(tmp_path: Path):
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
        "format": "json",
    })()

    findings = diagnostics.doctor_host(args)
    by_label = {item["label"]: item for item in findings}

    assert by_label["capability task_tools policy-only"]["status"] == "info"
    assert by_label["capability cost_tracking policy-only"]["status"] == "info"
    assert by_label["core objective host autonomy ceiling"]["status"] == "info"


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


def test_install_drift_prefers_project_source_checkout_for_installed_assets(tmp_path: Path):
    asset_root = tmp_path / ".agent-crew"
    (asset_root / "scripts").mkdir(parents=True)

    root = diagnostics.install_drift_source_root(asset_root, REPO_ROOT)

    assert root == REPO_ROOT


def test_install_drift_is_unknown_without_source_checkout(tmp_path: Path):
    asset_root = tmp_path / ".agent-crew"
    script = asset_root / "scripts" / "verify-install-drift.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\nraise SystemExit(1)\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()

    status = diagnostics.install_drift(asset_root, project, asset_root)

    assert status["status"] == "unknown"
    assert "source checkout unavailable" in status["detail"]


def test_mnemos_status_reports_missing_backend(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("MNEMOS_BIN", str(tmp_path / "missing-mnemos"))

    status = diagnostics.mnemos_status(env={"PATH": str(tmp_path)})

    assert status["status"] == "missing"
    assert status["available"] is False


def test_mnemos_status_detects_stable_fast_json_search(tmp_path: Path):
    mnemos = tmp_path / "mnemos"
    mnemos.write_text(
        """#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then
  echo "mnemos 1.2.3"
  exit 0
fi
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  echo '{"commands":{"search":{"fast":true,"json":true}}}'
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    mnemos.chmod(0o755)

    status = diagnostics.mnemos_status(env={"MNEMOS_BIN": str(mnemos)})

    assert status["status"] == "supported"
    assert status["stable_fast_search"] is True
    assert status["version"] == "mnemos 1.2.3"


def test_mnemos_status_detects_current_provider_contract(tmp_path: Path):
    mnemos = tmp_path / "mnemos"
    mnemos.write_text(
        """#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then
  echo "no legacy version" >&2
  exit 2
fi
if [ "${1:-}" = "version" ] && [ "${2:-}" = "--json" ]; then
  echo '{"provider":"mnemos","version":"0.1.0","provider_contract_version":"1.0","capabilities":{"fast_search":true},"capability_status":{"fast_search":"supported"}}'
  exit 0
fi
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  echo '{"provider":"mnemos","capabilities":{"fast_search":true},"capability_status":{"fast_search":"supported"}}'
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    mnemos.chmod(0o755)

    status = diagnostics.mnemos_status(env={"MNEMOS_BIN": str(mnemos)})

    assert status["status"] == "supported"
    assert status["stable_fast_search"] is True
    assert status["version"] == "0.1.0"
    assert status["detail"] == "0.1.0; stable fast JSON search advertised"


def test_mnemos_status_uses_version_payload_when_capabilities_command_is_missing(tmp_path: Path):
    mnemos = tmp_path / "mnemos"
    mnemos.write_text(
        """#!/usr/bin/env bash
if [ "${1:-}" = "version" ] && [ "${2:-}" = "--json" ]; then
  echo '{"version":"0.2.0","capabilities":{"fast_search":true}}'
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    mnemos.chmod(0o755)

    status = diagnostics.mnemos_status(env={"MNEMOS_BIN": str(mnemos)})

    assert status["status"] == "supported"
    assert status["stable_fast_search"] is True
    assert status["version"] == "0.2.0"


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


def test_adapter_doc_path_prefers_installed_adapter_docs(tmp_path: Path):
    asset_root = tmp_path / ".agent-crew"
    installed_doc = asset_root / "adapters" / "codex" / "invocation.md"
    installed_doc.parent.mkdir(parents=True)
    installed_doc.write_text("crew:<intent> slash command", encoding="utf-8")

    path = diagnostics.adapter_doc_path(asset_root, asset_root, "codex", "invocation.md")

    assert path == installed_doc


def test_claude_performance_probe_reports_budget_summary(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    (claude_dir / "agent-crew" / "hooks").mkdir(parents=True)
    (claude_dir / "agents").mkdir(parents=True)
    (claude_dir / "agent-crew" / "hooks" / "auto-route.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (claude_dir / "agents" / "planner.md").write_text("---\nname: planner\n---\n", encoding="utf-8")
    (claude_dir / "settings.json").write_text(
        json.dumps({
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"bash {claude_dir}/agent-crew/hooks/auto-route.sh",
                                "timeout": 5,
                            }
                        ],
                    }
                ]
            }
        }),
        encoding="utf-8",
    )

    ok, detail = diagnostics.claude_performance_probe(REPO_ROOT / "core", claude_dir)

    assert ok is True
    assert "hook_timeout_total=5s" in detail
