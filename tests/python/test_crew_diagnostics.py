"""Tests for crew diagnostics runtime probes."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DIAGNOSTICS = REPO_ROOT / "core" / "scripts" / "crew-diagnostics.py"


def _load_module(path: Path, name: str):
    script_dir = str(path.parent)
    if script_dir in sys.path:
        sys.path.remove(script_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
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


def test_mnemos_status_detects_recall_v2(tmp_path: Path):
    mnemos = tmp_path / "mnemos"
    mnemos.write_text(
        """#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then
  echo "mnemos 1.2.3"
  exit 0
fi
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  echo '{"commands":{"recall":{"json":true}}}'
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    mnemos.chmod(0o755)

    status = diagnostics.mnemos_status(env={"MNEMOS_BIN": str(mnemos)})

    assert status["status"] == "supported"
    assert status["recall_v2"] is True
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
  echo '{"provider":"mnemos","version":"0.1.0","provider_contract_version":"1.0","capabilities":{"recall_v1":true},"capability_status":{"recall_v1":"supported"}}'
  exit 0
fi
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  echo '{"provider":"mnemos","capabilities":{"recall_v1":true},"capability_status":{"recall_v1":"supported"}}'
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    mnemos.chmod(0o755)

    status = diagnostics.mnemos_status(env={"MNEMOS_BIN": str(mnemos)})

    assert status["status"] == "supported"
    assert status["recall_v2"] is True
    assert status["version"] == "0.1.0"
    assert status["detail"] == "0.1.0; Recall V2 advertised"


