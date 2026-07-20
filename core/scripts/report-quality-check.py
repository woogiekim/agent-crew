#!/usr/bin/env python3
"""Fail-closed answer-quality checks for agent-crew reports."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from quality_loop_lib import check_quality_loop, looks_mutating_task


MEASUREMENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds|m|minutes|%|tokens?|retries?|failures?|passes?|tests?)\b", re.I)
EVIDENCE_RE = re.compile(r"^(?:[-*]\s*)?(?:EVIDENCE|Evidence|evidence)\s*:\s*(.+)$", re.M)
BLOCKER_RE = re.compile(r"^(?:[-*]\s*)?BLOCKER\s*:\s*([a-zA-Z0-9_.:-]+)", re.M)
UNCERTAINTY_RE = re.compile(r"\b(?:Assumption|Unverified|Unknown|uncertain|uncertainty)\b", re.I)
STATUS_COMPLETED_RE = re.compile(r"^STATUS\s*:\s*completed\b", re.I | re.M)
TDD_RE = re.compile(r"\b(TDD|RED|GREEN|test evidence|tests? passed|pytest|JUnit|MockK)\b", re.I)
REVIEW_RE = re.compile(
    r"\b(REVIEW:\s*APPROVED|REVIEW_APPROVED|APPROVED|reviewer approved|"
    r"review findings.*remediated|CHANGES_REQUESTED.*remediated|재리뷰.*승인|리뷰.*승인)\b",
    re.I,
)
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
    ids = set()
    for key in (
        "memory_ids",
        "explicit_memory_ids",
        "accepted_context_memory_ids",
        "retrieved_memory_ids",
    ):
        values = data.get(key, [])
        if isinstance(values, list):
            ids.update(str(mid) for mid in values if str(mid).strip())
    satisfied = data.get("satisfied_by_successor", {})
    if isinstance(satisfied, dict):
        for values in satisfied.values():
            if isinstance(values, list):
                ids.update(str(mid) for mid in values if str(mid).strip())
    return ids


def load_task_text(task_dir: Path, report_text: str) -> str:
    register_path = task_dir / "register.json"
    try:
        register = json.loads(register_path.read_text(encoding="utf-8"))
        if register.get("task"):
            return str(register["task"])
    except Exception:
        pass
    match = re.search(r"^#\s+(.+)$", report_text, re.M)
    return match.group(1) if match else ""


def quality_evidence_from(task_dir: Path, paths: list[str]) -> dict:
    candidates = [
        task_dir / "context" / "tdd_log.md",
        task_dir / "context" / "review.md",
        task_dir / "context" / "reviewer.md",
        task_dir / "context" / "quality-loop.md",
        task_dir / "context" / "quality-loop.json",
    ]
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = task_dir / value
        candidates.append(path)

    tdd_paths: list[str] = []
    review_paths: list[str] = []
    for path in candidates:
        if not path.is_file():
            continue
        rel_name = str(path.relative_to(task_dir)) if path.is_relative_to(task_dir) else str(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        if TDD_RE.search(text):
            tdd_paths.append(rel_name)
        if REVIEW_RE.search(text):
            review_paths.append(rel_name)
    return {
        "tdd_evidence_paths": sorted(set(tdd_paths)),
        "review_evidence_paths": sorted(set(review_paths)),
    }


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
    memory_context_available = bool(memory_ids_from(memory_context) or memory_ids_from(canonical_context))
    if fixture.get("require_memory_evidence_trace_when_context_available") and memory_context_available and not memory_trace.is_file():
        failures.append("missing_memory_evidence_trace")
    if reusable_ids and not reused_ids:
        failures.append("missing_memory_context_reuse")

    task_text = load_task_text(task_dir, text)
    quality_evidence = quality_evidence_from(task_dir, paths)
    quality_loop_required = (
        fixture.get("require_quality_loop_for_implementation_reports")
        and STATUS_COMPLETED_RE.search(text)
        and looks_mutating_task(task_text)
        and "QUALITY_BYPASS_REASON:" not in text
    )
    if quality_loop_required:
        if not quality_evidence["tdd_evidence_paths"]:
            failures.append("missing_tdd_evidence")
        if not quality_evidence["review_evidence_paths"]:
            failures.append("missing_reviewer_evidence")
    pipeline_quality_loop = {}
    blocking_failures = list(failures)
    if (
        quality_loop_required
        and fixture.get("require_pipeline_quality_loop_for_implementation_reports")
    ):
        pipeline_quality_loop = check_quality_loop(task_dir)
        if not pipeline_quality_loop.get("passed", False):
            pipeline_failures = pipeline_quality_loop.get("failures", [])
            pipeline_hard_failures = pipeline_quality_loop.get("hard_failures")
            failures.extend(pipeline_failures)
            blocking_failures.extend(pipeline_hard_failures or pipeline_failures)

    return {
        "passed": not blocking_failures,
        "failures": sorted(set(failures)),
        "blocking_failures": sorted(set(blocking_failures)),
        "evidence_paths": paths,
        "missing_evidence_paths": missing_paths,
        "blockers": blockers,
        "invalid_blockers": invalid_blockers,
        "memory_context_ids": sorted(reusable_ids),
        "reused_memory_context_ids": reused_ids,
        "memory_evidence_trace": str(memory_trace) if memory_trace.is_file() else None,
        "quality_loop_required": bool(quality_loop_required),
        "tdd_evidence_paths": quality_evidence["tdd_evidence_paths"],
        "review_evidence_paths": quality_evidence["review_evidence_paths"],
        "pipeline_quality_loop": pipeline_quality_loop,
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
