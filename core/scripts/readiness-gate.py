#!/usr/bin/env python3
"""Evaluate the commercial readiness gate from validation and workload evidence.

Inputs:
  --state-dir PATH             project state directory used to generate local evidence
  --validation-report PATH     repeatable validation report JSON
  --workload-evidence PATH     repeatable workload evidence JSON
  --thresholds PATH            optional JSON threshold overrides
  --include-agent-requests     include direct-agent requests in generated evidence
  --recent N                   local evidence window; 0 means all

Outputs:
  JSON or text readiness gate report with metric statuses and blockers.

Exit codes:
  0 - readiness gate passed
  1 - gate failed because one or more metrics are blocked
  2 - invalid arguments or unreadable evidence
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core_objective_lib import capability_ceiling, format_ceiling_text


DEFAULT_THRESHOLDS = {
    "consecutive_clean_full_validation_runs": 1.0,
    "host_bridge_completion_rate": 0.95,
    "human_intervention_rate": 0.02,
    "retry_rate": 0.10,
    "task_success_rate": 0.95,
}


def load_script_module(script_name: str, module_name: str):
    path = Path(__file__).resolve().with_name(script_name)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise ValueError(f"cannot load helper script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return data


def load_thresholds(path: Path | None) -> dict[str, float]:
    thresholds = dict(DEFAULT_THRESHOLDS)
    if path is None:
        return thresholds

    overrides = load_json(path)
    for key, value in overrides.items():
        if value is None:
            continue
        try:
            thresholds[key] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"threshold {key} must be numeric") from exc
    return thresholds


def generated_workload_evidence(
    state_dir: Path | None,
    *,
    recent: int,
    include_agent_requests: bool,
) -> dict[str, Any] | None:
    if state_dir is None or not state_dir.is_dir():
        return None

    workload = load_script_module("hosted-workload-evidence.py", "hosted_workload_evidence")
    return workload.build_evidence(
        state_dir,
        recent=recent,
        adapter="local",
        include_agent_requests=include_agent_requests,
    )


def load_capabilities(state_dir: Path | None) -> dict[str, Any] | None:
    if state_dir is None:
        return None
    path = state_dir / "capabilities.json"
    if not path.is_file():
        return None
    return load_json(path)


def metric_blocker(metric: dict[str, Any], *, validation_reports_supplied: bool) -> dict[str, Any] | None:
    if metric.get("status") == "passed":
        return None

    metric_id = str(metric.get("id") or "unknown")
    if metric_id == "consecutive_clean_full_validation_runs" and not validation_reports_supplied:
        return {
            "id": "missing_validation_report",
            "metric": metric_id,
            "status": metric.get("status"),
            "value": metric.get("value"),
            "threshold": metric.get("threshold"),
            "reason": "No validation report was supplied for the readiness gate.",
            "next_action": "Run phase validation and pass --validation-report PATH.",
        }

    if metric.get("status") == "unmeasured":
        return {
            "id": f"unmeasured:{metric_id}",
            "metric": metric_id,
            "status": "unmeasured",
            "value": metric.get("value"),
            "threshold": metric.get("threshold"),
            "reason": "The metric has no measurable evidence.",
            "next_action": "Run crew readiness workload --output PATH, or provide explicit --workload-evidence PATH.",
        }

    direction = str(metric.get("direction") or "at_least")
    comparison = ">=" if direction == "at_least" else "<="
    return {
        "id": f"threshold:{metric_id}",
        "metric": metric_id,
        "status": metric.get("status"),
        "value": metric.get("value"),
        "threshold": metric.get("threshold"),
        "reason": f"Metric does not satisfy required threshold ({comparison} {metric.get('threshold')}).",
        "next_action": "Improve the underlying workflow evidence, then rerun the readiness gate.",
    }


def build_gate_report(
    validation_reports: list[dict[str, Any]],
    workload_evidence: list[dict[str, Any]],
    thresholds: dict[str, float],
    *,
    evidence_mode: str = "unknown",
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics_module = load_script_module("readiness-metrics.py", "readiness_metrics")
    metrics = metrics_module.build_report(validation_reports, workload_evidence, thresholds)
    blockers = [
        blocker
        for metric in metrics["metrics"]
        if (blocker := metric_blocker(metric, validation_reports_supplied=bool(validation_reports))) is not None
    ]

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "passed": not blockers,
        "evidence_mode": evidence_mode,
        "evidence_sources": [
            {
                "source": str(item.get("source") or "unknown"),
                "adapter": str(item.get("adapter") or "unknown"),
                "tasks": int(item.get("tasks", item.get("total_tasks", 0)) or 0),
                "generated_at": item.get("generated_at"),
                "validation_mode": item.get("validation_mode"),
            }
            for item in workload_evidence
        ],
        "thresholds": thresholds,
        "metrics": metrics,
        "blockers": blockers,
    }
    if capabilities is not None:
        ceiling = capability_ceiling(capabilities)
        ceiling["framework_gate_passed"] = report["passed"]
        report["core_objective"] = ceiling
    return report


def text_report(report: dict[str, Any]) -> str:
    lines = [
        "PASS: readiness gate" if report["passed"] else "FAIL: readiness gate",
        f"evidence_mode={report.get('evidence_mode', 'unknown')}",
        f"blockers={len(report['blockers'])}",
    ]
    for blocker in report["blockers"]:
        lines.append(
            f"- {blocker['id']}: metric={blocker['metric']} "
            f"value={blocker['value']} threshold={blocker['threshold']} "
            f"next={blocker['next_action']}"
        )
    lines.append("metrics:")
    for metric in report["metrics"]["metrics"]:
        lines.append(
            f"- {metric['status']} {metric['id']}: "
            f"value={metric['value']} threshold={metric['threshold']}"
        )
    core_objective = report.get("core_objective")
    if core_objective:
        lines.append("core_objective:")
        lines.append(f"- framework_gate_passed={str(report['passed']).lower()}")
        lines.append(f"- host_runtime_ceiling={format_ceiling_text(core_objective)}")
        lines.append(f"- summary={core_objective.get('summary')}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", help="Project state directory used to generate workload evidence.")
    parser.add_argument("--recent", type=int, default=20, help="Most recent local tasks/requests to include; 0 means all.")
    parser.add_argument("--include-agent-requests", action="store_true", help="Include direct-agent request evidence.")
    parser.add_argument("--validation-report", action="append", default=[], help="Validation report JSON.")
    parser.add_argument("--workload-evidence", action="append", default=[], help="Workload evidence JSON.")
    parser.add_argument("--thresholds", help="Optional threshold override JSON.")
    parser.add_argument("--output", help="Write readiness gate JSON to this path.")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    try:
        validation_reports = [load_json(Path(path).expanduser()) for path in args.validation_report]
        workload_evidence = [load_json(Path(path).expanduser()) for path in args.workload_evidence]
        evidence_mode = "explicit_workload_evidence" if workload_evidence else "generated_local_state"
        state_dir = Path(args.state_dir).expanduser().resolve() if args.state_dir else None
        if not workload_evidence:
            local_evidence = generated_workload_evidence(
                state_dir,
                recent=max(args.recent, 0),
                include_agent_requests=args.include_agent_requests,
            )
            if local_evidence is not None:
                workload_evidence.append(local_evidence)
            else:
                evidence_mode = "missing_workload_evidence"
        thresholds = load_thresholds(Path(args.thresholds).expanduser() if args.thresholds else None)
        report = build_gate_report(
            validation_reports,
            workload_evidence,
            thresholds,
            evidence_mode=evidence_mode,
            capabilities=load_capabilities(state_dir),
        )
    except ValueError as exc:
        print(f"readiness-gate: {exc}", file=sys.stderr)
        return 2

    if args.output:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(text_report(report))

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
