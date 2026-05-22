#!/usr/bin/env python3
"""Validate that a completed implementation task actually ran the quality loop.

Inputs:
  --task-dir DIR              Task state directory containing register.json,
                              pipeline.json, result.md, and progress.buffer.jsonl.
  --require-rework-cycle      Require a reviewer rejection/needs-changes event
                              followed by implementer+TDD retry and re-approval.
  --format text|json          Output format.

Outputs:
  text: PASS/FAIL plus failure labels.
  json: structured validation payload.

Exit codes:
  0 - quality-loop evidence is valid or not required
  1 - validation failed
  2 - invalid arguments
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from quality_loop_lib import check_quality_loop


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--require-rework-cycle", action="store_true")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"quality-loop-check: task dir not found: {task_dir}", file=sys.stderr)
        return 2

    result = check_quality_loop(
        task_dir,
        require_rework_cycle=args.require_rework_cycle,
    )
    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(("PASS" if result["passed"] else "FAIL") + ": pipeline quality loop")
        for failure in result["failures"]:
            print(f"- {failure}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
