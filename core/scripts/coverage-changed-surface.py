#!/usr/bin/env python3
"""Enforce 100% coverage for changed Python execution surfaces."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def normalize_path(value: str) -> str:
    return Path(value).as_posix().removeprefix("./")


def is_python_execution_surface(path: str) -> bool:
    normalized = normalize_path(path)
    return normalized.startswith("core/scripts/") and normalized.endswith(".py")


def git_diff_names(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "git diff failed"
        raise RuntimeError(reason)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def git_untracked_names() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "git ls-files failed"
        raise RuntimeError(reason)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(base_ref: str) -> list[str]:
    paths = []
    paths.extend(git_diff_names([f"{base_ref}...HEAD"]))
    paths.extend(git_diff_names(["--cached"]))
    paths.extend(git_diff_names([]))
    paths.extend(git_untracked_names())
    return sorted(dict.fromkeys(paths))


def load_coverage(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage JSON is missing a files object")
    return files


def coverage_index(files: dict[str, Any]) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for raw_path, payload in files.items():
        normalized = normalize_path(raw_path)
        indexed[normalized] = payload
        if "/core/scripts/" in normalized:
            indexed["core/scripts/" + normalized.rsplit("/core/scripts/", 1)[1]] = payload
    return indexed


def percent_covered(payload: dict[str, Any]) -> float:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return 0.0
    percent = summary.get("percent_covered_display", summary.get("percent_covered", 0))
    return float(str(percent).removesuffix("%"))


def missing_lines(payload: dict[str, Any]) -> list[int]:
    raw_lines = payload.get("missing_lines", [])
    if not isinstance(raw_lines, list):
        return []
    return [line for line in raw_lines if isinstance(line, int)]


def evaluate(files: dict[str, Any], paths: list[str], minimum: float) -> dict[str, Any]:
    index = coverage_index(files)
    targets = sorted({normalize_path(path) for path in paths if is_python_execution_surface(path)})
    results = []
    for target in targets:
        payload = index.get(target)
        if payload is None:
            results.append({
                "path": target,
                "status": "failed",
                "reason": "missing_coverage_data",
                "coverage": 0.0,
                "missing_lines": [],
            })
            continue
        coverage = percent_covered(payload)
        results.append({
            "path": target,
            "status": "passed" if coverage >= minimum else "failed",
            "reason": "ok" if coverage >= minimum else "coverage_below_minimum",
            "coverage": coverage,
            "missing_lines": missing_lines(payload),
        })

    return {
        "status": "passed" if all(item["status"] == "passed" for item in results) else "failed",
        "minimum": minimum,
        "target_files": targets,
        "results": results,
    }


def render_text(report: dict[str, Any]) -> str:
    if not report["target_files"]:
        return "PASS: no changed Python execution surfaces require coverage."
    if report["status"] == "passed":
        return f"PASS: {len(report['target_files'])} changed Python execution surface(s) meet 100% coverage."
    lines = ["FAIL: changed Python execution surface coverage is below 100%."]
    for item in report["results"]:
        if item["status"] == "failed":
            lines.append(
                f"- {item['path']}: {item['coverage']:.2f}% "
                f"({item['reason']}; missing={item['missing_lines']})"
            )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", default=".coverage.json")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--minimum", type=float, default=100.0)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        files = load_coverage(Path(args.coverage_json))
        paths = args.changed_file or changed_files(args.base_ref)
        report = evaluate(files, paths, args.minimum)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