def test_mnemos_status_uses_version_payload_when_capabilities_command_is_missing(tmp_path: Path):
    mnemos = tmp_path / "mnemos"
    mnemos.write_text(
        """#!/usr/bin/env bash
if [ "${1:-}" = "version" ] && [ "${2:-}" = "--json" ]; then
  echo '{"version":"0.2.0","capabilities":{"recall_v1":true}}'
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    mnemos.chmod(0o755)

    status = diagnostics.mnemos_status(env={"MNEMOS_BIN": str(mnemos)})

    assert status["status"] == "supported"
    assert status["recall_v2"] is True
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
    assert (
        "internal handoff fallback" in status_line["detail"]
        or "default host bridge ready" in status_line["detail"]
    )


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


def test_codex_hook_config_probe_flags_absent_stop_hook_as_stale_signal(tmp_path: Path):
    codex_home = tmp_path / ".codex"
    project_root = tmp_path / "project"
    (codex_home).mkdir()
    (project_root / ".codex").mkdir(parents=True)
    (codex_home / "hooks.json").write_text("{}\n", encoding="utf-8")
    (project_root / ".codex" / "hooks.json").write_text(
        json.dumps({
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "bash ~/.agent-crew/hooks/post-tool-use-dispatcher.sh",
                                "timeout": 15,
                            }
                        ],
                    }
                ]
            }
        }),
        encoding="utf-8",
    )

    report = diagnostics.codex_hook_config_probe(project_root, codex_home)

    assert report["stop_hook_registered"] is False
    assert report["missing_timeouts"] == []
    assert "Stop hook timeout indicates stale session or external hook source" in report["detail"]


def test_run_cmd_reports_subprocess_exceptions(monkeypatch):
    def raise_run(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(diagnostics.subprocess, "run", raise_run)

    assert diagnostics.run_cmd(["missing"]) == (127, "boom")


def test_adapter_doc_path_falls_back_to_source_root(tmp_path: Path):
    asset_root = tmp_path / "core"
    (tmp_path / "adapters").mkdir()

    path = diagnostics.adapter_doc_path(asset_root, tmp_path / "home", "codex", "missing.md")

    assert path == tmp_path / "adapters" / "codex" / "missing.md"


def test_install_drift_reports_missing_script(tmp_path: Path):
    status = diagnostics.install_drift(tmp_path / "core", tmp_path / "project", tmp_path / "home")

    assert status["status"] == "unknown"
    assert "not found" in status["detail"]


def test_mnemos_status_discovers_path_and_reports_legacy(monkeypatch, tmp_path: Path):
    mnemos = tmp_path / "mnemos"
    mnemos.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    mnemos.chmod(0o755)

    def fake_run(cmd, **_kwargs):
        if cmd[1:] == ["--version"]:
            return 0, "mnemos legacy"
        return 1, ""

    monkeypatch.setattr(diagnostics, "run_cmd", fake_run)
    status = diagnostics.mnemos_status(env={"PATH": str(tmp_path), "MNEMOS_BIN": str(tmp_path / "missing")})

    assert status["status"] == "legacy"
    assert status["path"] == str(mnemos)
    assert "capabilities --json unavailable" in status["detail"]


def test_mnemos_status_reports_partial_capabilities(tmp_path: Path):
    mnemos = tmp_path / "mnemos"
    mnemos.write_text(
        """#!/usr/bin/env bash
if [ "${1:-}" = "version" ] && [ "${2:-}" = "--json" ]; then
  echo '{"version":"0.3.0"}'
  exit 0
fi
if [ "${1:-}" = "capabilities" ] && [ "${2:-}" = "--json" ]; then
  echo '{"commands":{"search":{"fast":true,"json":false}}}'
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    mnemos.chmod(0o755)

    status = diagnostics.mnemos_status(env={"MNEMOS_BIN": str(mnemos)})

    assert status["status"] == "partial"
    assert "capabilities detected without Recall V2" in status["detail"]


def test_effective_config_reports_runtime_enforced_capabilities(monkeypatch, tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    state = home / "state" / project.name
    state.mkdir(parents=True)
    (state / "capabilities.json").write_text(
        json.dumps({
            "adapter": "claude",
            "task_tools": True,
            "agent_background": True,
            "monitor_tool": True,
            "cost_tracking": True,
            "hook_system": True,
            "interactive_question": True,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(diagnostics, "mnemos_status", lambda: {"status": "missing"})
    monkeypatch.setattr(diagnostics, "install_drift", lambda *_args: {"status": "pass", "detail": "ok"})
    args = argparse.Namespace(project_root=str(project), asset_root=str(REPO_ROOT / "core"), agent_crew_home=str(home))

    cfg = diagnostics.effective_config(args)

    assert all(report["status"] == "runtime-enforced" for report in cfg["capability_reports"])
    assert cfg["core_objective"]["status"] == "native_runtime_ready"


def test_auto_issue_reporting_probe_missing_hook_and_failures(tmp_path: Path):
    missing_ok, missing_detail = diagnostics.auto_issue_reporting_probe(
        tmp_path / "missing-core",
        tmp_path / "home",
        tmp_path / "project",
    )
    assert missing_ok is False
    assert missing_detail == "auto issue hook not found"

    asset_root = tmp_path / "asset"
    hook = asset_root / "hooks" / "auto-issue-report.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
    hook.chmod(0o755)
    ok, detail = diagnostics.auto_issue_reporting_probe(asset_root, tmp_path / "home", tmp_path / "project")
    assert ok is False
    assert detail == "hook rc=7"

    hook.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    ok, detail = diagnostics.auto_issue_reporting_probe(asset_root, tmp_path / "home", tmp_path / "project")
    assert ok is False
    assert "no native report" in detail


def test_host_bridge_blocker_probe_error_shapes(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(diagnostics, "__file__", str(tmp_path / "crew-diagnostics.py"))
    ok, detail, count = diagnostics.host_bridge_blocker_probe(tmp_path / "state", 0)
    assert (ok, detail, count) == (False, "host-bridge cleanup helper not found", 0)

    monkeypatch.setattr(diagnostics, "__file__", str(DIAGNOSTICS))
    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (2, "bad"))
    assert diagnostics.host_bridge_blocker_probe(tmp_path / "state", 0) == (
        False,
        "host-bridge stale blocker probe rc=2",
        0,
    )

    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (0, "{bad"))
    assert diagnostics.host_bridge_blocker_probe(tmp_path / "state", 0) == (
        False,
        "host-bridge stale blocker probe returned invalid json",
        0,
    )

    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (0, '{"matched":{"task_id":"x"}}'))
    assert diagnostics.host_bridge_blocker_probe(tmp_path / "state", 0) == (
        False,
        "host-bridge stale blocker probe format invalid",
        0,
    )

    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (0, '{"matched":[]}'))
    assert diagnostics.host_bridge_blocker_probe(tmp_path / "state", 0) == (
        True,
        "no stale host-bridge blocker tasks",
        0,
    )


def test_host_bridge_command_probe_error_and_default_paths(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(diagnostics, "__file__", str(tmp_path / "crew-diagnostics.py"))
    ok, detail = diagnostics.host_bridge_command_probe(tmp_path / "asset")
    assert ok is False
    assert detail == "host-bridge command checker not found"

    monkeypatch.setattr(diagnostics, "__file__", str(DIAGNOSTICS))
    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (127, ""))
    assert diagnostics.host_bridge_command_probe(REPO_ROOT / "core") == (
        False,
        "host-bridge checker could not run",
    )

    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (9, ""))
    assert diagnostics.host_bridge_command_probe(REPO_ROOT / "core") == (
        False,
        "host-bridge checker returned unexpected rc=9",
    )

    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (0, "{bad"))
    assert diagnostics.host_bridge_command_probe(REPO_ROOT / "core") == (
        False,
        "host-bridge checker returned invalid json (rc=0)",
    )

    monkeypatch.setattr(
        diagnostics,
        "run_cmd",
        lambda *_args, **_kwargs: (0, '{"ready":true,"defaulted":true,"command_head":"codex"}'),
    )
    assert diagnostics.host_bridge_command_probe(REPO_ROOT / "core") == (
        True,
        "default host bridge ready: codex",
    )

    monkeypatch.setattr(
        diagnostics,
        "run_cmd",
        lambda *_args, **_kwargs: (1, '{"ready":false,"status":"bad","reason":"denied"}'),
    )
    assert diagnostics.host_bridge_command_probe(REPO_ROOT / "core") == (False, "denied")


