#!/usr/bin/env python3
"""Run the phase-two validation pass and emit findings, gaps, and actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def artifact_base(command_id: str, attempt: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", command_id).strip("-") or "command"
    safe_attempt = re.sub(r"[^A-Za-z0-9_.-]+", "-", attempt).strip("-") or "run"
    return f"{safe_id}-{safe_attempt}"


def extract_failure_markers(*streams: str) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    current_section: str | None = None
    in_failed_list = False
    pattern = re.compile(r"(?:^|\b)(not ok|FAIL|failed=[1-9][0-9]*|Overall:\s+FAIL)(?:\b|$)", re.IGNORECASE)
    section_pattern = re.compile(r"^---\s+(.+?)\s+---$")

    line_number = 0
    for stream in streams:
        for line in stream.splitlines():
            line_number += 1
            section_match = section_pattern.match(line.strip())
            if section_match:
                current_section = section_match.group(1)
                in_failed_list = False

            stripped = line.strip()
            if stripped == "failed:":
                in_failed_list = True
                continue
            if in_failed_list and not stripped:
                in_failed_list = False

            if pattern.search(line) or (in_failed_list and stripped.startswith("- ")):
                marker: dict[str, Any] = {
                    "line": line_number,
                    "text": line[:500],
                }
                if current_section:
                    marker["section"] = current_section
                markers.append(marker)

    return markers


def write_artifacts(
    *,
    artifact_dir: Path | None,
    command_id: str,
    attempt: str,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stdout_sha256": sha256_text(stdout),
        "stderr_sha256": sha256_text(stderr),
    }
    if artifact_dir is None:
        return payload

    artifact_dir.mkdir(parents=True, exist_ok=True)
    base = artifact_base(command_id, attempt)
    stdout_path = artifact_dir / f"{base}.stdout.log"
    stderr_path = artifact_dir / f"{base}.stderr.log"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    payload.update({
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    })
    return payload


def expand_command(command: list[str], root: Path) -> list[str]:
    replacements = {
        "{python}": sys.executable,
        "{repo}": str(root),
        "{crew_bin}": str(root / "core" / "bin" / "crew"),
        "{memory_bin}": str(root / "core" / "bin" / "memory"),
    }
    return [replacements.get(part, part) for part in command]


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    artifact_dir: Path | None = None,
    command_id: str = "command",
    attempt: str = "initial",
) -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=str(cwd), env=env, text=True, capture_output=True)
    elapsed_ms = (time.perf_counter() - started) * 1000
    artifacts = write_artifacts(
        artifact_dir=artifact_dir,
        command_id=command_id,
        attempt=attempt,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )

    return {
        "command": command,
        "returncode": proc.returncode,
        "elapsed_ms": round(elapsed_ms, 3),
        "stdout_tail": tail(proc.stdout),
        "stderr_tail": tail(proc.stderr),
        "failure_markers": extract_failure_markers(proc.stdout, proc.stderr),
        **artifacts,
    }


def iter_commands(framework: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for level in framework.get("levels", []):
        for command in level.get("commands", []):
            items.append((str(level.get("id", "unknown")), command))
    return items


def selected(level: str, command_id: str, levels: set[str], commands: set[str]) -> bool:
    if levels and level not in levels:
        return False
    return not commands or command_id in commands


def criterion_summary(
    framework: dict[str, Any],
    command_results: list[dict[str, Any]],
    *,
    plan_only: bool,
) -> list[dict[str, Any]]:
    definitions = {criterion["id"]: criterion for criterion in framework.get("criteria", [])}
    mapped: dict[str, list[dict[str, Any]]] = {criterion_id: [] for criterion_id in definitions}
    for result in command_results:
        for criterion in result.get("criteria", []):
            mapped.setdefault(str(criterion), []).append(result)

    summaries = []
    for criterion_id, definition in definitions.items():
        results = mapped.get(criterion_id, [])
        required = [item for item in results if not item.get("optional")]
        optional = [item for item in results if item.get("optional")]
        failed_required = [
            item["id"] for item in required if item.get("passed") is False
        ]
        failed_optional = [
            item["id"] for item in optional if item.get("passed") is False
        ]
        passed_required = [item for item in required if item.get("passed") is True]

        if plan_only:
            status = "planned" if results else "unmeasured"
        elif failed_required:
            status = "needs_attention"
        elif required and len(passed_required) == len(required):
            status = "passed" if not failed_optional else "provisional"
        elif optional and failed_optional:
            status = "provisional"
        elif results:
            status = "passed"
        else:
            status = "unmeasured"

        summaries.append({
            "id": criterion_id,
            "status": status,
            "question": definition.get("question"),
            "required_commands": [item["id"] for item in required],
            "optional_commands": [item["id"] for item in optional],
            "failed_required_commands": failed_required,
            "failed_optional_commands": failed_optional,
            "phase_2_threshold": definition.get("phase_2_threshold"),
            "evidence": definition.get("evidence", []),
        })
    return summaries


def build_findings(
    framework: dict[str, Any],
    criteria: list[dict[str, Any]],
    *,
    plan_only: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    definitions = {criterion["id"]: criterion for criterion in framework.get("criteria", [])}
    findings: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    for summary in criteria:
        criterion_id = summary["id"]
        definition = definitions.get(criterion_id, {})
        status = summary["status"]

        if status == "passed":
            findings.append({
                "criterion_id": criterion_id,
                "severity": "info",
                "status": status,
                "summary": f"{criterion_id} validation met the phase-two threshold.",
            })
            continue

        if plan_only and status == "planned":
            findings.append({
                "criterion_id": criterion_id,
                "severity": "info",
                "status": status,
                "summary": f"{criterion_id} validation is defined for the next pass.",
            })
            continue

        severity = "high" if status == "needs_attention" else "medium"
        if status == "provisional":
            severity = "low"

        gap = {
            "criterion_id": criterion_id,
            "severity": severity,
            "status": status,
            "failed_required_commands": summary["failed_required_commands"],
            "failed_optional_commands": summary["failed_optional_commands"],
            "summary": gap_summary(criterion_id, status),
        }
        gaps.append(gap)
        findings.append(gap)

        action_text = action_for(definition, status)
        if action_text:
            actions.append({
                "criterion_id": criterion_id,
                "priority": severity,
                "action": action_text,
            })

    return findings, gaps, actions


def gap_summary(criterion_id: str, status: str) -> str:
    if status == "needs_attention":
        return f"{criterion_id} has required validation failures."
    if status == "provisional":
        return f"{criterion_id} has only optional or incomplete evidence gaps."
    if status == "unmeasured":
        return f"{criterion_id} is not covered by the selected phase-two commands."
    return f"{criterion_id} status is {status}."


def action_for(definition: dict[str, Any], status: str) -> str | None:
    if status == "needs_attention":
        return definition.get("follow_up_if_failed") or "Investigate required validation failures."
    if status == "provisional":
        return definition.get("follow_up_if_provisional") or definition.get("follow_up_if_failed")
    if status == "unmeasured":
        return definition.get("follow_up_if_unmeasured") or "Add a required command that measures this criterion."
    return None


def level_summary(framework: dict[str, Any], command_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for level in framework.get("levels", []):
        level_id = str(level.get("id", "unknown"))
        results = [item for item in command_results if item["level"] == level_id]
        required = [item for item in results if not item.get("optional")]
        failed_required = [
            item["id"] for item in required if item.get("passed") is False
        ]
        if not results:
            status = "unselected"
        elif any(item.get("skipped") for item in results):
            status = "planned"
        elif failed_required:
            status = "needs_attention"
        else:
            status = "passed"
        summaries.append({
            "id": level_id,
            "status": status,
            "description": level.get("description"),
            "commands": [item["id"] for item in results],
            "failed_required_commands": failed_required,
        })
    return summaries


def build_report(
    framework: dict[str, Any],
    *,
    root: Path,
    levels: set[str],
    commands: set[str],
    plan_only: bool,
    artifact_dir: Path | None = None,
    rerun_failed_once: bool = False,
) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("PROJECT_ROOT", str(root))
    command_results = []

    for level, command in iter_commands(framework):
        command_id = str(command.get("id", "unnamed"))
        if not selected(level, command_id, levels, commands):
            continue

        allowed = {int(value) for value in command.get("allowed_returncodes", [0])}
        expanded = expand_command([str(part) for part in command.get("command", [])], root)
        result: dict[str, Any] = {
            "id": command_id,
            "label": command.get("label", command_id),
            "level": level,
            "criteria": command.get("criteria", []),
            "optional": bool(command.get("optional", False)),
            "allowed_returncodes": sorted(allowed),
            "command": expanded,
        }

        if plan_only:
            result.update({"passed": None, "skipped": True, "skip_reason": "plan_only"})
        else:
            observed = run_command(
                expanded,
                cwd=root,
                env=env,
                artifact_dir=artifact_dir,
                command_id=command_id,
                attempt="initial",
            )
            result.update(observed)
            result["passed"] = observed["returncode"] in allowed
            if rerun_failed_once and not result["passed"]:
                rerun = run_command(
                    expanded,
                    cwd=root,
                    env=env,
                    artifact_dir=artifact_dir,
                    command_id=command_id,
                    attempt="rerun",
                )
                rerun_passed = rerun["returncode"] in allowed
                result.update({
                    "initial_returncode": observed["returncode"],
                    "initial_failure_markers": observed["failure_markers"],
                    "rerun_returncode": rerun["returncode"],
                    "rerun_elapsed_ms": rerun["elapsed_ms"],
                    "rerun_stdout_tail": rerun["stdout_tail"],
                    "rerun_stderr_tail": rerun["stderr_tail"],
                    "rerun_failure_markers": rerun["failure_markers"],
                    "flaky": rerun_passed,
                    "passed": rerun_passed,
                })
                if "stdout_path" in rerun:
                    result["rerun_stdout_path"] = rerun["stdout_path"]
                if "stderr_path" in rerun:
                    result["rerun_stderr_path"] = rerun["stderr_path"]
                if "stdout_sha256" in rerun:
                    result["rerun_stdout_sha256"] = rerun["stdout_sha256"]
                if "stderr_sha256" in rerun:
                    result["rerun_stderr_sha256"] = rerun["stderr_sha256"]
            result["skipped"] = False
        command_results.append(result)

    criteria = criterion_summary(framework, command_results, plan_only=plan_only)
    findings, gaps, actions = build_findings(framework, criteria, plan_only=plan_only)
    required_results = [
        item for item in command_results
        if not item.get("optional") and not item.get("skipped")
    ]
    passed = None if plan_only else all(item["passed"] for item in required_results)

    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "framework": {
            "name": framework.get("name"),
            "objective": framework.get("objective"),
            "path": str(root / "core" / "evaluations" / "phase-2-validation.json"),
        },
        "project_root": str(root),
        "passed": passed,
        "plan_only": plan_only,
        "levels": level_summary(framework, command_results),
        "commands": command_results,
        "criteria": criteria,
        "findings": findings,
        "gaps": gaps,
        "recommended_follow_up_actions": actions,
    }


def emit_text(report: dict[str, Any]) -> None:
    status = "PLAN" if report["plan_only"] else ("PASS" if report["passed"] else "FAIL")
    print(f"{status}: phase-two validation")
    for level in report["levels"]:
        if level["status"] == "unselected":
            continue
        print(f"- {level['status'].upper()} level/{level['id']}: {', '.join(level['commands'])}")

    print("criteria:")
    for criterion in report["criteria"]:
        print(f"- {criterion['id']}: {criterion['status']}")

    if report["gaps"]:
        print("gaps:")
        for gap in report["gaps"]:
            print(f"- {gap['severity']} {gap['criterion_id']}: {gap['summary']}")

    if report["recommended_follow_up_actions"]:
        print("follow-up actions:")
        for action in report["recommended_follow_up_actions"]:
            print(f"- {action['priority']} {action['criterion_id']}: {action['action']}")


def main() -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(root))
    parser.add_argument("--framework", default=str(root / "core" / "evaluations" / "phase-2-validation.json"))
    parser.add_argument("--level", action="append", default=[], help="Run only this level; may be repeated.")
    parser.add_argument("--command-id", action="append", default=[], help="Run only this command id; may be repeated.")
    parser.add_argument("--output", help="Write the JSON report to this path.")
    parser.add_argument("--artifact-dir", help="Write per-command stdout/stderr artifacts to this directory.")
    parser.add_argument("--rerun-failed-once", action="store_true", help="Rerun failing commands once; if the rerun passes, mark flaky=true and allow the gate to pass.")
    parser.add_argument("--plan-only", action="store_true", help="Show selected commands without running them.")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    framework = load_json(Path(args.framework).expanduser().resolve())
    artifact_dir = Path(args.artifact_dir).expanduser().resolve() if args.artifact_dir else None
    if artifact_dir is None and args.output and not args.plan_only:
        output = Path(args.output).expanduser()
        artifact_dir = output.with_name(f"{output.stem}-artifacts").resolve()
    report = build_report(
        framework,
        root=project_root,
        levels=set(args.level),
        commands=set(args.command_id),
        plan_only=args.plan_only,
        artifact_dir=artifact_dir,
        rerun_failed_once=args.rerun_failed_once,
    )

    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.format == "json":
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        emit_text(report)

    if args.plan_only:
        return 0
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
