#!/usr/bin/env python3
"""Validate the machine-readable agent capability manifest.

Inputs:
  --project-root PATH   repository checkout; defaults to this script's repo root
  --manifest PATH       manifest path; defaults to core/policies/agent-capabilities.json

Outputs:
  text or JSON report with per-control pass/fail details.

Exit codes:
  0 when every capability control passes
  1 when one or more controls fail
  2 when the manifest or repository cannot be parsed

Example:
  python3 core/scripts/agent-capability-check.py --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "role",
    "model_tier",
    "reasoning_tier",
    "allowed_capabilities",
    "denied_capabilities",
    "may_delegate",
    "may_implement",
    "may_modify_production_state",
    "may_mutate_workflow_state",
    "may_execute_destructive",
    "destructive_requires_approval",
}

VALID_ROLES = {
    "orchestrator",
    "planner",
    "worker",
    "reviewer",
    "resolver",
    "devops",
    "issuer",
    "support",
    "readonly",
    "component",
}
CUSTOM_PROFILE_FORBIDDEN_ROLES = {"orchestrator", "planner", "component"}

VALID_MODEL_TIERS = {"xhigh", "high", "medium", "cheap"}
VALID_REASONING_TIERS = {"xhigh", "deep", "balanced", "light"}
BOOLEAN_FIELDS = {
    "may_delegate",
    "may_implement",
    "may_modify_production_state",
    "may_mutate_workflow_state",
    "may_execute_destructive",
    "destructive_requires_approval",
}


def check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "detail": detail,
    }


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, str(exc)


def agent_markdown_files(root: Path) -> set[str]:
    agents_dir = root / "core" / "agents"
    if not agents_dir.is_dir():
        return set()
    return {
        path.stem
        for path in agents_dir.glob("*.md")
        if path.is_file()
    }


def frontmatter_reasoning_tier(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    head = "\n".join(text.splitlines()[:80])
    match = re.search(r"^reasoning_tier:\s*([a-zA-Z_-]+)\s*$", head, re.MULTILINE)
    return match.group(1) if match else None


def validate_agent_shape(name: str, data: Any) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return [check(f"{name}.shape", False, "Agent entry must be an object.")]

    missing = sorted(REQUIRED_FIELDS - set(data))
    checks.append(check(f"{name}.required_fields", not missing, f"missing={missing}"))

    extra = sorted(set(data) - (REQUIRED_FIELDS | {"notes"}))
    checks.append(check(f"{name}.no_extra_fields", not extra, f"extra={extra}"))

    checks.append(
        check(
            f"{name}.role",
            data.get("role") in VALID_ROLES,
            f"role={data.get('role')!r}",
        )
    )
    checks.append(
        check(
            f"{name}.model_tier",
            data.get("model_tier") in VALID_MODEL_TIERS,
            f"model_tier={data.get('model_tier')!r}",
        )
    )
    checks.append(
        check(
            f"{name}.reasoning_tier",
            data.get("reasoning_tier") in VALID_REASONING_TIERS,
            f"reasoning_tier={data.get('reasoning_tier')!r}",
        )
    )

    for field in BOOLEAN_FIELDS:
        checks.append(
            check(
                f"{name}.{field}",
                isinstance(data.get(field), bool),
                f"{field}={data.get(field)!r}",
            )
        )

    for field in ("allowed_capabilities", "denied_capabilities"):
        value = data.get(field)
        valid = (
            isinstance(value, list)
            and bool(value)
            and all(isinstance(item, str) and item for item in value)
            and len(value) == len(set(value))
        )
        checks.append(check(f"{name}.{field}", valid, f"count={len(value) if isinstance(value, list) else 'invalid'}"))

    allowed = set(data.get("allowed_capabilities") or [])
    denied = set(data.get("denied_capabilities") or [])
    overlap = sorted(allowed & denied)
    checks.append(check(f"{name}.no_capability_overlap", not overlap, f"overlap={overlap}"))
    return checks


def validate_role_policy(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    role = data.get("role")
    allowed = set(data.get("allowed_capabilities") or [])
    denied = set(data.get("denied_capabilities") or [])
    checks: list[dict[str, Any]] = []

    if role in {"orchestrator", "planner"}:
        checks.append(
            check(
                f"{name}.planner_orchestrator_boundary",
                data.get("may_delegate") is True
                and data.get("may_implement") is False
                and data.get("may_modify_production_state") is False
                and data.get("may_execute_destructive") is False,
                "orchestrators and planners delegate, but do not implement or execute destructive commands.",
            )
        )

    if role == "worker":
        checks.append(
            check(
                f"{name}.worker_boundary",
                data.get("may_delegate") is False
                and data.get("may_implement") is True
                and data.get("may_mutate_workflow_state") is False
                and data.get("may_execute_destructive") is False,
                "workers implement focused work without delegation, workflow-state mutation, or destructive execution.",
            )
        )

    if role in {"readonly", "support", "issuer"}:
        checks.append(
            check(
                f"{name}.non_implementer_boundary",
                data.get("may_delegate") is False
                and data.get("may_implement") is False
                and data.get("may_modify_production_state") is False
                and data.get("may_mutate_workflow_state") is False
                and data.get("may_execute_destructive") is False,
                "read-only, support, and issuer roles must not mutate production or workflow state.",
            )
        )

    if role == "reviewer":
        checks.append(
            check(
                f"{name}.reviewer_read_only_boundary",
                data.get("may_delegate") is False
                and data.get("may_implement") is False
                and data.get("may_modify_production_state") is False
                and data.get("may_mutate_workflow_state") is False
                and data.get("may_execute_destructive") is False
                and {"read_file", "read_only"}.issubset(allowed)
                and {"edit_file", "destructive_command"}.issubset(denied),
                "reviewer must be read-only and explicitly denied edit/destructive authority.",
            )
        )

    if role == "devops":
        checks.append(
            check(
                f"{name}.devops_approval_boundary",
                data.get("may_delegate") is False
                and data.get("may_implement") is False
                and data.get("may_mutate_workflow_state") is False
                and (
                    data.get("may_execute_destructive") is False
                    or data.get("destructive_requires_approval") is True
                )
                and "destructive_command_without_approval" in denied,
                "devops destructive authority requires orchestrator approval.",
            )
        )

    if role == "resolver":
        checks.append(
            check(
                f"{name}.resolver_boundary",
                data.get("may_delegate") is False
                and data.get("may_implement") is True
                and data.get("may_mutate_workflow_state") is False
                and data.get("may_execute_destructive") is False,
                "resolver may edit conflicts, but cannot delegate, mutate workflow state, or run destructive commands.",
            )
        )

    if data.get("may_execute_destructive") is False:
        checks.append(
            check(
                f"{name}.no_destructive_allowance",
                "destructive_command" not in allowed
                and "destructive_command_without_approval" not in allowed,
                "non-destructive roles must not allow destructive capabilities.",
            )
        )

    return checks


def validate_custom_profiles(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    profiles = manifest.get("custom_profiles")
    default_profile = manifest.get("default_custom_profile")

    checks.append(
        check(
            "custom_profiles.object",
            isinstance(profiles, dict) and bool(profiles),
            "custom_profiles must define at least one safe profile.",
        )
    )
    if not isinstance(profiles, dict):
        return checks

    checks.append(
        check(
            "custom_profiles.default_exists",
            isinstance(default_profile, str) and default_profile in profiles,
            f"default_custom_profile={default_profile!r}",
        )
    )

    default_data = profiles.get(default_profile) if isinstance(default_profile, str) else None
    checks.append(
        check(
            "custom_profiles.default_safe_worker",
            isinstance(default_data, dict)
            and default_data.get("role") == "worker"
            and default_data.get("may_delegate") is False
            and default_data.get("may_execute_destructive") is False
            and default_data.get("may_mutate_workflow_state") is False
            and "destructive_command" in set(default_data.get("denied_capabilities") or []),
            "default custom profile must be a non-delegating, non-destructive worker.",
        )
    )

    for profile_name in sorted(profiles):
        data = profiles.get(profile_name)
        checks.extend(validate_agent_shape(f"profile.{profile_name}", data))
        if not isinstance(data, dict):
            continue

        checks.extend(validate_role_policy(f"profile.{profile_name}", data))
        checks.append(
            check(
                f"profile.{profile_name}.no_recursive_orchestrator_role",
                data.get("role") not in CUSTOM_PROFILE_FORBIDDEN_ROLES
                and data.get("may_mutate_workflow_state") is False,
                "custom profiles must not grant orchestrator/planner/component or workflow-state authority.",
            )
        )

    return checks


def evaluate(root: Path, manifest_path: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    schema_path = root / "core" / "schemas" / "agent-capabilities.schema.json"
    checks: list[dict[str, Any]] = []

    schema_payload, schema_error = read_json(schema_path)
    checks.append(
        check(
            "schema.present",
            schema_payload is not None and schema_error is None,
            f"path={schema_path}",
        )
    )
    checks.append(
        check(
            "schema.version_const",
            isinstance(schema_payload, dict)
            and schema_payload.get("properties", {}).get("schema_version", {}).get("const") == 1,
            "schema_version must be pinned to 1.",
        )
    )

    manifest, error = read_json(manifest_path)
    if manifest is None:
        checks.append(check("manifest.parse", False, error or "unable to parse manifest"))
        return build_result(root, manifest_path, checks)
    checks.append(check("manifest.parse", True, f"path={manifest_path}"))

    agents = manifest.get("agents")
    checks.append(check("manifest.schema_version", manifest.get("schema_version") == 1, "schema_version must be 1."))
    checks.append(check("manifest.agents_object", isinstance(agents, dict) and bool(agents), "agents must be a non-empty object."))
    checks.extend(validate_custom_profiles(manifest))
    if not isinstance(agents, dict):
        return build_result(root, manifest_path, checks)

    md_agents = agent_markdown_files(root)
    manifest_agents = set(agents)
    missing = sorted(md_agents - manifest_agents)
    extra = sorted(manifest_agents - md_agents)
    checks.append(check("manifest.covers_agent_files", not missing, f"missing={missing}"))
    checks.append(check("manifest.no_unknown_agents", not extra, f"extra={extra}"))

    for name in sorted(manifest_agents):
        data = agents.get(name)
        checks.extend(validate_agent_shape(name, data))
        if not isinstance(data, dict):
            continue

        checks.extend(validate_role_policy(name, data))
        frontmatter_tier = frontmatter_reasoning_tier(root / "core" / "agents" / f"{name}.md")
        checks.append(
            check(
                f"{name}.frontmatter_reasoning_consistency",
                frontmatter_tier is None or frontmatter_tier == data.get("reasoning_tier"),
                f"frontmatter={frontmatter_tier!r} manifest={data.get('reasoning_tier')!r}",
            )
        )

    model_tiers = {data.get("model_tier") for data in agents.values() if isinstance(data, dict)}
    top_count = sum(1 for data in agents.values() if isinstance(data, dict) and data.get("model_tier") == "xhigh")
    cheap_count = sum(1 for data in agents.values() if isinstance(data, dict) and data.get("model_tier") == "cheap")
    checks.append(
        check(
            "routing.cost_aware_model_tiers",
            {"xhigh", "high", "medium", "cheap"}.issubset(model_tiers)
            and top_count < len(agents)
            and cheap_count >= 2,
            f"tiers={sorted(tier for tier in model_tiers if tier)} xhigh={top_count} cheap={cheap_count}",
        )
    )

    reasoning_tiers = {data.get("reasoning_tier") for data in agents.values() if isinstance(data, dict)}
    checks.append(
        check(
            "routing.reasoning_tier_distribution",
            {"xhigh", "deep", "balanced", "light"}.issubset(reasoning_tiers),
            f"tiers={sorted(tier for tier in reasoning_tiers if tier)}",
        )
    )

    return build_result(root, manifest_path, checks)


def build_result(root: Path, manifest_path: Path, checks: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [item for item in checks if not item["passed"]]
    return {
        "schema_version": 1,
        "project_root": str(root),
        "manifest": str(manifest_path),
        "passed": not failures,
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failures),
            "failed": len(failures),
        },
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(repo_root))
    parser.add_argument("--manifest", default="")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    manifest = Path(args.manifest).expanduser().resolve() if args.manifest else root / "core" / "policies" / "agent-capabilities.json"
    result = evaluate(root, manifest)

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        summary = result["summary"]
        print(("PASS" if result["passed"] else "FAIL") + ": agent capability check")
        print(f"checks={summary['checks']} passed={summary['passed']} failed={summary['failed']}")
        for failure in result["failures"]:
            print(f"- {failure['name']}: {failure['detail']}")

    if result["passed"]:
        return 0
    return 1 if any(item["name"] != "manifest.parse" for item in result["failures"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
