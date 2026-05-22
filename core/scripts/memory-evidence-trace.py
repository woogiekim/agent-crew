#!/usr/bin/env python3
"""Record memory/evidence usage for answer-quality audits."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_evidence(task_dir: Path, values: list[str]) -> tuple[list[str], list[str]]:
    existing = []
    missing = []
    for value in values:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = task_dir / value
        if candidate.exists():
            existing.append(value)
        else:
            missing.append(value)
    return existing, missing


def write_markdown(path: Path, trace: dict) -> None:
    lines = [
        "# Memory Evidence Trace",
        "",
        f"CREATED_AT: {trace['created_at']}",
        f"MEMORY_CONTEXT_REUSED: {'yes' if trace['memory_context_reused'] else 'no'}",
    ]
    if trace["memory_ids"]:
        lines.append("MEMORY_IDS: " + ", ".join(trace["memory_ids"]))
    for evidence in trace["evidence_paths"]:
        lines.append(f"EVIDENCE: {evidence}")
    if trace["missing_evidence_paths"]:
        lines.append("MISSING_EVIDENCE: " + ", ".join(trace["missing_evidence_paths"]))
    if trace["note"]:
        lines.append(f"NOTE: {trace['note']}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--memory-id", action="append", default=[])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--reused", choices=["yes", "no"], required=True)
    parser.add_argument("--source", default="manual")
    parser.add_argument("--note", default="")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    task_dir = Path(args.task_dir).expanduser().resolve()
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    evidence_paths, missing_paths = resolve_evidence(task_dir, args.evidence)
    trace = {
        "schema_version": 1,
        "created_at": utc_now_z(),
        "task_dir": str(task_dir),
        "source": args.source,
        "memory_ids": args.memory_id,
        "evidence_paths": evidence_paths,
        "missing_evidence_paths": missing_paths,
        "memory_context_reused": args.reused == "yes",
        "note": args.note,
    }

    json_path = context_dir / "memory-evidence.json"
    markdown_path = context_dir / "memory-evidence.md"
    json_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(markdown_path, trace)

    if args.format == "json":
        print(json.dumps(trace, ensure_ascii=False, indent=2))
    else:
        print(f"TRACE: {json_path}")
        print(f"MEMORY_CONTEXT_REUSED: {'yes' if trace['memory_context_reused'] else 'no'}")
        if missing_paths:
            print("MISSING_EVIDENCE: " + ", ".join(missing_paths))

    return 1 if missing_paths else 0


if __name__ == "__main__":
    raise SystemExit(main())
