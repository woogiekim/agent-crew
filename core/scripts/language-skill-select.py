#!/usr/bin/env python3
"""Select effective-language skills from changed source paths only."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


SKILL_BY_SUFFIX = {
    ".kt": "effective-kotlin.md",
    ".java": "effective-java.md",
    ".ts": "effective-typescript.md",
    ".tsx": "effective-typescript.md",
    ".mts": "effective-typescript.md",
    ".cts": "effective-typescript.md",
    ".js": "effective-typescript.md",
    ".jsx": "effective-typescript.md",
    ".mjs": "effective-typescript.md",
    ".cjs": "effective-typescript.md",
    ".py": "effective-python.md",
    ".go": "effective-go.md",
    ".rs": "effective-rust.md",
    ".scala": "effective-scala.md",
    ".sc": "effective-scala.md",
    ".swift": "effective-swift.md",
}

AGENT_SKILLS = {
    "backend": {
        "effective-kotlin.md",
        "effective-java.md",
        "effective-python.md",
        "effective-go.md",
        "effective-rust.md",
        "effective-scala.md",
    },
    "frontend": {"effective-typescript.md", "effective-swift.md"},
    "reviewer": set(SKILL_BY_SUFFIX.values()),
    "test-writer": set(SKILL_BY_SUFFIX.values()),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select language skills from changed source file paths."
    )
    parser.add_argument("--agent", required=True, choices=sorted(AGENT_SKILLS))
    parser.add_argument("changed_files", nargs="*")
    parser.add_argument("--changed-file", action="append", default=[])
    return parser.parse_args()


def skill_root() -> Path:
    configured_home = os.environ.get("AGENT_CREW_HOME")
    if configured_home:
        installed = Path(configured_home) / "system" / "agents" / "skills"
        if installed.is_dir():
            return installed

    return Path(__file__).resolve().parents[1] / "agents" / "skills"


def select(agent: str, changed_files: list[str]) -> list[Path]:
    allowed = AGENT_SKILLS[agent]
    names = {
        skill_name
        for changed_file in changed_files
        if (skill_name := SKILL_BY_SUFFIX.get(Path(changed_file).suffix.lower()))
        and skill_name in allowed
    }
    root = skill_root()
    return [root / name for name in sorted(names)]


def main() -> int:
    args = parse_args()
    stdin_files = []
    if not sys.stdin.isatty():
        stdin_files = [line for line in sys.stdin.read().splitlines() if line]
    changed_files = [*args.changed_files, *args.changed_file, *stdin_files]
    for path in select(args.agent, changed_files):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
