#!/usr/bin/env python3
"""Materialize durable learning events from task-local evolution reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "agent-crew.learning-event.v1"


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_repository(value: str) -> str:
    raw = value.strip()
    raw = re.sub(r"^git@", "", raw)
    raw = raw.replace(":", "/", 1) if raw.startswith("github.com:") else raw
    raw = re.sub(r"^https?://", "", raw)
    raw = re.sub(r"^ssh://", "", raw)
    raw = raw.removesuffix(".git")
    raw = raw.strip("/")
    return raw.lower()


def git_remote(project_root: str) -> str:
    if not project_root:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", project_root, "config", "--get", "remote.origin.url"],
            text=True,
            capture_output=True,
            timeout=2,
        )
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def repository_for(register: dict[str, Any]) -> str:
    explicit = str(register.get("repository") or "").strip()
    if explicit:
        return explicit

    remote = git_remote(str(register.get("project_root") or ""))
    if remote:
        return remote

    project_root = str(register.get("project_root") or "").strip()
    return Path(project_root).name if project_root else "unknown"


def relative_ref(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def proposal_keys(report: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for item in report.get("observed_patterns") or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "mistake_correction":
            pattern_key = str(item.get("pattern_key") or "").strip()
            if pattern_key:
                keys.append(f"mistake_correction:{pattern_key}")
            continue
        if item.get("kind") == "review_principle":
            principle_key = str(item.get("principle_key") or "").strip()
            if principle_key:
                keys.append(f"review_principle:{principle_key}")
            continue
        kind = str(item.get("kind") or "").strip()
        if kind:
            keys.append(kind)
    return sorted(set(keys))


def target_assets(report: dict[str, Any], key: str) -> list[str]:
    assets: list[str] = []
    seen: set[str] = set()
    for item in report.get("observed_patterns") or []:
        if not isinstance(item, dict):
            continue
        item_key = ""
        if item.get("kind") == "mistake_correction":
            item_key = f"mistake_correction:{item.get('pattern_key') or ''}"
        elif item.get("kind") == "review_principle":
            item_key = f"review_principle:{item.get('principle_key') or ''}"
        else:
            item_key = str(item.get("kind") or "")
        if item_key != key:
            continue
        for asset in item.get("target_assets") or []:
            value = str(asset).strip()
            if value and value not in seen:
                seen.add(value)
                assets.append(value)
    return assets


def reviewer_status_for(key: str, register: dict[str, Any]) -> str:
    explicit = str(register.get("reviewer_status") or "").strip().lower()
    if explicit:
        return explicit
    if key.startswith("mistake_correction:"):
        return "corrected"
    if key.startswith("review_principle:"):
        return "approved"
    return str(register.get("approval_status") or "unknown").lower()


def outcome_for(key: str) -> str:
    if key.startswith("mistake_correction:"):
        return "corrected"
    if key.startswith("review_principle:"):
        return "reviewer_approved"
    return "observed"


def event_id_for(*parts: str) -> str:
    material = "\x1f".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def build_events(state_dir: Path, task_dir: Path, report_path: Path) -> list[dict[str, Any]]:
    report = read_json(report_path)
    if report.get("generation_mode") != "report_only" or not report.get("meaningful"):
        return []

    register = read_json(task_dir / "register.json")
    repository = repository_for(register)
    repository_key = normalize_repository(repository)
    evidence_ref = relative_ref(report_path, state_dir)
    task_id = str(report.get("task_id") or register.get("task_id") or task_dir.name)
    task_shape = str(report.get("task_shape") or register.get("task_shape") or "unknown")
    project_id = str(register.get("project_id") or state_dir.name)
    project_root_hash = str(register.get("project_root_hash") or "")

    events: list[dict[str, Any]] = []
    for key in proposal_keys(report):
        event_id = event_id_for(repository_key, task_shape, key, key, evidence_ref)
        events.append({
            "schema_version": SCHEMA_VERSION,
            "event_id": event_id,
            "project_id": project_id,
            "project_root_hash": project_root_hash,
            "repository": repository,
            "repository_key": repository_key,
            "task_id": task_id,
            "task_shape": task_shape,
            "pattern_key": key,
            "failure_signature": key,
            "evidence_ref": evidence_ref,
            "reviewer_status": reviewer_status_for(key, register),
            "outcome": outcome_for(key),
            "target_assets": target_assets(report, key),
            "created_at": utc_now_z(),
        })
    return events


def append_unique(output: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    existing = read_jsonl(output)
    seen = {str(row.get("event_id") or "") for row in existing}
    written = 0
    with output.open("a", encoding="utf-8") as handle:
        for event in events:
            if event["event_id"] in seen:
                continue
            seen.add(event["event_id"])
            written += 1
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "status": "ok",
        "generated": len(events),
        "written": written,
        "skipped_existing": len(events) - written,
        "output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="materialize evolution learning events")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--report")
    parser.add_argument("--output")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    task_dir = Path(args.task_dir)
    report_path = Path(args.report) if args.report else task_dir / "context" / "evolution-report.json"
    output = Path(args.output) if args.output else state_dir / "learning" / "events.jsonl"

    events = build_events(state_dir, task_dir, report_path)
    result = append_unique(output, events)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
