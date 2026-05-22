#!/usr/bin/env python3
"""Fail-closed answer-quality checks for agent-crew reports."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


MEASUREMENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds|m|minutes|%|tokens?|retries?|failures?|passes?|tests?)\b", re.I)
EVIDENCE_RE = re.compile(r"^(?:[-*]\s*)?(?:EVIDENCE|Evidence|evidence)\s*:\s*(.+)$", re.M)
BLOCKER_RE = re.compile(r"^(?:[-*]\s*)?BLOCKER\s*:\s*([a-zA-Z0-9_.:-]+)", re.M)
UNCERTAINTY_RE = re.compile(r"\b(?:Assumption|Unverified|Unknown|uncertain|uncertainty)\b", re.I)
MEMORY_ID_RE = re.compile(
    r"\b(?:"
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
    r"|"
    r"(?=[a-z0-9_.:-]{6,}\b)(?=[a-z0-9_.:-]*(?:[_.:-]|\d))[a-z0-9][a-z0-9_.:-]+"
    r")\b",
    re.I,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_paths(text: str) -> list[str]:
    paths: list[str] = []
    for raw in EVIDENCE_RE.findall(text):
        value = raw.strip()
        if value.startswith("[") and "](" in value:
            value = value.split("](", 1)[1].split(")", 1)[0]
        value = value.split("#", 1)[0].strip().strip("`")
        if value:
            paths.append(value)
    return paths


def memory_ids_from(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return set(MEMORY_ID_RE.findall(path.read_text(encoding="utf-8", errors="replace")))


def memory_ids_from_trace(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {str(mid) for mid in data.get("memory_ids", []) if str(mid).strip()}


def check_report(report_path: Path, task_dir: Path, fixture: dict) -> dict:
    text = report_path.read_text(encoding="utf-8", errors="replace")
    failures: list[str] = []

    if not MEASUREMENT_RE.search(text):
        failures.append("missing_measurements")

    paths = evidence_paths(text)
    if not paths:
        failures.append("missing_evidence")
    missing_paths = []
    for value in paths:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = task_dir / value
        if not candidate.exists():
            missing_paths.append(value)
    if missing_paths:
        failures.append("invalid_evidence_paths")

    blockers = BLOCKER_RE.findall(text)
    allowed = set(fixture.get("allowed_blockers", []))
    invalid_blockers = [b for b in blockers if allowed and b not in allowed]
    if invalid_blockers:
        failures.append("invalid_blocker_classification")

    if not UNCERTAINTY_RE.search(text):
        failures.append("missing_uncertainty")

    memory_context = task_dir / fixture.get("memory_context_path", "context/memory.md")
    canonical_context = task_dir / fixture.get("canonical_context_path", "context/canonical-context.md")
    memory_trace = task_dir / fixture.get("memory_evidence_trace_path", "context/memory-evidence.json")
    reusable_ids = (
        memory_ids_from(memory_context)
        | memory_ids_from(canonical_context)
        | memory_ids_from_trace(memory_trace)
    )
    reused_ids = sorted(mid for mid in reusable_ids if mid in text)
    if reusable_ids and not reused_ids:
        failures.append("missing_memory_context_reuse")

    return {
        "passed": not failures,
        "failures": failures,
        "evidence_paths": paths,
        "missing_evidence_paths": missing_paths,
        "blockers": blockers,
        "invalid_blockers": invalid_blockers,
        "memory_context_ids": sorted(reusable_ids),
        "reused_memory_context_ids": reused_ids,
    }


def stale_blocker_count_from_telemetry(path) -> int:
    if not path:
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    summary = data.get("summary", {}) if isinstance(data, dict) else {}
    try:
        return int(summary.get("tasks_stale_blocked") or 0)
    except Exception:
        return 0


def has_stale_blocker_classification(text: str) -> bool:
    return (
        "stale_host_bridge_not_invoked" in text
        or re.search(r"^STALE_BLOCKERS\s*:\s*\d+", text, re.I | re.M) is not None
    )


def main() -> int:
    default_fixture = Path(__file__).resolve().parent.parent / "evaluations" / "answer-quality.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--task-dir", required=True)
    parser.add_argument("--fixture", default=str(default_fixture))
    parser.add_argument("--telemetry", help="Optional telemetry JSON evidence used to require stale-blocker classification.")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    report_path = Path(args.report)
    result = check_report(report_path, Path(args.task_dir), load_json(Path(args.fixture)))
    stale_count = stale_blocker_count_from_telemetry(Path(args.telemetry) if args.telemetry else None)
    result["stale_blocker_count"] = stale_count
    if stale_count > 0:
        text = report_path.read_text(encoding="utf-8", errors="replace")
        if not has_stale_blocker_classification(text):
            result["failures"].append("missing_stale_blocker_classification")
            result["passed"] = False
    if args.format == "json":
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(("PASS" if result["passed"] else "FAIL") + ": report quality")
        for failure in result["failures"]:
            print(f"- {failure}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
