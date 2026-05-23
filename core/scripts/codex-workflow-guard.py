#!/usr/bin/env python3
"""Codex adapter workflow-state guard.

The guard converts workflow-sensitive Codex policy checks into deterministic
state validation that command wrappers and tests can run before continuing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate_state(task_dir: Path, require: list[str]) -> dict:
    checks = {
        "task-dir": task_dir.is_dir(),
        "handoff": (task_dir / "handoff.md").is_file(),
        "pipeline": (task_dir / "pipeline.json").is_file(),
        "register": (task_dir / "register.json").is_file(),
    }
    missing = [name for name in require if not checks.get(name, False)]
    return {
        "status": "blocked" if missing else "ok",
        "task_dir": str(task_dir),
        "missing": missing,
        "checks": checks,
        "blocker": "missing_required_state_markers" if missing else "",
        "next": "Run crew:run/crew run to create workflow state, or resume from a valid TASK_DIR." if missing else "",
    }


def print_text(result: dict) -> None:
    if result["status"] == "ok":
        print("STATUS: ok")
        return
    print("STATUS: blocked")
    print(f"BLOCKER: {result['blocker']}")
    print(f"MISSING: {', '.join(result['missing'])}")
    print(f"NEXT: {result['next']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument(
        "--require",
        action="append",
        choices=["task-dir", "handoff", "pipeline", "register"],
        default=[],
        help="Required marker. May be repeated.",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    required = args.require or ["task-dir", "handoff", "pipeline", "register"]
    result = validate_state(Path(args.task_dir).expanduser(), required)
    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print_text(result)
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