def test_claude_performance_probe_missing_skipped_and_invalid(monkeypatch, tmp_path: Path):
    ok, detail = diagnostics.claude_performance_probe(tmp_path / "asset")
    assert ok is False
    assert detail == "claude performance checker not found"

    asset = tmp_path / "asset-with-script"
    script = asset / "scripts" / "claude-performance-check.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    ok, detail = diagnostics.claude_performance_probe(asset, tmp_path / "not-installed")
    assert ok is True
    assert "skipped" in detail

    claude_dir = tmp_path / "claude"
    (claude_dir / "agents").mkdir(parents=True)
    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (0, "{bad"))
    ok, detail = diagnostics.claude_performance_probe(asset, claude_dir)
    assert ok is False
    assert "invalid json" in detail


def test_auto_issue_reporting_blocker_probe_missing_hook_and_failures(tmp_path: Path):
    missing_ok, missing_detail = diagnostics.auto_issue_reporting_blocker_probe(
        tmp_path / "missing-core",
        tmp_path / "home",
        tmp_path / "project",
    )
    assert missing_ok is False
    assert missing_detail == "auto issue hook not found"

    asset_root = tmp_path / "asset"
    hook = asset_root / "hooks" / "auto-issue-report.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/usr/bin/env bash\nexit 6\n", encoding="utf-8")
    hook.chmod(0o755)
    ok, detail = diagnostics.auto_issue_reporting_blocker_probe(asset_root, tmp_path / "home", tmp_path / "project")
    assert ok is False
    assert detail == "hook rc=6"

    hook.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    ok, detail = diagnostics.auto_issue_reporting_blocker_probe(asset_root, tmp_path / "home", tmp_path / "project")
    assert ok is False
    assert "no native blocker report" in detail


def test_stale_state_summary_error_paths(monkeypatch, tmp_path: Path):
    missing = diagnostics.stale_state_summary(tmp_path / "asset", tmp_path / "state")
    assert missing["status"] == "unknown"
    assert "not found" in missing["detail"]

    asset = tmp_path / "asset-with-script"
    script = asset / "scripts" / "cleanup-task-state.py"
    script.parent.mkdir(parents=True)
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (3, "bad"))
    rc_status = diagnostics.stale_state_summary(asset, tmp_path / "state")
    assert rc_status == {"status": "warn", "detail": "cleanup probe rc=3"}

    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (0, "{bad"))
    invalid = diagnostics.stale_state_summary(asset, tmp_path / "state")
    assert invalid == {"status": "warn", "detail": "cleanup probe returned invalid json"}


