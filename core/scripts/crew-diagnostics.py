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


def run_cmd(args: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False, timeout=15)
    except Exception as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def source_root(asset_root: Path) -> Path:
    return asset_root.parent if asset_root.name == "core" and (asset_root.parent / "adapters").is_dir() else asset_root


def install_drift(asset_root: Path, project_root: Path, agent_crew_home: Path) -> dict[str, Any]:
    script = asset_root / "scripts" / "verify-install-drift.py"
    root = source_root(asset_root)
    if not script.is_file():
        return {"status": "unknown", "detail": "verify-install-drift.py not found"}
    _ = project_root
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
            detail = "active adapter advertises this runtime capability"
        elif active_adapter == "codex" and name in {"hook_system", "interactive_question", "task_tools", "agent_background", "monitor_tool", "cost_tracking"}:
            status = "policy-only"
            detail = "Codex uses prompt/file fallbacks; this capability is not runtime-enforced"
        else:
            status = "unavailable"
            detail = "active adapter does not advertise this runtime capability"
        capability_reports.append({
            "name": name,
            "enabled": enabled,
            "status": status,
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
    return {
        "status": "pass",
        "summary": summary,
        "detail": (
            f"active_markers={summary.get('stale_active_markers', 0)} "
            f"supervisor_pending={summary.get('stale_supervisor_pending_sentinels', 0)} "
            f"archival_targets={summary.get('planned_archival_targets', 0)}"
        ),
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
    stale = stale_state_summary(asset_root, state_dir)
    findings.append(print_status("stale state markers", stale["status"] == "pass", stale["detail"], emit=args.format == "text"))
    cap_schema = agent_crew_home / "schemas" / "capabilities.schema.json"
    cap_file = state_dir / "capabilities.json"
    findings.append(print_status("capability file consistency", cap_schema.is_file() and cap_file.exists(), str(cap_file), emit=args.format == "text"))
    return findings


def doctor_host(args: argparse.Namespace) -> list[dict[str, Any]]:
    cfg = effective_config(args)
    findings = [
        print_status("active adapter visible", bool(cfg["active_adapter"]), str(cfg["active_adapter"]), emit=args.format == "text"),
        print_status("install drift status", cfg["install_drift"]["status"] != "warn", cfg["install_drift"]["detail"], emit=args.format == "text"),
    ]
    for report in cfg["capability_reports"]:
        ok = report["status"] == "runtime-enforced"
        findings.append(print_status(
            f"capability {report['name']} {report['status']}",
            ok,
            report["detail"],
            emit=args.format == "text",
        ))
    codex_invocation = Path(args.asset_root).parent / "adapters" / "codex" / "invocation.md"
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
