#!/usr/bin/env python3
"""Scan changed executable/test files for fake completion markers.

The scanner is intentionally conservative: it uses a closed marker list and
skips markdown documents to avoid treating prose about TODOs as unfinished
implementation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


MARKERS: list[tuple[str, re.Pattern[str]]] = [
    ("kotlin_todo_call", re.compile(r"\bTODO\s*\(", re.IGNORECASE)),
    ("todo_placeholder", re.compile(r"\bTODO\b", re.IGNORECASE)),
    ("fixme_placeholder", re.compile(r"\bFIXME\b", re.IGNORECASE)),
    ("xxx_placeholder", re.compile(r"\bXXX\b", re.IGNORECASE)),
    ("implement_later", re.compile(r"\bimplement\s+later\b", re.IGNORECASE)),
    ("fill_in_details", re.compile(r"\bfill\s+in\s+details\b", re.IGNORECASE)),
    (
        "add_appropriate_error_handling",
        re.compile(r"\badd\s+appropriate\s+error\s+handling\b", re.IGNORECASE),
    ),
    ("disabled_test", re.compile(r"@\s*(Disabled|Ignore)\b")),
    (
        "skipped_test",
        re.compile(r"\b(?:it|test|describe)\.skip\s*\(", re.IGNORECASE),
    ),
    (
        "focused_test_only",
        re.compile(r"\b(?:it|test|describe)\.only\s*\(", re.IGNORECASE),
    ),
    (
        "python_not_implemented",
        re.compile(r"\b(?:raise\s+)?NotImplementedError\b", re.IGNORECASE),
    ),
    (
        "js_not_implemented",
        re.compile(
            r"throw\s+new\s+Error\s*\(\s*['\"][^'\"]*not implemented",
            re.IGNORECASE,
        ),
    ),
]

MARKDOWN_EXTENSIONS = {".md", ".mdx", ".markdown"}
SCANNABLE_EXTENSIONS = {
    ".bash",
    ".c",
    ".cjs",
    ".cpp",
    ".cs",
    ".cts",
    ".go",
    ".gradle",
    ".groovy",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".mjs",
    ".mts",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".zsh",
}
SCANNABLE_FILENAMES = {"Dockerfile", "Jenkinsfile", "Makefile", "Rakefile"}
FENCE_RE = re.compile(r"^\s*```")
BLOCKQUOTE_RE = re.compile(r"^\s*>")
SNIPPET_MAX = 160


def is_scannable_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in MARKDOWN_EXTENSIONS:
        return False
    return (
        suffix in SCANNABLE_EXTENSIONS
        or path.name in SCANNABLE_FILENAMES
        or is_extensionless_executable(path)
    )


def is_extensionless_executable(path: Path) -> bool:
    if path.suffix:
        return False
    return os.access(path, os.X_OK) or has_shebang(path)


def has_shebang(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def normalized_lines(path: Path, text: str) -> Iterable[tuple[int, str]]:
    in_fence = False
    markdown = path.suffix.lower() in MARKDOWN_EXTENSIONS
    for line_number, line in enumerate(text.splitlines(), start=1):
        if markdown and FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if markdown and (in_fence or BLOCKQUOTE_RE.match(line)):
            continue
        yield line_number, line


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [{
            "path": str(path),
            "line": 0,
            "marker": "unreadable_file",
            "token": str(exc),
            "snippet": "",
        }]

    findings: list[dict] = []
    for line_number, line in normalized_lines(path, text):
        for marker, pattern in MARKERS:
            match = pattern.search(line)
            if not match:
                continue
            findings.append({
                "path": str(path),
                "line": line_number,
                "marker": marker,
                "token": match.group(0),
                "snippet": line.strip()[:SNIPPET_MAX],
            })
            break

    return findings


def scan_paths(paths: Iterable[Path | str]) -> dict:
    unique_paths = []
    seen = set()
    for raw_path in paths:
        path = Path(raw_path)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)

    findings: list[dict] = []
    scanned: list[str] = []
    for path in unique_paths:
        if not path.is_file() or not is_scannable_file(path):
            continue
        scanned.append(str(path))
        findings.extend(scan_file(path))

    return {
        "status": "failed" if findings else "passed",
        "scanned": scanned,
        "findings": findings,
    }


def render_text(report: dict) -> str:
    if report["status"] == "passed":
        return f"PASS: no fake completion markers in {len(report['scanned'])} file(s)."

    lines = ["FAIL: fake completion markers found."]
    for finding in report["findings"]:
        lines.append(
            f"- {finding['path']}:{finding['line']} "
            f"{finding['marker']} ({finding['token']})"
        )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", default=[], help="File path to scan.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    report = scan_paths(args.path)
    if args.format == "json":
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(render_text(report))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