def test_doctor_static_missing_and_json_command(monkeypatch, tmp_path: Path):
    args = argparse.Namespace(asset_root=str(tmp_path / "asset"), project_root=str(tmp_path / "project"), format="text")
    assert diagnostics.doctor_static(args)[0]["detail"] == "script not found"

    checker = tmp_path / "asset-with-checker" / "scripts" / "framework-review-check.py"
    checker.parent.mkdir(parents=True)
    checker.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return 0, '{"ok": true}'

    monkeypatch.setattr(diagnostics, "run_cmd", fake_run)
    args = argparse.Namespace(asset_root=str(checker.parent.parent), project_root=str(tmp_path / "project"), format="json")
    finding = diagnostics.doctor_static(args)[0]

    assert finding["status"] == "pass"
    assert captured["cmd"][-2:] == ["--format", "json"]

    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (0, "framework ok"))
    args = argparse.Namespace(asset_root=str(checker.parent.parent), project_root=str(tmp_path / "project"), format="text")
    finding = diagnostics.doctor_static(args)[0]
    assert finding["status"] == "pass"


def test_doctor_runtime_reports_fallback_recommendations(monkeypatch, tmp_path: Path):
    asset = tmp_path / "asset"
    (asset / "bin").mkdir(parents=True)
    (asset / "bin" / "crew").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    report_file = tmp_path / "report-file"
    report_file.write_text("not a dir", encoding="utf-8")
    monkeypatch.setenv("AGENT_CREW_REPORT_STATE_DIR", str(report_file))
    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (0, "ok\nlast line"))
    monkeypatch.setattr(diagnostics, "auto_issue_reporting_probe", lambda *_args: (True, "auto ok"))
    monkeypatch.setattr(diagnostics, "auto_issue_reporting_blocker_probe", lambda *_args: (True, "blocker ok"))
    monkeypatch.setattr(
        diagnostics,
        "stale_state_summary",
        lambda *_args: {"status": "warn", "detail": "stale detail", "recommendation": "cleanup now"},
    )
    monkeypatch.setattr(diagnostics, "host_bridge_blocker_probe", lambda *_args: (False, "bridge detail", 2))
    monkeypatch.setattr(diagnostics, "mnemos_status", lambda: {"status": "supported", "detail": "mnemos ok"})
    args = argparse.Namespace(
        asset_root=str(asset),
        agent_crew_home=str(tmp_path / "home"),
        project_root=str(tmp_path / "project"),
        format="json",
    )

    findings = diagnostics.doctor_runtime(args)
    by_label = {item["label"]: item for item in findings}

    assert by_label["schema validation"]["detail"] == "validator not found"
    assert by_label["report outbox creation"]["status"] == "warn"
    assert "cleanup now" in by_label["stale state markers"]["detail"]
    assert "crew cleanup-host-bridge" in by_label["stale host-bridge blockers"]["detail"]


