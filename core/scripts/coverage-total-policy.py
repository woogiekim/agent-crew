#!/usr/bin/env python3
"""Validate full Python coverage policy without hiding legacy debt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EPSILON = 0.01
REQUIRED_EXCEPTION_FIELDS = {
    "baseline_percent",
    "max_missing_lines",
    "owner",
    "reason",
    "target",
}


def normalize_path(value: str) -> str:
    return Path(value).as_posix().removeprefix("./")


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def coverage_files(payload: dict[str, Any]) -> dict[str, Any]:
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage JSON is missing a files object")
    return {normalize_path(path): value for path, value in files.items()}


def exception_entries(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = payload.get("exceptions")
    if not isinstance(entries, list):
        raise ValueError("coverage exceptions JSON is missing an exceptions list")

    indexed: dict[str, dict[str, Any]] = {}
    defaults = {
        "owner": payload.get("default_owner"),
        "reason": payload.get("default_reason"),
        "target": payload.get("default_target"),
    }
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("path"):
            raise ValueError("each coverage exception must be an object with a path")
        path = normalize_path(str(entry["path"]))
        if path in indexed:
            raise ValueError(f"duplicate coverage exception: {path}")
        indexed[path] = {**defaults, **entry}
    return indexed


def percent_covered(payload: dict[str, Any]) -> float:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return 0.0
    return float(summary.get("percent_covered", 0.0))


def missing_count(payload: dict[str, Any]) -> int:
    missing = payload.get("missing_lines", [])
    return len(missing) if isinstance(missing, list) else 0


def invalid_exception_fields(entry: dict[str, Any]) -> list[str]:
    return sorted(field for field in REQUIRED_EXCEPTION_FIELDS if field not in entry)


def failure(path: str, code: str, detail: str) -> dict[str, str]:
    return {"path": path, "code": code, "detail": detail}


def evaluate(
    coverage_payload: dict[str, Any],
    exceptions_payload: dict[str, Any],
    minimum: float,
    prefix: str,
) -> dict[str, Any]:
    files = coverage_files(coverage_payload)
    exceptions = exception_entries(exceptions_payload)
    failures: list[dict[str, str]] = []
    covered: list[str] = []
    legacy: list[str] = []

    for path in sorted(exceptions):
        if path not in files:
            failures.append(failure(path, "stale_exception", "exception path is absent from coverage data"))

    for path, payload in sorted(files.items()):
        if not path.startswith(prefix) or not path.endswith(".py"):
            continue

        percent = percent_covered(payload)
        missing = missing_count(payload)
        exception = exceptions.get(path)
        if percent + EPSILON >= minimum:
            covered.append(path)
            if exception is not None:
                failures.append(failure(path, "obsolete_exception", "file now meets 100%; remove exception"))
            continue

        if exception is None:
            failures.append(failure(path, "missing_exception", f"{percent:.2f}% coverage is below {minimum:.2f}%"))
            continue

        missing_fields = invalid_exception_fields(exception)
        if missing_fields:
            failures.append(failure(path, "invalid_exception", "missing fields: " + ", ".join(missing_fields)))
            continue

        baseline = float(exception["baseline_percent"])
        max_missing = int(exception["max_missing_lines"])
        if percent + EPSILON < baseline:
            failures.append(failure(path, "coverage_regressed", f"{percent:.2f}% below baseline {baseline:.2f}%"))
        if missing > max_missing:
            failures.append(failure(path, "missing_lines_regressed", f"{missing} missing lines exceeds {max_missing}"))
        legacy.append(path)

    totals = coverage_payload.get("totals", {})
    raw_total = float(totals.get("percent_covered", 0.0)) if isinstance(totals, dict) else 0.0
    return {
        "status": "passed" if not failures else "failed",
        "minimum": minimum,
        "raw_total_percent": raw_total,
        "covered_100_count": len(covered),
        "legacy_exception_count": len(legacy),
        "covered_100": covered,
        "legacy_exceptions": legacy,
        "failures": failures,
    }


def render_text(report: dict[str, Any]) -> str:
    if report["status"] == "passed":
        return (
            "PASS: full Python coverage policy satisfied "
            f"({report['covered_100_count']} file(s) at 100%, "
            f"{report['legacy_exception_count']} legacy exception(s), "
            f"raw total {report['raw_total_percent']:.2f}%)."
        )

    lines = ["FAIL: full Python coverage policy violations:"]
    for item in report["failures"]:
        lines.append(f"- {item['path']}: {item['code']} - {item['detail']}")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", default="coverage.json")
    parser.add_argument("--exceptions", default="core/coverage/python-coverage-exceptions.json")
    parser.add_argument("--minimum", type=float, default=100.0)
    parser.add_argument("--prefix", default="core/scripts/")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = evaluate(
            load_json(Path(args.coverage_json)),
            load_json(Path(args.exceptions)),
            args.minimum,
            args.prefix,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
