#!/usr/bin/env python3
"""Replay retry chaos fixtures against deterministic recovery rules.

Inputs:
  --fixture PATH       defaults to core/evaluations/retry-chaos.json
  --project-root PATH  repository checkout; defaults to this script's repo root

Outputs:
  text or JSON report with retry counters, blockers, and mismatch details.

Exit codes:
  0 - every chaos case matched the golden fixture
  1 - one or more replay comparisons failed
  2 - fixture or arguments are invalid

Example:
  python3 core/scripts/retry-chaos-check.py --format json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


STATUS_COMPLETED_RE = re.compile(r"^STATUS\s*:\s*completed\b", re.I | re.M)
STATUS_PLAN_READY_RE = re.compile(r"^STATUS\s*:\s*plan_ready\b", re.I | re.M)
STATUS_BLOCKED_RE = re.compile(r"^STATUS\s*:\s*BLOCKED\b", re.I | re.M)


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "fixture root must be an object"
    return payload, None


def reviewer_decision(
    repo_root: Path,
    response: str,
    review_mode: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    command = [
        sys.executable,
        str(repo_root / "core" / "scripts" / "reviewer-loop-decision.py"),
        "--format",
        "json",
    ]
    if review_mode:
        command.extend(["--review-mode", review_mode])
    proc = subprocess.run(
        command,
        input=response,
        text=True,
        capture_output=True,
    )
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:
        return None, f"reviewer_decision_parse_failed:{exc}"
    if proc.returncode not in {0, 1}:
        return None, f"reviewer_decision_failed:{proc.returncode}:{proc.stderr.strip()}"
    return payload, None


def status_line(response: str) -> str:
    if STATUS_COMPLETED_RE.search(response):
        return "completed"
    if STATUS_PLAN_READY_RE.search(response):
        return "plan_ready"
    if STATUS_BLOCKED_RE.search(response):
        return "blocked"
    return "missing"


def simulate_case(case: dict[str, Any], budgets: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    max_crash_retries = int(budgets.get("max_crash_retries", 5))
    max_validation_retries = int(budgets.get("max_validation_retries", 3))
    max_reviewer_retries = int(
        budgets.get("max_reviewer_retries", budgets.get("max_reviewer_contract_retries", 2))
    )
    max_reviewer_contract_retries = int(budgets.get("max_reviewer_contract_retries", 2))
    max_token_resumes = int(budgets.get("max_token_truncation_resumes", 1))

    observed: dict[str, Any] = {
        "final_status": "incomplete",
        "blocked_by": [],
        "invocations": 0,
        "crash_failures": 0,
        "token_resumes": 0,
        "validation_retries": 0,
        "reviewer_retries": 0,
        "reviewer_contract_retries": 0,
        "retry_reasons": [],
        "directives": [],
    }
    failures: list[str] = []

    events = case.get("events")
    if not isinstance(events, list) or not events:
        return {
            "id": str(case.get("id", "unnamed")),
            "passed": False,
            "observed": observed,
            "expected": case.get("expected") or {},
            "failures": ["events must be a non-empty array"],
        }

    for index, raw_event in enumerate(events):
        if not isinstance(raw_event, dict):
            failures.append(f"event_not_object:{index}")
            continue

        observed["invocations"] += 1
        kind = raw_event.get("kind")
        response = str(raw_event.get("response") or "")

        if kind == "reviewer_result":
            review_mode = raw_event.get("review_mode")
            decision, error = reviewer_decision(
                repo_root,
                response,
                str(review_mode) if review_mode else None,
            )
            if error:
                failures.append(error)
                observed["final_status"] = "blocked"
                observed["blocked_by"] = ["reviewer_decision_failed"]
                break

            action = decision.get("action")
            if action == "approve":
                observed["final_status"] = "completed"
                break
            if action == "retry":
                reason = str(decision.get("reason") or "reviewer_retry")
                observed["retry_reasons"].append(reason)
                if decision.get("directive"):
                    observed["directives"].append(decision["directive"])

                if decision.get("retry_target") == "reviewer":
                    observed["reviewer_retries"] += 1
                    if reason == "review_contract_invalid":
                        observed["reviewer_contract_retries"] += 1

                    if (
                        observed["reviewer_retries"] > max_reviewer_retries
                        or observed["reviewer_contract_retries"] > max_reviewer_contract_retries
                    ):
                        observed["final_status"] = "blocked"
                        observed["blocked_by"] = [
                            "review_contract_loop_exhausted"
                            if reason == "review_contract_invalid"
                            else "reviewer_loop_exhausted"
                        ]
                        break

                    continue

                observed["validation_retries"] += 1
                if observed["validation_retries"] > max_validation_retries:
                    observed["final_status"] = "blocked"
                    observed["blocked_by"] = ["quality_loop_exhausted"]
                    break

        elif kind != "agent_result":
            failures.append(f"unknown_event_kind:{kind!r}")
            continue

        else:
            line = status_line(response)
            if line == "completed":
                observed["final_status"] = "completed"
                break
            if line == "plan_ready":
                observed["final_status"] = "plan_ready"
                break
            if line == "blocked":
                observed["final_status"] = "blocked"
                observed["blocked_by"] = ["agent_blocked"]
                break

            host_status = str(raw_event.get("host_status") or "error")
            if host_status == "completed" and observed["token_resumes"] < max_token_resumes:
                observed["token_resumes"] += 1
                observed["retry_reasons"].append("token_truncation")
                continue
            if host_status == "blocked":
                observed["final_status"] = "blocked"
                observed["blocked_by"] = ["host_blocked"]
                break
            if host_status == "cancelled":
                observed["final_status"] = "blocked"
                observed["blocked_by"] = ["cancelled"]
                break

            observed["crash_failures"] += 1
            observed["retry_reasons"].append("crash")
            if observed["crash_failures"] > max_crash_retries:
                observed["final_status"] = "blocked"
                observed["blocked_by"] = ["agent_crashed_after_retry_budget"]
                break

    expected = case.get("expected") or {}
    for key in (
        "final_status",
        "blocked_by",
        "invocations",
        "crash_failures",
        "token_resumes",
        "validation_retries",
        "reviewer_retries",
        "reviewer_contract_retries",
        "retry_reasons",
    ):
        if key in expected and expected.get(key) != observed.get(key):
            failures.append(f"{key}:{observed.get(key)!r}!=expected:{expected.get(key)!r}")

    return {
        "id": str(case.get("id", "unnamed")),
        "passed": not failures,
        "observed": observed,
        "expected": expected,
        "failures": failures,
    }


def evaluate(repo_root: Path, fixture_path: Path) -> dict[str, Any]:
    fixture, error = load_json(fixture_path)
    if fixture is None:
        return invalid_fixture(fixture_path, error or "fixture_parse_failed")

    budgets = fixture.get("budgets")
    cases_raw = fixture.get("cases")
    if fixture.get("schema_version") != 1 or not isinstance(budgets, dict) or not isinstance(cases_raw, list) or not cases_raw:
        return invalid_fixture(fixture_path, "fixture must have schema_version=1, budgets object, and non-empty cases array")
    if any(not isinstance(case, dict) for case in cases_raw):
        return invalid_fixture(fixture_path, "fixture cases must be objects")

    cases = [simulate_case(case, budgets, repo_root) for case in cases_raw]
    failed = [case for case in cases if not case["passed"]]
    return {
        "schema_version": 1,
        "fixture": str(fixture_path),
        "passed": not failed,
        "summary": {
            "cases": len(cases),
            "passed": len(cases) - len(failed),
            "failed": len(failed),
        },
        "cases": cases,
        "failures": [
            {"id": case["id"], "failures": case["failures"]}
            for case in failed
        ],
    }


def invalid_fixture(fixture_path: Path, detail: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "fixture": str(fixture_path),
        "passed": False,
        "error_type": "invalid_fixture",
        "summary": {"cases": 0, "passed": 0, "failed": 1},
        "cases": [],
        "failures": [detail],
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(repo_root))
    parser.add_argument("--fixture", default=str(repo_root / "core" / "evaluations" / "retry-chaos.json"))
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    result = evaluate(root, Path(args.fixture).expanduser().resolve())
    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(("PASS" if result["passed"] else "FAIL") + ": retry chaos check")
        summary = result["summary"]
        print(f"cases={summary['cases']} passed={summary['passed']} failed={summary['failed']}")
        for failure in result["failures"]:
            print(f"- {failure}")

    if result["passed"]:
        return 0
    if result.get("error_type") == "invalid_fixture":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
