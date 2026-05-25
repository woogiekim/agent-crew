#!/usr/bin/env python3
"""Validate round 2 persistent workflow operational chaos scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_CHAOS = {
    "process crash",
    "runtime restart",
    "partial persistence failure",
    "plugin failure",
    "token exhaustion",
    "memory corruption",
    "infrastructure interruption",
}
REQUIRED_METRICS = {
    "Resume Success Rate",
    "Workflow Survival Rate",
    "Recovery Accuracy",
    "Approval Integrity",
    "Deterministic Stability",
    "Workflow Continuity Score",
}
RECOVERY_REQUIRED_CHAOS = {
    "process crash",
    "runtime restart",
    "partial persistence failure",
    "plugin failure",
    "token exhaustion",
    "memory corruption",
    "infrastructure interruption",
}
SAFE_BLOCK_CHAOS = {"partial persistence failure", "memory corruption"}
ALLOWED_TRANSITIONS = {
    "PLANNING": {"CHECKPOINTING", "EXECUTING", "WAITING_APPROVAL", "BLOCKED_SAFELY"},
    "CHECKPOINTING": {"EXECUTING", "INTERRUPTED", "WAITING_APPROVAL", "BLOCKED_SAFELY"},
    "EXECUTING": {"WAITING_APPROVAL", "INTERRUPTED", "RECOVERING", "COMPLETED", "BLOCKED_SAFELY"},
    "WAITING_APPROVAL": {"EXECUTING", "INTERRUPTED", "RECOVERING", "BLOCKED_SAFELY"},
    "INTERRUPTED": {"RECOVERING", "BLOCKED_SAFELY"},
    "RECOVERING": {"EXECUTING", "WAITING_APPROVAL", "COMPLETED", "BLOCKED_SAFELY"},
    "COMPLETED": set(),
    "BLOCKED_SAFELY": set(),
}
TERMINAL_STATUS = {
    "COMPLETED": "completed",
    "BLOCKED_SAFELY": "blocked_safely",
}


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "fixture root must be an object"
    return data, None


def transition_failures(states: list[str]) -> list[str]:
    failures: list[str] = []
    if not states:
        return ["missing_state_sequence"]
    for previous, current in zip(states, states[1:]):
        allowed = ALLOWED_TRANSITIONS.get(previous)
        if allowed is None:
            failures.append(f"unknown_state:{previous}")
            continue
        if current not in allowed:
            failures.append(f"invalid_transition:{previous}->{current}")
    if states[-1] not in TERMINAL_STATUS:
        failures.append(f"non_terminal_final_state:{states[-1]}")
    return failures


def event_kinds(case: dict[str, Any]) -> set[str]:
    return {
        str(event.get("kind"))
        for event in case.get("events", [])
        if isinstance(event, dict) and event.get("kind")
    }


def has_unsafe_execution(events: list[dict[str, Any]]) -> bool:
    for event in events:
        if event.get("unsafe_execution") is True:
            return True
        if event.get("kind") != "dangerous_action":
            continue
        if event.get("approved") is True:
            continue
        if event.get("status") in {"blocked", "skipped"}:
            continue
        return True
    return False


def observed_recovery_accuracy(chaos: set[str], states: list[str], kinds: set[str]) -> str:
    if chaos & SAFE_BLOCK_CHAOS and states and states[-1] == "BLOCKED_SAFELY":
        return "safe_block"
    if "runtime restart" in chaos and "approval_rehydrated" in kinds:
        return "approval_preserved"
    if "plugin failure" in chaos and "plugin_isolated" in kinds:
        return "isolated"
    if {"checkpoint_restored", "partial_replay", "workflow_rehydrated"} & kinds:
        return "restored"
    return "missing"


def has_observability_trace(events: list[dict[str, Any]]) -> bool:
    if not events:
        return False
    required = {"trace_id", "state", "kind"}
    return all(required.issubset(event) for event in events)


def simulate_case(case: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    case_id = str(case.get("id", "unnamed"))
    chaos = set(case.get("chaos", [])) if isinstance(case.get("chaos"), list) else set()
    states = [str(state) for state in case.get("state_sequence", [])] if isinstance(case.get("state_sequence"), list) else []
    events = [event for event in case.get("events", []) if isinstance(event, dict)] if isinstance(case.get("events"), list) else []
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    kinds = event_kinds(case)

    failures.extend(transition_failures(states))
    if not chaos:
        failures.append("missing_chaos")
    if not events:
        failures.append("missing_events")

    unsafe_execution = has_unsafe_execution(events)
    terminal_status = TERMINAL_STATUS.get(states[-1], "invalid") if states else "missing"
    workflow_survived = terminal_status in {"completed", "blocked_safely"} and not unsafe_execution
    deterministic_stability = not any(failure.startswith(("invalid_transition", "unknown_state", "non_terminal")) for failure in failures)
    observability_trace = has_observability_trace(events)
    approval_integrity = not unsafe_execution
    plugin_isolated = "plugin failure" not in chaos or "plugin_isolated" in kinds
    resume_success = bool(
        workflow_survived
        and chaos & RECOVERY_REQUIRED_CHAOS
        and (
            {"checkpoint_restored", "approval_rehydrated", "partial_replay", "plugin_isolated", "safe_block", "workflow_rehydrated", "memory_quarantine"}
            & kinds
        )
    )
    recovery_accuracy = observed_recovery_accuracy(chaos, states, kinds)
    workflow_continuity_score = round(
        (
            (0.25 if workflow_survived else 0)
            + (0.20 if approval_integrity else 0)
            + (0.20 if deterministic_stability else 0)
            + (0.15 if observability_trace else 0)
            + (0.10 if resume_success else 0)
            + (0.10 if plugin_isolated else 0)
        ),
        2,
    )
    observed = {
        "terminal_status": terminal_status,
        "workflow_survived": workflow_survived,
        "resume_success": resume_success,
        "recovery_accuracy": recovery_accuracy,
        "approval_integrity": approval_integrity,
        "plugin_isolated": plugin_isolated,
        "deterministic_stability": deterministic_stability,
        "observability_trace": observability_trace,
        "unsafe_execution": unsafe_execution,
        "workflow_continuity_score": workflow_continuity_score,
    }

    for key in (
        "terminal_status",
        "workflow_survived",
        "resume_success",
        "recovery_accuracy",
        "approval_integrity",
        "plugin_isolated",
        "deterministic_stability",
        "observability_trace",
        "unsafe_execution",
    ):
        if expected.get(key) != observed[key]:
            failures.append(f"{key}:{observed[key]!r}!=expected:{expected.get(key)!r}")

    score_min = expected.get("workflow_continuity_score_min")
    if not isinstance(score_min, (int, float)):
        failures.append("workflow_continuity_score_min_missing")
    elif workflow_continuity_score < float(score_min):
        failures.append(f"workflow_continuity_score:{workflow_continuity_score}<minimum:{score_min}")

    return {
        "id": case_id,
        "passed": not failures,
        "chaos": sorted(chaos),
        "observed": observed,
        "expected": expected,
        "failures": failures,
    }


def metric_value(name: str, cases: list[dict[str, Any]]) -> float:
    if not cases:
        return 0.0

    if name == "Resume Success Rate":
        applicable = [case for case in cases if set(case["chaos"]) & RECOVERY_REQUIRED_CHAOS]
        if not applicable:
            return 0.0
        return sum(1 for case in applicable if case["observed"]["resume_success"]) / len(applicable)
    if name == "Workflow Survival Rate":
        return sum(1 for case in cases if case["observed"]["workflow_survived"]) / len(cases)
    if name == "Recovery Accuracy":
        return sum(1 for case in cases if case["observed"]["recovery_accuracy"] in {"restored", "approval_preserved", "isolated", "safe_block"}) / len(cases)
    if name == "Approval Integrity":
        return sum(1 for case in cases if case["observed"]["approval_integrity"]) / len(cases)
    if name == "Deterministic Stability":
        return sum(1 for case in cases if case["observed"]["deterministic_stability"]) / len(cases)
    if name == "Workflow Continuity Score":
        return sum(case["observed"]["workflow_continuity_score"] for case in cases) / len(cases)
    return 0.0


def invalid_fixture(fixture_path: Path, detail: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "fixture": str(fixture_path),
        "passed": False,
        "error_type": "invalid_fixture",
        "summary": {"cases": 0, "passed": 0, "failed": 1},
        "metrics": {},
        "cases": [],
        "failures": [detail],
    }


def evaluate(fixture_path: Path) -> dict[str, Any]:
    fixture, error = load_json(fixture_path)
    if fixture is None:
        return invalid_fixture(fixture_path, error or "fixture_parse_failed")

    cases_raw = fixture.get("cases")
    if fixture.get("schema_version") != 1 or fixture.get("round") != 2 or not isinstance(cases_raw, list) or not cases_raw:
        return invalid_fixture(fixture_path, "fixture must have schema_version=1, round=2, and non-empty cases array")
    if any(not isinstance(case, dict) for case in cases_raw):
        return invalid_fixture(fixture_path, "fixture cases must be objects")

    chaos = set(fixture.get("chaos_requirements", [])) if isinstance(fixture.get("chaos_requirements"), list) else set()
    metrics = set(fixture.get("success_metrics", [])) if isinstance(fixture.get("success_metrics"), list) else set()
    thresholds = fixture.get("metric_thresholds") if isinstance(fixture.get("metric_thresholds"), dict) else {}
    if not REQUIRED_CHAOS.issubset(chaos):
        return invalid_fixture(fixture_path, "fixture must include all required chaos requirements")
    if not REQUIRED_METRICS.issubset(metrics):
        return invalid_fixture(fixture_path, "fixture must include all required persistent workflow success metrics")

    cases = [simulate_case(case) for case in cases_raw]
    covered_chaos = {name for case in cases for name in case["chaos"]}
    coverage_failures = sorted(REQUIRED_CHAOS - covered_chaos)
    metric_results = {name: round(metric_value(name, cases), 3) for name in sorted(REQUIRED_METRICS)}
    metric_failures = [
        f"{name}:{value}<threshold:{thresholds.get(name)}"
        for name, value in metric_results.items()
        if not isinstance(thresholds.get(name), (int, float)) or value < float(thresholds[name])
    ]
    failed = [case for case in cases if not case["passed"]]

    failures: list[Any] = [
        {"id": case["id"], "failures": case["failures"]}
        for case in failed
    ]
    failures.extend(f"missing_chaos_case:{name}" for name in coverage_failures)
    failures.extend(metric_failures)

    return {
        "schema_version": 1,
        "fixture": str(fixture_path),
        "passed": not failures,
        "summary": {
            "cases": len(cases),
            "passed": len(cases) - len(failed),
            "failed": len(failures),
            "chaos_covered": len(covered_chaos & REQUIRED_CHAOS),
        },
        "metrics": metric_results,
        "cases": cases,
        "failures": failures,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(repo_root / "core" / "evaluations" / "persistent-workflow-chaos.json"))
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    result = evaluate(Path(args.fixture).expanduser().resolve())
    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(("PASS" if result["passed"] else "FAIL") + ": persistent workflow chaos check")
        summary = result["summary"]
        print(
            f"cases={summary['cases']} passed={summary['passed']} "
            f"failed={summary['failed']} chaos_covered={summary['chaos_covered']}"
        )
        for name, value in result["metrics"].items():
            print(f"{name}: {value}")
        for failure in result["failures"]:
            print(f"- {failure}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
