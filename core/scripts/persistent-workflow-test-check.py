#!/usr/bin/env python3
"""Validate the persistent workflow test strategy contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_CATEGORIES = {
    "workflow_durability",
    "resume_and_recovery",
    "human_approval_integrity",
    "workflow_determinism",
    "workflow_observability",
    "plugin_isolation",
    "long_running_operational",
}
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
REQUIRED_ANTI_GOALS = {
    "raw token speed",
    "prompt throughput",
    "benchmark scoring",
    "superficial latency metrics",
}
REQUIRED_DOC_TERMS = [
    "Persistent AI Workforce System",
    "long-running operational workflow system",
    "Can this AI continue working tomorrow?",
    "Can the workflow survive and continue safely?",
    "Workflow durability",
    "Resume and recovery",
    "Human approval integrity",
    "Workflow determinism",
    "Workflow observability",
    "Plugin isolation",
    "Long-running operational tests",
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def finding(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def all_evidence_paths_exist(root: Path, fixture: dict) -> bool:
    categories = fixture.get("test_categories", {})
    if not isinstance(categories, dict):
        return False

    for category in categories.values():
        if not isinstance(category, dict):
            return False
        evidence = category.get("round_1_evidence", [])
        if not evidence:
            return False
        for rel_path in evidence:
            if not isinstance(rel_path, str) or not (root / rel_path).exists():
                return False
    return True


def evaluate(root: Path) -> dict:
    root = root.resolve()
    doc = read_text(root / "docs/persistent-workflow-test-strategy.md")
    fixture = read_json(root / "core/evaluations/persistent-workflow-test-strategy.json")

    categories = fixture.get("test_categories", {})
    category_names = set(categories) if isinstance(categories, dict) else set()
    chaos = set(fixture.get("chaos_requirements", [])) if isinstance(fixture.get("chaos_requirements"), list) else set()
    metrics = set(fixture.get("success_metrics", [])) if isinstance(fixture.get("success_metrics"), list) else set()
    anti_goals = set(fixture.get("anti_goals", [])) if isinstance(fixture.get("anti_goals"), list) else set()
    commands = fixture.get("round_1_commands", []) if isinstance(fixture.get("round_1_commands"), list) else []

    checks = [
        finding(
            "doc_exists",
            bool(doc),
            "persistent workflow test strategy documentation must exist.",
        ),
        finding(
            "doc_core_terms",
            all(term in doc for term in REQUIRED_DOC_TERMS),
            "documentation must preserve the persistent workflow testing philosophy.",
        ),
        finding(
            "identity_and_objective",
            fixture.get("system_identity") == "Persistent AI Workforce System"
            and fixture.get("round") == 1
            and all(term in fixture.get("objective", []) for term in [
                "workflow durability",
                "execution continuity",
                "resumability",
                "operational safety",
                "deterministic orchestration",
            ]),
            "fixture must encode round 1 objective and system identity.",
        ),
        finding(
            "critical_questions",
            "Can this AI continue working tomorrow?" in fixture.get("critical_questions", []),
            "fixture must include the most important persistent workflow validation question.",
        ),
        finding(
            "category_coverage",
            REQUIRED_CATEGORIES.issubset(category_names),
            "all required persistent workflow test categories must be represented.",
        ),
        finding(
            "evidence_paths",
            all_evidence_paths_exist(root, fixture),
            "each category must point at existing round 1 evidence artifacts.",
        ),
        finding(
            "chaos_coverage",
            REQUIRED_CHAOS.issubset(chaos),
            "chaos engineering requirements must include interruption, persistence, plugin, token, memory, and infrastructure failures.",
        ),
        finding(
            "metric_coverage",
            REQUIRED_METRICS.issubset(metrics),
            "operational success metrics must be persistent workflow metrics.",
        ),
        finding(
            "anti_goal_coverage",
            REQUIRED_ANTI_GOALS.issubset(anti_goals),
            "strategy must explicitly deprioritize superficial throughput and benchmark metrics.",
        ),
        finding(
            "round_1_commands",
            all(isinstance(command, str) and command.startswith("python3 core/scripts/") for command in commands)
            and any("workflow-replay-check.py" in command for command in commands)
            and any("retry-chaos-check.py" in command for command in commands)
            and any("framework-review-check.py" in command for command in commands),
            "round 1 command set must connect strategy, replay, chaos, and framework checks.",
        ),
    ]

    failed = [check for check in checks if not check["passed"]]
    return {
        "passed": not failed,
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
        },
        "checks": checks,
        "failures": failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    result = evaluate(Path(args.root))
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        status = "PASS" if result["passed"] else "FAIL"
        summary = result["summary"]
        print(
            f"{status}: persistent workflow test strategy check "
            f"checks={summary['checks']} passed={summary['passed']} failed={summary['failed']}"
        )
        for failure in result["failures"]:
            print(f"FAIL: {failure['name']} - {failure['detail']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
