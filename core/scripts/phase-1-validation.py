#!/usr/bin/env python3
"""Run the phase-one validation framework and capture evidence."""

from __future__ import annotations

import argparse
import json
import os
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


def expand_command(command: list[str], root: Path) -> list[str]:
    replacements = {
        "{python}": sys.executable,
        "{repo}": str(root),
        "{crew_bin}": str(root / "core" / "bin" / "crew"),
        "{memory_bin}": str(root / "core" / "bin" / "memory"),
    }
    return [replacements.get(part, part) for part in command]


def run_command(command: list[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=str(cwd), env=env, text=True, capture_output=True)
    elapsed_ms = (time.perf_counter() - started) * 1000

    return {
        "command": command,
        "returncode": proc.returncode,
        "elapsed_ms": round(elapsed_ms, 3),
        "stdout_tail": tail(proc.stdout),
        "stderr_tail": tail(proc.stderr),
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


def criterion_summary(framework: dict[str, Any], command_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {criterion["id"]: criterion for criterion in framework.get("criteria", [])}
    mapped: dict[str, list[dict[str, Any]]] = {criterion_id: [] for criterion_id in by_id}
    for result in command_results:
        for criterion in result.get("criteria", []):
            mapped.setdefault(str(criterion), []).append(result)

    summaries = []
    for criterion_id, definition in by_id.items():
        results = mapped.get(criterion_id, [])
        required = [item for item in results if not item.get("optional")]
        optional = [item for item in results if item.get("optional")]
        failed_required = [item["id"] for item in required if not item["passed"]]
        failed_optional = [item["id"] for item in optional if not item["passed"]]
        passed_required = [item for item in required if item["passed"]]

        if failed_required:
            status = "needs_attention"
        elif required and len(passed_required) == len(required):
            status = "passed"
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
            "phase_1_threshold": definition.get("phase_1_threshold"),
        })
    return summaries


def build_report(
    framework: dict[str, Any],
    *,
    root: Path,
    levels: set[str],
    commands: set[str],
    plan_only: bool,
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
            observed = run_command(expanded, cwd=root, env=env)
            result.update(observed)
            result["passed"] = observed["returncode"] in allowed
            result["skipped"] = False
        command_results.append(result)

    criteria = [] if plan_only else criterion_summary(framework, command_results)
    required_results = [
        item for item in command_results
        if not item.get("optional") and not item.get("skipped")
    ]
    passed = None if plan_only else all(item["passed"] for item in required_results)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "framework": {
            "name": framework.get("name"),
            "objective": framework.get("objective"),
            "path": str(root / "core" / "evaluations" / "phase-1-validation.json"),
        },
        "project_root": str(root),
        "passed": passed,
        "plan_only": plan_only,
        "commands": command_results,
        "criteria": criteria,
    }


def emit_text(report: dict[str, Any]) -> None:
    status = "PLAN" if report["plan_only"] else ("PASS" if report["passed"] else "FAIL")
    print(f"{status}: phase-one validation")
    for item in report["commands"]:
        if item.get("skipped"):
            print(f"- SKIP {item['level']}/{item['id']}: {item['skip_reason']}")
            continue
        item_status = "PASS" if item["passed"] else "FAIL"
        print(f"- {item_status} {item['level']}/{item['id']}: {item['elapsed_ms']}ms rc={item['returncode']}")

    if report.get("criteria"):
        print("criteria:")
        for criterion in report["criteria"]:
            print(f"- {criterion['id']}: {criterion['status']}")


def main() -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(root))
    parser.add_argument("--framework", default=str(root / "core" / "evaluations" / "phase-1-validation.json"))
    parser.add_argument("--level", action="append", default=[], help="Run only this level; may be repeated.")
    parser.add_argument("--command-id", action="append", default=[], help="Run only this command id; may be repeated.")
    parser.add_argument("--output", help="Write the JSON report to this path.")
    parser.add_argument("--plan-only", action="store_true", help="Show selected commands without running them.")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    framework = load_json(Path(args.framework).expanduser().resolve())
    report = build_report(
        framework,
        root=project_root,
        levels=set(args.level),
        commands=set(args.command_id),
        plan_only=args.plan_only,
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
