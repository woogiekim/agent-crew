#!/usr/bin/env python3
"""Build readiness workload evidence from local agent-crew task state.

Inputs:
  --state-dir PATH      project state directory with tasks/
  --recent N           limit to most recent task directories
  --output PATH        optional JSON output path

Outputs:
  JSON or text evidence with task counts, bridge completions, manual repairs,
  human interventions, retries, and task success totals.

Exit codes:
  0 - evidence generated
  2 - invalid state directory or arguments
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_RE = re.compile(r"(?im)^STATUS\s*:\s*([a-z_]+)\b")


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def result_status(result_text: str, register: dict[str, Any]) -> str:
    match = STATUS_RE.search(result_text)
    if match:
        return match.group(1).lower()
    return str(register.get("current_phase") or "unknown").lower()


def progress_retry_count(task_dir: Path) -> int:
    buffer = task_dir / "progress.buffer.jsonl"
    attempts: set[tuple[int, int]] = set()
    explicit_retries = 0
    if buffer.is_file():
        for line in buffer.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            event = str(row.get("event") or "").lower()
            detail = str(row.get("detail") or "").lower()
            status = str(row.get("status") or "").lower()
            if "retry" in event or "retry" in detail or status == "retry":
                explicit_retries += 1
            try:
                stage = int(row.get("stage") or 0)
                attempt = int(row.get("attempt") or 0)
            except Exception:
                continue
            if attempt > 1:
                attempts.add((stage, attempt))
    return max(explicit_retries, len(attempts))


def task_dirs(state_dir: Path, recent: int) -> list[Path]:
    tasks_root = state_dir / "tasks"
    if not tasks_root.is_dir():
        return []
    dirs = [path for path in tasks_root.iterdir() if path.is_dir()]
    dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return dirs[:recent] if recent > 0 else dirs


def task_record(task_dir: Path) -> dict[str, Any]:
    register = read_json(task_dir / "register.json")
    result = read_text(task_dir / "result.md")
    status = result_status(result, register)
    host_bridge_status = str(register.get("host_bridge_status") or "").lower()
    manual_repaired = bool(
        register.get("manual_fallback_repaired_at")
        or host_bridge_status.startswith("manual_fallback")
        or (task_dir / "context" / "manual-fallback-repair.json").is_file()
    )
    host_bridge_completed = host_bridge_status == "auto_completed"
    retry_count = progress_retry_count(task_dir)
    success = status == "completed"
    handoff_ready = status == "handoff_ready" or str(register.get("current_phase") or "").lower() == "handoff_ready"

    return {
        "task_id": task_dir.name,
        "task_dir": str(task_dir),
        "status": status,
        "current_phase": str(register.get("current_phase") or status),
        "host_bridge_status": host_bridge_status or "unknown",
        "task_success": success,
        "host_bridge_completed": host_bridge_completed,
        "manual_repair_required": manual_repaired,
        "human_intervention_required": manual_repaired,
        "retries": retry_count,
        "handoff_ready": handoff_ready,
    }


def build_evidence(state_dir: Path, *, recent: int = 0, adapter: str = "local") -> dict[str, Any]:
    if not state_dir.is_dir():
        raise ValueError(f"state directory not found: {state_dir}")

    tasks = [task_record(path) for path in task_dirs(state_dir, recent)]
    total = len(tasks)
    successes = sum(1 for task in tasks if task["task_success"])
    bridge_completed = sum(1 for task in tasks if task["host_bridge_completed"])
    manual_repairs = sum(1 for task in tasks if task["manual_repair_required"])
    retries = sum(int(task["retries"]) for task in tasks)
    handoff_ready = sum(1 for task in tasks if task["handoff_ready"])

    return {
        "schema_version": 1,
        "adapter": adapter,
        "source": "agent-crew-local-state",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "state_dir": str(state_dir),
        "tasks": total,
        "successes": successes,
        "host_bridge_completed": bridge_completed,
        "manual_repairs": manual_repairs,
        "human_interventions": manual_repairs,
        "retries": retries,
        "handoff_ready_tasks": handoff_ready,
        "task_records": tasks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--recent", type=int, default=0, help="Most recent task directories to include; 0 means all.")
    parser.add_argument("--adapter", default="local")
    parser.add_argument("--output", help="Write JSON evidence to this path.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    try:
        evidence = build_evidence(Path(args.state_dir).expanduser().resolve(), recent=max(args.recent, 0), adapter=args.adapter)
    except ValueError as exc:
        print(f"hosted-workload-evidence: {exc}", file=sys.stderr)
        return 2

    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    else:
        print("PASS: hosted workload evidence")
        print(
            f"tasks={evidence['tasks']} successes={evidence['successes']} "
            f"host_bridge_completed={evidence['host_bridge_completed']} "
            f"manual_repairs={evidence['manual_repairs']} retries={evidence['retries']} "
            f"handoff_ready={evidence['handoff_ready_tasks']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
