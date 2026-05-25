#!/usr/bin/env python3
"""Validate the durable workflow architecture contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_ISSUES = {"107", "108", "109", "110", "111", "112", "113"}
REQUIRED_STATES = {
    "PLANNING",
    "CHECKPOINTING",
    "WAITING_APPROVAL",
    "EXECUTING",
    "REVIEWING",
    "RECOVERING",
    "RESUMING",
    "ROLLING_BACK",
    "COMPLETED",
    "FAILED",
}
REQUIRED_ROLES = {"planner", "designer", "backend", "frontend", "reviewer", "devops"}
REQUIRED_SCHEMA_PROPERTIES = {
    "workflow_id",
    "task_id",
    "current_state",
    "lifecycle",
    "checkpoint",
    "resume",
    "roles",
    "approval",
    "observability",
    "extension_policy",
    "memory_refs",
}
REQUIRED_DOC_TERMS = [
    "Persistent AI Workforce System",
    "long-running durable AI execution",
    "workflow durability",
    "operational continuity",
    "resumable workflows",
    "human-supervised execution",
    "durable orchestration",
    "Roles are more important than agent quantity.",
    "Extensibility must never compromise workflow durability.",
    "Long-running AI workflows must survive interruption and continue execution safely.",
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


def evaluate(root: Path) -> dict:
    root = root.resolve()
    doc = read_text(root / "docs/durable-workflow-architecture.md")
    schema = read_json(root / "core/schemas/durable-workflow.schema.json")
    fixture = read_json(root / "core/evaluations/durable-workflow-architecture.json")

    schema_props = set(schema.get("properties", {}))
    schema_required = set(schema.get("required", []))
    state_enum = set(
        schema.get("properties", {})
        .get("current_state", {})
        .get("enum", [])
    )
    issues = fixture.get("issues", {}) if isinstance(fixture.get("issues"), dict) else {}
    fixture_states = set(
        fixture.get("state_machine", {}).get("states", [])
        if isinstance(fixture.get("state_machine"), dict)
        else []
    )
    transitions = (
        fixture.get("state_machine", {}).get("transitions", [])
        if isinstance(fixture.get("state_machine"), dict)
        else []
    )
    roles = set(fixture.get("roles", [])) if isinstance(fixture.get("roles"), list) else set()

    checks = [
        finding(
            "doc_exists",
            bool(doc),
            "durable workflow architecture documentation must exist.",
        ),
        finding(
            "doc_core_terms",
            all(term in doc for term in REQUIRED_DOC_TERMS),
            "documentation must preserve Persistent AI Workforce direction and key principles.",
        ),
        finding(
            "issue_coverage",
            REQUIRED_ISSUES.issubset(set(issues)) and all(f"#{issue}" in doc for issue in REQUIRED_ISSUES),
            "issues #107-#113 must be mapped to architecture surfaces.",
        ),
        finding(
            "state_machine_states",
            REQUIRED_STATES.issubset(fixture_states) and REQUIRED_STATES.issubset(state_enum),
            "fixture and schema must define the durable workflow state vocabulary.",
        ),
        finding(
            "transition_coverage",
            all(isinstance(pair, list) and len(pair) == 2 for pair in transitions)
            and ["RECOVERING", "RESUMING"] in transitions
            and ["WAITING_APPROVAL", "CHECKPOINTING"] in transitions,
            "fixture must define checkpoint, approval, recovery, and resume transitions.",
        ),
        finding(
            "schema_contract",
            REQUIRED_SCHEMA_PROPERTIES.issubset(schema_props)
            and REQUIRED_SCHEMA_PROPERTIES.issubset(schema_required)
            and schema.get("additionalProperties") is False,
            "schema must require the durable workflow protocol surfaces.",
        ),
        finding(
            "role_contracts",
            REQUIRED_ROLES.issubset(roles)
            and all(role in doc for role in ["Planner", "Designer", "Backend", "Frontend", "Reviewer", "DevOps"]),
            "role-oriented execution contracts must include canonical roles.",
        ),
        finding(
            "approval_contract",
            all(term in doc for term in ["AI proposes", "Human approves", "AI executes"])
            and "git push" in json.dumps(fixture),
            "human-supervised approval contract must be durable and explicit.",
        ),
        finding(
            "observability_contract",
            len(fixture.get("continuity_metrics", [])) >= 10
            and "workflow continuity observability" in doc.lower(),
            "continuity observability must define operational recovery metrics.",
        ),
        finding(
            "extension_safety_contract",
            len(fixture.get("extension_denials", [])) >= 5
            and "capability registry" in json.dumps(fixture)
            and "approval guarantees" in doc,
            "plugin/runtime extension architecture must deny unsafe execution paths.",
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
            f"{status}: durable workflow architecture check "
            f"checks={summary['checks']} passed={summary['passed']} failed={summary['failed']}"
        )
        for failure in result["failures"]:
            print(f"FAIL: {failure['name']} - {failure['detail']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
