#!/usr/bin/env python3
"""Read-only diagnostics and effective config rendering for crew CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def run_cmd(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
            env=env,
        )
    except Exception as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def provider_capability_supported(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.lower() == "supported")


def provider_payload_supports_fast_search(payload: dict[str, Any]) -> bool:
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    commands = payload.get("commands") if isinstance(payload.get("commands"), dict) else {}
    capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
    capability_status = payload.get("capability_status") if isinstance(payload.get("capability_status"), dict) else {}
    search = commands.get("search") if isinstance(commands.get("search"), dict) else {}

    capability_maps = (payload, features, capabilities, capability_status)
    return bool(
        any(
            provider_capability_supported(mapping.get(name))
            for mapping in capability_maps
            for name in ("search_fast", "fast_search")
        )
        or (
            provider_capability_supported(search.get("fast"))
            and provider_capability_supported(search.get("json"))
        )
    )


def source_root(asset_root: Path) -> Path:
    return asset_root.parent if asset_root.name == "core" and (asset_root.parent / "adapters").is_dir() else asset_root


def is_source_checkout(path: Path) -> bool:
    return (path / "core").is_dir() and (path / "adapters").is_dir()


def install_drift_source_root(asset_root: Path, project_root: Path) -> Path | None:
    if is_source_checkout(project_root):
        return project_root

    root = source_root(asset_root)
    if is_source_checkout(root):
        return root

    return None


def adapter_doc_path(asset_root: Path, agent_crew_home: Path, adapter: str, filename: str) -> Path:
    for candidate in (
        source_root(asset_root) / "adapters" / adapter / filename,
        agent_crew_home / "adapters" / adapter / filename,
        asset_root / "adapters" / adapter / filename,
    ):
        if candidate.is_file():
            return candidate
    return source_root(asset_root) / "adapters" / adapter / filename


def install_drift(asset_root: Path, project_root: Path, agent_crew_home: Path) -> dict[str, Any]:
    script = asset_root / "scripts" / "verify-install-drift.py"
    root = install_drift_source_root(asset_root, project_root)
    if not script.is_file():
        return {"status": "unknown", "detail": "verify-install-drift.py not found"}
    if root is None:
        return {
            "status": "unknown",
            "detail": "source checkout unavailable; run crew update for deterministic drift verification",
        }
    rc, out = run_cmd(
        [
            sys.executable,
            str(script),
            "--source-root",
            str(root),
            "--agent-crew-home",
            str(agent_crew_home),
            "--skip-path-bin",
        ]
    )
    return {"status": "pass" if rc == 0 else "warn", "detail": out.splitlines()[-1] if out else f"rc={rc}"}


def mnemos_status(env: dict[str, str] | None = None) -> dict[str, Any]:
    probe_env = os.environ.copy()
    if env:
        probe_env.update(env)

    configured = probe_env.get("MNEMOS_BIN") or str(Path.home() / ".local" / "bin" / "mnemos")
    path = Path(configured).expanduser()
    if not path.is_file() or not os.access(path, os.X_OK):
        discovered = shutil.which("mnemos", path=probe_env.get("PATH"))
        if discovered:
            path = Path(discovered)
        else:
            return {
                "available": False,
                "path": configured,
                "version": "unavailable",
                "status": "missing",
                "stable_fast_search": False,
                "detail": "mnemos CLI not found; memory provider will degrade to no-backend mode",
            }

    version = "unknown"
    version_payload: dict[str, Any] = {}
    rc, version_out = run_cmd([str(path), "version", "--json"], env=probe_env)
    if rc == 0 and version_out:
        try:
            parsed = json.loads(version_out)
            if isinstance(parsed, dict):
                version_payload = parsed
                detected_version = parsed.get("version")
                if isinstance(detected_version, str) and detected_version:
                    version = detected_version
        except Exception:
            version_payload = {}

    if version == "unknown":
        rc, version_out = run_cmd([str(path), "--version"], env=probe_env)
        version = version_out.splitlines()[0] if rc == 0 and version_out else "unknown"

    stable_fast_search = False
    caps_status = "unknown"
    caps_detail = ""
    caps_rc, caps_out = run_cmd([str(path), "capabilities", "--json"], env=probe_env)
    if caps_rc == 0 and caps_out:
        try:
            caps = json.loads(caps_out)
            caps = caps if isinstance(caps, dict) else {}
            stable_fast_search = provider_payload_supports_fast_search(caps)
            caps_status = "supported" if stable_fast_search else "partial"
            caps_detail = "stable fast JSON search advertised" if stable_fast_search else "capabilities detected without stable fast JSON search"
        except Exception:
            caps_status = "unknown"
            caps_detail = "capabilities output was not valid JSON"
    elif version_payload:
        stable_fast_search = provider_payload_supports_fast_search(version_payload)
        caps_status = "supported" if stable_fast_search else "partial"
        caps_detail = "stable fast JSON search advertised" if stable_fast_search else "version metadata detected without stable fast JSON search"
    else:
        caps_status = "legacy"
        caps_detail = "capabilities --json unavailable; regular search and deprecated fallback may be used"

    if version == "unknown":
        status = "unknown"
        detail = f"mnemos version unknown; {caps_detail}"
    elif caps_status == "supported":
        status = "supported"
        detail = f"{version}; {caps_detail}"
    elif caps_status == "legacy":
        status = "legacy"
        detail = f"{version}; {caps_detail}"
    else:
        status = "partial"
        detail = f"{version}; {caps_detail}"

    return {
        "available": True,
        "path": str(path),
        "version": version,
        "status": status,
        "stable_fast_search": stable_fast_search,
        "detail": detail,
    }


def effective_config(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    asset_root = Path(args.asset_root).resolve()
    agent_crew_home = Path(args.agent_crew_home).expanduser()
    project_name = project_root.name
    state_dir = agent_crew_home / "state" / project_name
    capabilities = load_json(state_dir / "capabilities.json")
    flags = {
        "task_tools": bool(capabilities.get("task_tools")),
        "agent_background": bool(capabilities.get("agent_background")),
        "monitor_tool": bool(capabilities.get("monitor_tool")),
        "cost_tracking": bool(capabilities.get("cost_tracking")),
        "hook_system": bool(capabilities.get("hook_system")),
        "interactive_question": bool(capabilities.get("interactive_question")),
    }
    active_adapter = capabilities.get("adapter") or capabilities.get("host") or os.environ.get("AGENT_CREW_HOST", "unknown")
    capability_reports = []
    for name, enabled in flags.items():
        if enabled:
            status = "runtime-enforced"
            severity = "pass"
            detail = "active adapter advertises this runtime capability"
        elif active_adapter == "codex" and name in {"hook_system", "interactive_question", "task_tools", "agent_background", "monitor_tool", "cost_tracking"}:
            status = "policy-only"
            severity = "info"
            detail = "Codex uses prompt/file fallbacks; this capability is not runtime-enforced"
        else:
            status = "unavailable"
            severity = "warn"
            detail = "active adapter does not advertise this runtime capability"
        capability_reports.append({
            "name": name,
            "enabled": enabled,
            "status": status,
            "severity": severity,
            "non_blocking": severity == "info",
            "detail": detail,
        })
    report_publish = os.environ.get("AGENT_CREW_REPORT_PUBLISH") or os.environ.get("AGENT_CREW_AUTO_ISSUE_PUBLISH") or "none"
    return {
        "project_root": str(project_root),
        "state_dir": str(state_dir),
        "active_adapter": active_adapter,
        "capability_flags": flags,
        "capability_reports": capability_reports,
        "budgets": {
            "stage_timeout_seconds": int(os.environ.get("AGENT_CREW_STAGE_TIMEOUT_SECONDS") or 0),
            "task_token_budget": os.environ.get("AGENT_CREW_TASK_TOKEN_BUDGET", ""),
        },
        "timeouts": {
            "auto_issue_timeout_seconds": int(os.environ.get("AGENT_CREW_AUTO_ISSUE_TIMEOUT_SECONDS") or 8),
            "stale_host_bridge_seconds": int(os.environ.get("AGENT_CREW_STALE_HOST_BRIDGE_SECONDS") or 0),
        },
        "report_settings": {
            "publish": report_publish,
            "state_dir": os.environ.get("AGENT_CREW_REPORT_STATE_DIR", str(agent_crew_home / "state" / "reports")),
        },
        "memory_backend": os.environ.get("AGENT_CREW_MEMORY_BACKEND", "mnemos"),
        "mnemos": mnemos_status(),
        "install_drift": install_drift(asset_root, project_root, agent_crew_home),
    }


def print_status(label: str, ok: bool, detail: str = "", *, emit: bool = True) -> dict[str, Any]:
    status = "PASS" if ok else "WARN"
    line = f"{status}: {label}"
    if detail:
        line += f" — {detail}"
    if emit:
        print(line)
    return {"label": label, "status": status.lower(), "detail": detail}


def print_finding(label: str, status: str, detail: str = "", *, emit: bool = True) -> dict[str, Any]:
    normalized = status.lower()
    line = f"{normalized.upper()}: {label}"
    if detail:
        line += f" — {detail}"
    if emit:
        print(line)
    return {"label": label, "status": normalized, "detail": detail}


def auto_issue_reporting_probe(asset_root: Path, agent_crew_home: Path, project_root: Path) -> tuple[bool, str]:
    hook = asset_root / "hooks" / "auto-issue-report.sh"
    if not hook.is_file():
        return False, "auto issue hook not found"

    hook_home = agent_crew_home
    if not (hook_home / "bin" / "crew").is_file() and (asset_root / "bin" / "crew").is_file():
        hook_home = asset_root

    with tempfile.TemporaryDirectory(prefix="agent-crew-report-probe-") as tmp:
        report_root = Path(tmp) / "reports"
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "agent-crew error: runtime doctor smoke traceback",
        }
        env = os.environ.copy()
        env.update(
            {
                "AGENT_CREW_HOME": str(hook_home),
                "AGENT_CREW_REPORT_STATE_DIR": str(report_root),
                "AGENT_CREW_AUTO_ISSUE_STATE_DIR": str(report_root),
                "AGENT_CREW_AUTO_ISSUE_DRY_RUN": "0",
                "AGENT_CREW_AUTO_ISSUE_REPORT": "1",
                "AGENT_CREW_AUTO_ISSUE_REPORT_DISABLED": "0",
                "AGENT_CREW_REPORT_PUBLISH": "none",
                "AGENT_CREW_AUTO_ISSUE_PUBLISH": "none",
                "PROJECT_ROOT": str(project_root),
            }
        )
        proc = subprocess.run(
            ["bash", str(hook)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
            env=env,
        )
        reported = list((report_root / "reported").glob("*.json"))
        outbox = list((report_root / "outbox").glob("*.json"))
        if proc.returncode != 0:
            return False, f"hook rc={proc.returncode}"
        if not reported or not outbox:
            return False, "hook completed but no native report/outbox record was created"
        return True, "hook smoke created native report and outbox record"


def host_bridge_blocker_probe(state_dir: Path, min_age_seconds: int) -> tuple[bool, str, int]:
    script = Path(__file__).resolve().parent / "cleanup-host-bridge-blockers.py"
    if not script.is_file():
        return False, "host-bridge cleanup helper not found", 0

    rc, out = run_cmd(
        [
            sys.executable,
            str(script),
            "--state-dir",
            str(state_dir),
            "--format",
            "json",
            "--min-age-seconds",
            str(min_age_seconds),
        ]
    )
    if rc != 0:
        return False, f"host-bridge stale blocker probe rc={rc}", 0
    try:
        payload = json.loads(out)
    except Exception:
        return False, "host-bridge stale blocker probe returned invalid json", 0
    matches = payload.get("matched") or []
    if not isinstance(matches, list):
        return False, "host-bridge stale blocker probe format invalid", 0
    if not matches:
        return True, "no stale host-bridge blocker tasks", 0
    task_ids = ", ".join(item.get("task_id", "unknown") for item in matches[:3])
    detail = (
        f"host_bridge_not_invoked tasks={len(matches)} "
        f"(sample={task_ids})"
    )
    return False, detail, len(matches)


def host_bridge_command_probe(
    asset_root: Path,
    *,
    agent_crew_home: Path | None = None,
    project_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    script = Path(__file__).resolve().parent / "check-host-bridge.py"
    if not script.is_file():
        return False, "host-bridge command checker not found"

    probe_env = os.environ.copy()
    if env:
        probe_env.update(env)

    command = [sys.executable, str(script), "--json"]
    if agent_crew_home is not None:
        command.extend(["--agent-crew-home", str(agent_crew_home)])
    if project_root is not None:
        command.extend(["--project-root", str(project_root)])

    rc, out = run_cmd(command, env=probe_env)
    if rc == 127:
        return False, "host-bridge checker could not run"
    if rc not in (0, 1, 2):
        return False, f"host-bridge checker returned unexpected rc={rc}"

    try:
        payload = json.loads(out)
    except Exception:
        return False, f"host-bridge checker returned invalid json (rc={rc})"

    if payload.get("ready"):
        if payload.get("defaulted"):
            return True, f"default host bridge ready: {payload.get('command_head', '')}"
        return True, f"host bridge ready: {payload.get('command_head', '')}"
    if payload.get("status") in {"missing", "empty"}:
        return True, payload.get("reason", "internal handoff fallback available")
    return False, payload.get("reason", "unknown host bridge status")


def claude_performance_probe(asset_root: Path, claude_dir: Path | None = None) -> tuple[bool, str]:
    script = asset_root / "scripts" / "claude-performance-check.py"
    if not script.is_file():
        return False, "claude performance checker not found"

    target_dir = claude_dir or Path(os.environ.get("CLAUDE_DIR", str(Path.home() / ".claude"))).expanduser()
    if not (target_dir / "agent-crew").is_dir() and not (target_dir / "agents").is_dir():
        return True, f"Claude adapter not installed at {target_dir}; skipped"

    rc, out = run_cmd([sys.executable, str(script), "--claude-dir", str(target_dir), "--format", "json"])
    try:
        payload = json.loads(out)
    except Exception:
        return False, f"claude performance checker returned invalid json (rc={rc})"
    summary = payload.get("summary", f"rc={rc}")
    return rc == 0, str(summary)


def auto_issue_reporting_blocker_probe(asset_root: Path, agent_crew_home: Path, project_root: Path) -> tuple[bool, str]:
    hook = asset_root / "hooks" / "auto-issue-report.sh"
    if not hook.is_file():
        return False, "auto issue hook not found"

    hook_home = agent_crew_home
    if not (hook_home / "bin" / "crew").is_file() and (asset_root / "bin" / "crew").is_file():
        hook_home = asset_root

    with tempfile.TemporaryDirectory(prefix="agent-crew-report-blocker-probe-") as tmp:
        report_root = Path(tmp) / "reports"
        payload = {
            "source": "supervisor_blocked",
            "status": "blocked",
            "blocker": "state_schema_invalid",
            "task_id": "20260523-000000-0",
            "detail": "validate-state-schema.py failed during runtime doctor smoke",
        }
        env = os.environ.copy()
        env.update(
            {
                "AGENT_CREW_HOME": str(hook_home),
                "AGENT_CREW_REPORT_STATE_DIR": str(report_root),
                "AGENT_CREW_AUTO_ISSUE_STATE_DIR": str(report_root),
                "AGENT_CREW_AUTO_ISSUE_DRY_RUN": "0",
                "AGENT_CREW_AUTO_ISSUE_REPORT": "1",
                "AGENT_CREW_AUTO_ISSUE_REPORT_DISABLED": "0",
                "AGENT_CREW_REPORT_PUBLISH": "none",
                "AGENT_CREW_AUTO_ISSUE_PUBLISH": "none",
                "PROJECT_ROOT": str(project_root),
            }
        )
        proc = subprocess.run(
            ["bash", str(hook)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
            env=env,
        )
        reported = list((report_root / "reported").glob("*.json"))
        outbox = list((report_root / "outbox").glob("*.json"))
        if proc.returncode != 0:
            return False, f"hook rc={proc.returncode}"
        if not reported or not outbox:
            return False, "hook completed but no native blocker report/outbox record was created"
        return True, "hook smoke created native blocker report and outbox record"


def stale_state_summary(asset_root: Path, state_dir: Path) -> dict[str, Any]:
    cleanup = asset_root / "scripts" / "cleanup-task-state.py"
    if not cleanup.is_file():
        return {"status": "unknown", "detail": "cleanup-task-state.py not found"}
    rc, out = run_cmd(
        [
            sys.executable,
            str(cleanup),
            "--state-dir",
            str(state_dir),
            "--format",
            "json",
        ]
    )
    if rc != 0:
        return {"status": "warn", "detail": f"cleanup probe rc={rc}"}
    try:
        payload = json.loads(out)
    except Exception:
        return {"status": "warn", "detail": "cleanup probe returned invalid json"}
    summary = payload.get("summary") or {}
    archival_targets = int(summary.get("planned_archival_targets") or 0)
    review_targets = int(summary.get("operator_review_targets") or 0)
    status = "warn" if archival_targets or review_targets else "pass"
    recommendation = (
        "run crew cleanup-state --apply after confirming no live workflow owns these markers"
        if archival_targets
        else "review stale handoff-ready tasks with crew resume, crew repair, or crew cancel"
        if review_targets
        else ""
    )
    return {
        "status": status,
        "summary": summary,
        "detail": (
            f"active_markers={summary.get('stale_active_markers', 0)} "
            f"supervisor_pending={summary.get('stale_supervisor_pending_sentinels', 0)} "
            f"handoff_ready={summary.get('stale_handoff_ready_tasks', 0)} "
            f"archival_targets={archival_targets} "
            f"review_targets={review_targets}"
        ),
        "recommendation": recommendation,
    }


def doctor_static(args: argparse.Namespace) -> list[dict[str, Any]]:
    checker = Path(args.asset_root) / "scripts" / "framework-review-check.py"
    if not checker.is_file():
        return [print_status("framework review check", False, "script not found", emit=args.format == "text")]
    cmd = [sys.executable, str(checker), "--project-root", args.project_root]
    if args.format == "json":
        cmd.extend(["--format", "json"])
    rc, out = run_cmd(cmd)
    if out and args.format == "text":
        print(out)
    return [{"label": "framework review check", "status": "pass" if rc == 0 else "warn", "detail": f"rc={rc}"}]


def doctor_runtime(args: argparse.Namespace) -> list[dict[str, Any]]:
    asset_root = Path(args.asset_root)
    agent_crew_home = Path(args.agent_crew_home).expanduser()
    project_root = Path(args.project_root).resolve()
    state_dir = agent_crew_home / "state" / project_root.name
    findings: list[dict[str, Any]] = []
    for command in ("bash", "python3", "git"):
        findings.append(print_status(f"command available: {command}", shutil.which(command) is not None, emit=args.format == "text"))
    validator = asset_root / "scripts" / "validate-state-schema.py"
    if validator.is_file():
        rc, out = run_cmd([sys.executable, str(validator), "--state-dir", str(state_dir), "--format", "text"])
        findings.append(print_status("schema validation", rc in (0, 1), out.splitlines()[-1] if out else f"rc={rc}", emit=args.format == "text"))
    else:
        findings.append(print_status("schema validation", False, "validator not found", emit=args.format == "text"))
    trace_rc, trace_out = run_cmd([str(asset_root / "bin" / "crew"), "trace", "--recent", "1"], cwd=project_root)
    findings.append(print_status("trace rendering", trace_rc == 0, trace_out.splitlines()[0] if trace_out else "ok", emit=args.format == "text"))
    report_root = Path(os.environ.get("AGENT_CREW_REPORT_STATE_DIR", agent_crew_home / "state" / "reports"))
    try:
        (report_root / "outbox").mkdir(parents=True, exist_ok=True)
        outbox = Path(tempfile.mkdtemp(prefix="doctor-", dir=str(report_root / "outbox")))
        shutil.rmtree(outbox)
        findings.append(print_status("report outbox creation", True, str(report_root / "outbox"), emit=args.format == "text"))
    except Exception as exc:
        findings.append(print_status("report outbox creation", False, str(exc), emit=args.format == "text"))
    ok, detail = auto_issue_reporting_probe(asset_root, agent_crew_home, project_root)
    findings.append(print_status("automatic issue reporting smoke", ok, detail, emit=args.format == "text"))
    ok, detail = auto_issue_reporting_blocker_probe(asset_root, agent_crew_home, project_root)
    findings.append(print_status("automatic issue blocker smoke", ok, detail, emit=args.format == "text"))
    stale = stale_state_summary(asset_root, state_dir)
    stale_detail = stale["detail"]
    if stale.get("recommendation"):
        stale_detail = f"{stale_detail}; {stale['recommendation']}"
    findings.append(print_status("stale state markers", stale["status"] == "pass", stale_detail, emit=args.format == "text"))

    stale_bridge_secs = int(os.environ.get("AGENT_CREW_STALE_HOST_BRIDGE_SECONDS") or 3600)
    ok, detail, count = host_bridge_blocker_probe(state_dir, stale_bridge_secs)
    bridge_detail = detail
    if not ok and count:
        bridge_detail = (
            f"{detail}; run crew cleanup-host-bridge --status completed --note \""
            f"host_bridge_not_invoked cleanup for {count} tasks\""
        )
    findings.append(print_status("stale host-bridge blockers", ok, bridge_detail, emit=args.format == "text"))
    cap_schema = agent_crew_home / "schemas" / "capabilities.schema.json"
    cap_file = state_dir / "capabilities.json"
    findings.append(print_status("capability file consistency", cap_schema.is_file() and cap_file.exists(), str(cap_file), emit=args.format == "text"))
    mnemos = mnemos_status()
    findings.append(print_status(
        "mnemos compatibility",
        mnemos["status"] in {"supported", "legacy", "missing"},
        mnemos["detail"],
        emit=args.format == "text",
    ))
    return findings


def doctor_host(args: argparse.Namespace) -> list[dict[str, Any]]:
    cfg = effective_config(args)
    cfg["command_check"] = host_bridge_command_probe(
        Path(args.asset_root),
        agent_crew_home=Path(args.agent_crew_home).expanduser(),
        project_root=Path(args.project_root).resolve(),
    )
    findings = [
        print_status("active adapter visible", bool(cfg["active_adapter"]), str(cfg["active_adapter"]), emit=args.format == "text"),
        print_status("install drift status", cfg["install_drift"]["status"] != "warn", cfg["install_drift"]["detail"], emit=args.format == "text"),
    ]
    for report in cfg["capability_reports"]:
        severity = str(report.get("severity") or ("pass" if report["status"] == "runtime-enforced" else "warn"))
        findings.append(print_finding(
            f"capability {report['name']} {report['status']}",
            severity,
            report["detail"],
            emit=args.format == "text",
        ))
    findings.append(
        print_status(
            "host bridge command readiness",
            cfg["command_check"][0],
            cfg["command_check"][1],
            emit=args.format == "text",
        )
    )
    claude_ok, claude_detail = claude_performance_probe(Path(args.asset_root))
    findings.append(print_status("claude performance budgets", claude_ok, claude_detail, emit=args.format == "text"))
    codex_invocation = adapter_doc_path(
        Path(args.asset_root),
        Path(args.agent_crew_home).expanduser(),
        "codex",
        "invocation.md",
    )
    text = codex_invocation.read_text(encoding="utf-8", errors="replace") if codex_invocation.is_file() else ""
    findings.append(print_status("slash command vocabulary documented", "slash command" in text and "crew:<intent>" in text, str(codex_invocation), emit=args.format == "text"))
    return findings


def cmd_doctor(args: argparse.Namespace) -> int:
    all_findings: list[dict[str, Any]] = []
    modes = ["static", "runtime", "host"] if args.mode == "all" else [args.mode]
    for mode in modes:
        if args.format == "text":
            print(f"== {mode} ==")
        if mode == "static":
            all_findings.extend(doctor_static(args))
        elif mode == "runtime":
            all_findings.extend(doctor_runtime(args))
        elif mode == "host":
            all_findings.extend(doctor_host(args))
    if args.format == "json":
        print(json.dumps({"findings": all_findings}, ensure_ascii=False, indent=2))
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    cfg = effective_config(args)
    if args.subcommand == "dump":
        if args.format == "json":
            print(json.dumps(cfg, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"active_adapter: {cfg['active_adapter']}")
            print(f"state_dir: {cfg['state_dir']}")
            print(f"memory_backend: {cfg['memory_backend']}")
            print(f"mnemos.status: {cfg['mnemos']['status']} ({cfg['mnemos']['detail']})")
            print(f"install_drift: {cfg['install_drift']['status']} ({cfg['install_drift']['detail']})")
            for key, value in cfg["capability_flags"].items():
                report = next(item for item in cfg["capability_reports"] if item["name"] == key)
                print(f"capability.{key}: {str(value).lower()} ({report['status']}; {report['detail']})")
            for group in ("budgets", "timeouts", "report_settings"):
                for key, value in cfg[group].items():
                    print(f"{group}.{key}: {value}")
        return 0
    args.mode = "runtime"
    return cmd_doctor(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="agent-crew diagnostics")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--asset-root", required=True)
    parser.add_argument("--agent-crew-home", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--mode", choices=("all", "static", "runtime", "host"), default="all")
    doctor.add_argument("--format", choices=("text", "json"), default="text")
    doctor.set_defaults(func=cmd_doctor)
    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="subcommand", required=True)
    config_doctor = config_sub.add_parser("doctor")
    config_doctor.add_argument("--format", choices=("text", "json"), default="text")
    config_doctor.add_argument("--mode", choices=("runtime",), default="runtime")
    config_doctor.set_defaults(func=cmd_config)
    dump = config_sub.add_parser("dump")
    dump.add_argument("--effective", action="store_true")
    dump.add_argument("--format", choices=("text", "json"), default="text")
    dump.set_defaults(func=cmd_config)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
