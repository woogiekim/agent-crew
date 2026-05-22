#!/usr/bin/env python3
"""Generate compact canonical context from repeated prior outcomes."""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path


CONCLUSION_RE = re.compile(r"^(?:[-*]\s*)?(?:CONCLUSION|Conclusion|conclusion)\s*:\s*(.+)$")
BLOCKER_RE = re.compile(r"^(?:[-*]\s*)?BLOCKER\s*:\s*(.+)$")


def collect(paths: list[Path]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            match = CONCLUSION_RE.match(line) or BLOCKER_RE.match(line)
            if not match:
                continue
            value = " ".join(match.group(1).split())
            if value:
                counter[value] += 1
    return counter


def render(counter: Counter[str], limit: int) -> str:
    lines = ["# Canonical Context", "", "Compact repeated outcomes for downstream reuse.", ""]
    for value, count in counter.most_common(limit):
        lines.append(f"- repeated={count}: {value}")
    if len(lines) == 4:
        lines.append("- Unknown: no repeated prior outcomes were available.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("inputs", nargs="+")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(collect([Path(p) for p in args.inputs]), args.limit), encoding="utf-8")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
