#!/usr/bin/env python3
"""Validate task-local artifact references in semantic agent completions.

Semantic agents return compact pointers to durable task artifacts. This helper
checks those pointers and reads only enough UTF-8 content to reject empty or
whitespace-only artifacts; it does not duplicate artifact content.

Exit codes:
  0 - accepted or not applicable to the agent
  1 - semantic completion requires a validation retry
  2 - invalid arguments or unreadable response input

Example:
  check-completion-artifact.py --agent planner --task-dir TASK_DIR \
    --response RESPONSE_FILE --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from completion_artifact_lib import validate


def read_response(path: str | None) -> tuple[str, str | None]:
    if path is None:
        return sys.stdin.read(), None

    try:
        return Path(path).read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return "", f"check-completion-artifact: cannot read response: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--response")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()

    text, error = read_response(args.response)
    if error:
        print(error, file=sys.stderr)
        return 2

    result = validate(args.agent, Path(args.task_dir), text)
    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"ACTION: {result['action']}")
        print(f"REASON: {result['reason']}")
        if result["field"]:
            print(f"FIELD: {result['field']}")
        if result["path"]:
            print(f"PATH: {result['path']}")

    return 1 if result["action"] == "retry_validation" else 0


if __name__ == "__main__":
    raise SystemExit(main())
