#!/usr/bin/env python3
"""파일 존재와 실행 계획 준비를 구분하는 읽기 전용 supervisor preflight."""
import argparse
import json
from pathlib import Path
import sys


def start_mode(path):
    if not path.exists():
        return "fresh"
    pipeline = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(pipeline, dict):
        raise ValueError("pipeline must be an object")
    required = pipeline.get("planning_required", False)
    if not isinstance(required, bool):
        raise ValueError("planning_required must be boolean")
    if required:
        if pipeline.get("stages") != ["supervisor"] or pipeline.get("completed_stages", 0) != 0:
            raise ValueError("planning placeholder conflicts with execution state")
        return "fresh"
    return "resume"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(start_mode(args.pipeline))
    except (ValueError, OSError) as error:
        print(f"supervisor start blocked: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