def test_doctor_runtime_validator_and_outbox_success(monkeypatch, tmp_path: Path):
    asset = tmp_path / "asset"
    (asset / "bin").mkdir(parents=True)
    (asset / "scripts").mkdir(parents=True)
    (asset / "bin" / "crew").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (asset / "scripts" / "validate-state-schema.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    report_root = tmp_path / "reports"
    monkeypatch.setenv("AGENT_CREW_REPORT_STATE_DIR", str(report_root))
    monkeypatch.setattr(diagnostics, "run_cmd", lambda *_args, **_kwargs: (0, "ok\nvalid"))
    monkeypatch.setattr(diagnostics, "auto_issue_reporting_probe", lambda *_args: (True, "auto ok"))
    monkeypatch.setattr(diagnostics, "auto_issue_reporting_blocker_probe", lambda *_args: (True, "blocker ok"))
    monkeypatch.setattr(
        diagnostics,
        "stale_state_summary",
        lambda *_args: {"status": "pass", "detail": "clean", "recommendation": ""},
    )
    monkeypatch.setattr(diagnostics, "host_bridge_blocker_probe", lambda *_args: (True, "bridge clean", 0))
    monkeypatch.setattr(diagnostics, "mnemos_status", lambda: {"status": "missing", "detail": "mnemos missing"})
    args = argparse.Namespace(
        asset_root=str(asset),
        agent_crew_home=str(tmp_path / "home"),
        project_root=str(tmp_path / "project"),
        format="json",
    )

    findings = diagnostics.doctor_runtime(args)
    by_label = {item["label"]: item for item in findings}

    assert by_label["schema validation"]["detail"] == "valid"
    assert by_label["report outbox creation"]["status"] == "pass"
    assert (report_root / "outbox").is_dir()


def _config_payload() -> dict:
    return {
        "active_adapter": "codex",
        "state_dir": "/state",
        "memory_backend": "mnemos",
        "mnemos": {"status": "supported", "detail": "ok"},
        "install_drift": {"status": "pass", "detail": "ok"},
        "core_objective": diagnostics.capability_ceiling({
            "adapter": "codex",
            "task_tools": True,
            "agent_background": True,
            "monitor_tool": True,
            "cost_tracking": True,
            "hook_system": True,
            "interactive_question": True,
        }),
        "capability_flags": {
            "task_tools": True,
            "agent_background": True,
            "monitor_tool": True,
            "cost_tracking": True,
            "hook_system": True,
            "interactive_question": True,
        },
        "capability_reports": [
            {"name": name, "status": "runtime-enforced", "detail": "ok"}
            for name in (
                "task_tools",
                "agent_background",
                "monitor_tool",
                "cost_tracking",
                "hook_system",
                "interactive_question",
            )
        ],
        "budgets": {"stage_timeout_seconds": 0, "task_token_budget": ""},
        "timeouts": {"auto_issue_timeout_seconds": 8, "stale_host_bridge_seconds": 0},
        "report_settings": {"publish": "none", "state_dir": "/reports"},
    }


def test_cmd_doctor_json_and_cmd_config_modes(monkeypatch, capsys):
    monkeypatch.setattr(diagnostics, "doctor_static", lambda _args: [{"label": "static", "status": "pass", "detail": ""}])
    monkeypatch.setattr(diagnostics, "doctor_runtime", lambda _args: [{"label": "runtime", "status": "pass", "detail": ""}])
    monkeypatch.setattr(diagnostics, "doctor_host", lambda _args: [{"label": "host", "status": "pass", "detail": ""}])
    args = argparse.Namespace(mode="all", format="json")

    assert diagnostics.cmd_doctor(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["label"] for item in payload["findings"]] == ["static", "runtime", "host"]

    args = argparse.Namespace(mode="static", format="text")
    assert diagnostics.cmd_doctor(args) == 0
    assert "== static ==" in capsys.readouterr().out

    monkeypatch.setattr(diagnostics, "effective_config", lambda _args: _config_payload())
    args = argparse.Namespace(subcommand="dump", format="json")
    assert diagnostics.cmd_config(args) == 0
    assert json.loads(capsys.readouterr().out)["active_adapter"] == "codex"

    args = argparse.Namespace(subcommand="dump", format="text")
    assert diagnostics.cmd_config(args) == 0
    assert "capability.task_tools" in capsys.readouterr().out

    called = {}

    def fake_cmd_doctor(args):
        called["mode"] = args.mode
        return 5

    monkeypatch.setattr(diagnostics, "cmd_doctor", fake_cmd_doctor)
    args = argparse.Namespace(subcommand="doctor", format="json")
    assert diagnostics.cmd_config(args) == 5
    assert called["mode"] == "runtime"


def test_main_parses_doctor_command(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(diagnostics, "cmd_doctor", lambda _args: 7)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crew-diagnostics.py",
            "--project-root",
            str(tmp_path / "project"),
            "--asset-root",
            str(REPO_ROOT / "core"),
            "--agent-crew-home",
            str(tmp_path / "home"),
            "doctor",
            "--mode",
            "static",
            "--format",
            "json",
        ],
    )

    assert diagnostics.main() == 7
