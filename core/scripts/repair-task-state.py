#!/usr/bin/env python3
"""Repair local task state after a manual host-handoff fallback."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def resolve_task_dir(state_dir: Path, task_id: str) -> Path:
    task_dir = state_dir / "tasks" / task_id
    if not task_dir.is_dir():
        raise SystemExit(f"repair-task-state: task not found: {task_id}")
    return task_dir


def backup_result(task_dir: Path) -> None:
    result = task_dir / "result.md"
    if not result.is_file():
        return

    archive = task_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    target = archive / "result-before-repair.md"
    if not target.exists():
        target.write_text(result.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")


def render_result(task: str, task_id: str, status: str, note: str, blocker: str,
                  evidence_paths: list[str], memory_ids: list[str],
                  memory_context_reused: bool) -> str:
    lines = [
        f"# {task or task_id}",
        "",
        f"STATUS: {status}",
        f"TASK_ID: {task_id}",
        "MEASUREMENTS: repaired manual handoff state, 1 repair event recorded",
    ]
    if status == "blocked":
        lines.append(f"BLOCKER: {blocker}")
    lines.append(f"EVIDENCE: context/manual-fallback-repair.json")
    for path in evidence_paths:
        lines.append(f"EVIDENCE: {path}")
    lines.append("UNCERTAINTY: Manual repair records the current-session outcome; original host bridge execution did not run automatically.")
    if note:
        lines.append(f"NOTE: {note}")
    if memory_ids:
        lines.append("MEMORY_IDS: " + ", ".join(memory_ids))
        lines.append(f"MEMORY_CONTEXT_REUSED: {'yes' if memory_context_reused else 'no'}")
    return "\n".join(lines).rstrip() + "\n"


def repair(args: argparse.Namespace) -> dict:
    state_dir = Path(args.state_dir).expanduser().resolve()
    task_dir = resolve_task_dir(state_dir, args.task_id)
    register_path = task_dir / "register.json"
    pipeline_path = task_dir / "pipeline.json"
    now = utc_now_z()

    register = load_json(register_path)
    pipeline = load_json(pipeline_path)
    previous = {
        "status": register.get("current_phase"),
        "blocked_by": register.get("blocked_by", []),
    }

    status = args.status
    blocker = args.blocker or ("manual_fallback_blocked" if status == "blocked" else "")
    blocked_by = [blocker] if status == "blocked" and blocker else []

    register.update({
        "current_phase": status,
        "blocked_by": blocked_by,
        "host_bridge_status": "manual_fallback_completed" if status == "completed" else "manual_fallback_blocked",
        "manual_fallback_repaired_at": now,
        "manual_fallback_repair_path": str(task_dir / "context" / "manual-fallback-repair.json"),
    })

    stages = pipeline.get("stages") or ["supervisor"]
    pipeline.update({
        "completed_stages": len(stages) if status == "completed" else int(pipeline.get("completed_stages") or 0),
        "stage_agent_status": {
            "1": {"supervisor": status}
        },
    })

    repair_record = {
        "schema_version": 1,
        "task_id": args.task_id,
        "status": status,
        "blocker": blocker,
        "note": args.note,
        "evidence_paths": args.evidence,
        "memory_ids": args.memory_id,
        "memory_context_reused": args.reused_memory_context,
        "previous": previous,
        "repaired_at": now,
    }

    backup_result(task_dir)
    write_json(register_path, register)
    write_json(pipeline_path, pipeline)
    write_json(task_dir / "context" / "manual-fallback-repair.json", repair_record)
    (task_dir / "result.md").write_text(
        render_result(
            register.get("task", ""),
            args.task_id,
            status,
            args.note,
            blocker,
            args.evidence,
            args.memory_id,
            args.reused_memory_context,
        ),
        encoding="utf-8",
    )
    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now} | REPAIR | manual fallback marked {status}\n")
        handle.write(f"{now} | STATUS | {status}\n")
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', args.task_id)}.{args.task_id}.0.0",
            "task_id": args.task_id,
            "session_id": register.get("session_id", ""),
            "event": "REPAIR",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": status,
            "detail": args.note or "manual fallback repaired",
            "files": ["context/manual-fallback-repair.json", "result.md"],
        },
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', args.task_id)}.{args.task_id}.0.0",
            "task_id": args.task_id,
            "session_id": register.get("session_id", ""),
            "event": "COMPLETED" if status == "completed" else "BLOCKED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": status,
            "detail": status if status == "completed" else blocker,
            "files": [],
        },
    )
    return repair_record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--status", choices=["completed", "blocked"], default="completed")
    parser.add_argument("--note", default="")
    parser.add_argument("--blocker", default="")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--memory-id", action="append", default=[])
    parser.add_argument("--reused-memory-context", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("task_id")
    args = parser.parse_args()

    record = repair(args)
    if args.format == "json":
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(f"STATUS: {record['status']}")
        print(f"TASK_ID: {record['task_id']}")
        print("REPAIR: context/manual-fallback-repair.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
