#!/usr/bin/env python3
"""Best-effort mistake/correction event recorder.

Recording failures are intentionally non-blocking: learning must not slow or
fail the main workflow.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def split_values(values: list[str]) -> list[str]:
    items: list[str] = []
    for value in values:
        for item in str(value).split(","):
            item = item.strip()
            if item:
                items.append(item)
    return items


def build_event(args: argparse.Namespace) -> dict:
    return {
        "schema_version": 1,
        "event_type": "mistake_correction",
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "surface": args.surface,
        "mistake_type": args.mistake_type,
        "pattern_key": args.pattern_key,
        "original_decision": args.original_decision,
        "corrected_decision": args.corrected_decision,
        "correction_source": args.correction_source,
        "summary": args.summary,
        "evidence_refs": split_values(args.evidence_ref),
        "target_assets": split_values(args.target_asset),
        "non_blocking": True,
    }


def append_event(task_dir: Path, event: dict) -> bool:
    try:
        context_dir = task_dir / "context"
        context_dir.mkdir(parents=True, exist_ok=True)
        with (context_dir / "mistake-events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return True
    except Exception:
        return False


def record(args: argparse.Namespace) -> int:
    written = append_event(Path(args.task_dir), build_event(args))
    print(json.dumps({"status": "recorded" if written else "skipped", "non_blocking": True}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Record non-blocking mistake correction events")
    subparsers = parser.add_subparsers(dest="command")

    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--task-dir", required=True)
    record_parser.add_argument("--surface", required=True)
    record_parser.add_argument("--mistake-type", required=True)
    record_parser.add_argument("--pattern-key", required=True)
    record_parser.add_argument("--original-decision", default="")
    record_parser.add_argument("--corrected-decision", default="")
    record_parser.add_argument("--correction-source", default="unknown")
    record_parser.add_argument("--summary", required=True)
    record_parser.add_argument("--evidence-ref", action="append", default=[])
    record_parser.add_argument("--target-asset", action="append", default=[])
    record_parser.set_defaults(func=record)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
