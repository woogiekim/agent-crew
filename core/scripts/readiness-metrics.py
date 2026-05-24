#!/usr/bin/env python3
"""Aggregate commercialization readiness decision metrics from evidence files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METRIC_IDS = [
    "consecutive_clean_full_validation_runs",
    "host_bridge_completion_rate",
    "human_intervention_rate",
    "retry_rate",
    "task_success_rate",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validation_clean(report: dict[str, Any]) -> bool:
    if report.get("plan_only"):
        return False
    return report.get("passed") is True


def consecutive_clean(reports: list[dict[str, Any]]) -> int:
    count = 0
    for report in reversed(reports):
        if validation_clean(report):
            count += 1
            continue
        break

    return count


def rate(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def evidence_totals(evidence: list[dict[str, Any]]) -> dict[str, float]:
    totals = {
        "tasks": 0.0,
        "successes": 0.0,
        "host_bridge_completed": 0.0,
        "manual_repairs": 0.0,
        "retries": 0.0,
    }
    for item in evidence:
        totals["tasks"] += float(item.get("tasks", item.get("total_tasks", 0)) or 0)
        totals["successes"] += float(item.get("successes", item.get("successful_tasks", 0)) or 0)
        totals["host_bridge_completed"] += float(item.get("host_bridge_completed", 0) or 0)
        totals["manual_repairs"] += float(item.get("manual_repairs", item.get("human_interventions", 0)) or 0)
        totals["retries"] += float(item.get("retries", 0) or 0)

    return totals


def metric_status(value: float | None, threshold: float | None, *, direction: str) -> str:
    if value is None or threshold is None:
        return "unmeasured"
    if direction == "at_most":
        return "passed" if value <= threshold else "needs_attention"
    return "passed" if value >= threshold else "needs_attention"


def build_report(
    validation_reports: list[dict[str, Any]],
    workload_evidence: list[dict[str, Any]],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    totals = evidence_totals(workload_evidence)
    task_count = totals["tasks"]
    metrics = [
        {
            "id": "consecutive_clean_full_validation_runs",
            "value": consecutive_clean(validation_reports),
            "threshold": thresholds.get("consecutive_clean_full_validation_runs"),
            "direction": "at_least",
        },
        {
            "id": "host_bridge_completion_rate",
            "value": rate(totals["host_bridge_completed"], task_count),
            "threshold": thresholds.get("host_bridge_completion_rate"),
            "direction": "at_least",
        },
        {
            "id": "human_intervention_rate",
            "value": rate(totals["manual_repairs"], task_count),
            "threshold": thresholds.get("human_intervention_rate"),
            "direction": "at_most",
        },
        {
            "id": "retry_rate",
            "value": rate(totals["retries"], task_count),
            "threshold": thresholds.get("retry_rate"),
            "direction": "at_most",
        },
        {
            "id": "task_success_rate",
            "value": rate(totals["successes"], task_count),
            "threshold": thresholds.get("task_success_rate"),
            "direction": "at_least",
        },
    ]
    for metric in metrics:
        metric["status"] = metric_status(
            metric["value"],
            metric["threshold"],
            direction=str(metric["direction"]),
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "totals": totals,
        "metrics": metrics,
        "passed": all(metric["status"] == "passed" for metric in metrics),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-report", action="append", default=[], help="Phase 1 or Phase 2 validation JSON report.")
    parser.add_argument("--workload-evidence", action="append", default=[], help="Hosted/workload evidence JSON.")
    parser.add_argument("--thresholds", help="Optional JSON file with metric thresholds.")
    parser.add_argument("--output", help="Write readiness metric JSON to this path.")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    validation_reports = [load_json(Path(path).expanduser()) for path in args.validation_report]
    workload_evidence = [load_json(Path(path).expanduser()) for path in args.workload_evidence]
    thresholds = load_json(Path(args.thresholds).expanduser()) if args.thresholds else {}
    report = build_report(validation_reports, workload_evidence, thresholds)

    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.format == "json":
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print("PASS: readiness metrics" if report["passed"] else "FAIL: readiness metrics")
        for metric in report["metrics"]:
            print(f"- {metric['status']} {metric['id']}: value={metric['value']} threshold={metric['threshold']}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
