#!/usr/bin/env python3
"""Dry-run-first cleanup and archival plan for stale task state."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def age_seconds(path: Path) -> int:
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return 0
    return max(0, int((datetime.now(timezone.utc) - mtime).total_seconds()))


def discover(state_dir: Path, min_age_seconds: int, handoff_ready_min_age_seconds: int | None = None) -> list[dict]:
    tasks_root = state_dir / "tasks"
    if not tasks_root.is_dir():
        return []
    handoff_threshold = max(min_age_seconds, 3600 if handoff_ready_min_age_seconds is None else handoff_ready_min_age_seconds)

    items: list[dict] = []
    for path in sorted(tasks_root.glob("active*")):
        if path.is_file() and age_seconds(path) >= min_age_seconds:
            items.append({
                "kind": "stale_active_marker",
                "path": str(path),
                "age_seconds": age_seconds(path),
                "planned_action": "archive_marker",
                "destructive": False,
            })

    for pending in sorted(tasks_root.glob("*/supervisor-pending.txt")):
        if age_seconds(pending) >= min_age_seconds:
            items.append({
                "kind": "stale_supervisor_pending",
                "task_id": pending.parent.name,
                "path": str(pending),
                "age_seconds": age_seconds(pending),
                "planned_action": "archive_sentinel",
                "destructive": False,
            })

    for task_dir in sorted(path for path in tasks_root.iterdir() if path.is_dir()):
        register = load_json(task_dir / "register.json")
        result = (task_dir / "result.md").read_text(encoding="utf-8", errors="replace") if (task_dir / "result.md").is_file() else ""
        repaired = bool(register.get("manual_fallback_repaired_at") or "REPAIR" in result)
        blocked = register.get("current_phase") == "blocked" or "STATUS: blocked" in result
        handoff_ready = (
            register.get("current_phase") == "handoff_ready"
            or "STATUS: handoff_ready" in result
        )
        bridge_status = str(register.get("host_bridge_status") or "")
        if handoff_ready and bridge_status in {"internal_handoff_ready", "not_invoked", ""} and age_seconds(task_dir) >= handoff_threshold:
            items.append({
                "kind": "stale_handoff_ready_task",
                "task_id": task_dir.name,
                "path": str(task_dir),
                "age_seconds": age_seconds(task_dir),
                "planned_action": "operator_review_then_repair_or_cancel",
                "commands": [
                    f"crew resume {task_dir.name}",
                    f"crew repair --status completed --note \"<summary>\" {task_dir.name}",
                    f"crew cancel --note \"superseded stale handoff\" {task_dir.name}",
                ],
                "destructive": False,
            })
        if blocked or repaired:
            items.append({
                "kind": "task_retention_policy",
                "task_id": task_dir.name,
                "path": str(task_dir),
                "state": "repaired" if repaired else "blocked",
                "planned_action": "retain_task_artifacts_and_archive_cleanup_metadata",
                "retained": ["result.md", "register.json", "pipeline.json", "progress.log", "context/"],
                "removed": [],
                "destructive": False,
            })
    return items


def summarize(items: list[dict]) -> dict:
    counts = {
        "stale_active_markers": 0,
        "stale_supervisor_pending_sentinels": 0,
        "stale_handoff_ready_tasks": 0,
        "retained_task_directories": 0,
        "planned_archival_targets": 0,
        "operator_review_targets": 0,
        "destructive_deletions": 0,
    }
    for item in items:
        kind = item.get("kind")
        if kind == "stale_active_marker":
            counts["stale_active_markers"] += 1
            counts["planned_archival_targets"] += 1
        elif kind == "stale_supervisor_pending":
            counts["stale_supervisor_pending_sentinels"] += 1
            counts["planned_archival_targets"] += 1
        elif kind == "stale_handoff_ready_task":
            counts["stale_handoff_ready_tasks"] += 1
            counts["operator_review_targets"] += 1
        elif kind == "task_retention_policy":
            counts["retained_task_directories"] += 1
        if item.get("destructive"):
            counts["destructive_deletions"] += 1
    return counts


def archive_item(state_dir: Path, item: dict) -> str:
    source = Path(item["path"])
    archive_root = state_dir / "archive" / "task-state-cleanup"
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / source.name
    if source.is_file():
        suffix = 1
        while target.exists():
            target = archive_root / f"{source.name}.{suffix}"
            suffix += 1
        shutil.move(str(source), str(target))
    return str(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--min-age-seconds", type=int, default=0)
    parser.add_argument("--handoff-ready-min-age-seconds", type=int, default=None)
    parser.add_argument("--apply", action="store_true", help="Archive stale markers/sentinels. Dry-run is the default.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state_dir = Path(args.state_dir).expanduser().resolve()
    handoff_age = None if args.handoff_ready_min_age_seconds is None else max(args.handoff_ready_min_age_seconds, 0)
    items = discover(state_dir, max(args.min_age_seconds, 0), handoff_age)
    archived = []
    if args.apply:
        for item in items:
            if item["kind"] in {"stale_active_marker", "stale_supervisor_pending"}:
                item["archived_to"] = archive_item(state_dir, item)
                archived.append(item["archived_to"])

    payload = {
        "schema_version": 1,
        "mode": "apply" if args.apply else "dry-run",
        "state_dir": str(state_dir),
        "summary": summarize(items),
        "planned_changes": items,
        "archived": archived,
        "policy": {
            "archival": "stale active markers and supervisor-pending sentinels are moved under archive/task-state-cleanup on apply",
            "handoff_ready": "handoff-ready task directories require operator review; use crew resume, crew repair, or crew cancel",
            "retention": "blocked and repaired task directories are retained with result, register, pipeline, progress, and context evidence",
            "destructive_deletion": "not performed by this command",
        },
    }

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"mode: {payload['mode']}")
        print(f"planned_changes: {len(items)}")
        summary = payload["summary"]
        print(
            "stale_counts: "
            f"active_markers={summary['stale_active_markers']} "
            f"supervisor_pending={summary['stale_supervisor_pending_sentinels']} "
            f"handoff_ready={summary['stale_handoff_ready_tasks']} "
            f"archival_targets={summary['planned_archival_targets']} "
            f"review_targets={summary['operator_review_targets']} "
            f"retained_tasks={summary['retained_task_directories']}"
        )
        print("policy: archival moves markers; handoff-ready tasks require operator review; blocked/repaired task evidence is retained; destructive deletion is not performed")
        for item in items:
            label = item.get("task_id") or Path(item["path"]).name
            print(f"- {item['kind']} {label}: {item['planned_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
