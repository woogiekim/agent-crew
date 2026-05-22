#!/usr/bin/env python3
"""Bulk repair stale host_bridge_not_invoked task blockers."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_iso(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def task_age_seconds(task_dir: Path, register: dict) -> int:
    started = None
    progress = task_dir / "progress.buffer.jsonl"
    if progress.is_file():
        for line in progress.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("event") == "STARTED":
                started = parse_iso(row.get("ts", ""))
                break
    if not started:
        started = datetime.fromtimestamp(task_dir.stat().st_mtime, tz=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - started).total_seconds()))


def has_host_bridge_blocker(task_dir: Path, register: dict) -> bool:
    if register.get("current_phase") == "completed":
        return False
    blockers = [str(value) for value in register.get("blocked_by", []) or []]
    if any(value == "host_bridge_not_invoked" or "host AI bridge" in value for value in blockers):
        return True
    result = task_dir / "result.md"
    if result.is_file():
        text = result.read_text(encoding="utf-8", errors="replace")
        return "host_bridge_not_invoked" in text or "host AI bridge has not completed this handoff" in text
    return False


def find_matches(state_dir: Path, min_age_seconds: int) -> list[tuple[Path, dict, int]]:
    tasks_root = state_dir / "tasks"
    if not tasks_root.is_dir():
        return []
    matches = []
    for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        register = load_json(task_dir / "register.json")
        if not register:
            continue
        age = task_age_seconds(task_dir, register)
        if age < min_age_seconds:
            continue
        if has_host_bridge_blocker(task_dir, register):
            matches.append((task_dir, register, age))
    return matches


def repair_task(script: Path, state_dir: Path, task_id: str, status: str, note: str) -> int:
    command = [
        sys.executable,
        str(script),
        "--state-dir",
        str(state_dir),
        "--status",
        status,
        "--note",
        note,
    ]
    if status == "blocked":
        command.extend(["--blocker", "manual_fallback_unresolved"])
    command.append(task_id)
    return subprocess.run(command, text=True, capture_output=True).returncode


def write_cleanup_evidence(task_dir: Path, register: dict, age: int, status: str, note: str) -> Path:
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    path = context_dir / "stale-host-bridge-cleanup.json"
    payload = {
        "schema_version": 1,
        "task_id": task_dir.name,
        "task": register.get("task", ""),
        "age_seconds": age,
        "cleanup_status": status,
        "note": note,
        "original_current_phase": register.get("current_phase", ""),
        "original_blocked_by": register.get("blocked_by", []) or [],
        "classified_blocker": "stale_host_bridge_not_invoked",
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--min-age-seconds", type=int, default=0)
    parser.add_argument("--status", choices=["completed", "blocked"], default="completed")
    parser.add_argument("--note", default="bulk cleanup of stale host_bridge_not_invoked task")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state_dir = Path(args.state_dir).expanduser().resolve()
    matches = find_matches(state_dir, args.min_age_seconds)
    repaired = []
    failed = []
    repair_script = Path(__file__).resolve().parent / "repair-task-state.py"

    if args.apply:
        for task_dir, register, age in matches:
            write_cleanup_evidence(task_dir, register, age, args.status, args.note)
            rc = repair_task(repair_script, state_dir, task_dir.name, args.status, args.note)
            if rc == 0:
                repaired.append(task_dir.name)
            else:
                failed.append(task_dir.name)

    payload = {
        "schema_version": 1,
        "matched": [
            {
                "task_id": task_dir.name,
                "age_seconds": age,
                "task": register.get("task", ""),
            }
            for task_dir, register, age in matches
        ],
        "apply": args.apply,
        "status": args.status,
        "repaired": repaired,
        "failed": failed,
        "passed": not failed,
    }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        action = "repaired" if args.apply else "matched"
        print(f"{action}: {len(repaired) if args.apply else len(matches)} host_bridge_not_invoked task(s)")
        for item in payload["matched"]:
            print(f"- {item['task_id']} age={item['age_seconds']}s")
        if failed:
            print("failed: " + ", ".join(failed))

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
