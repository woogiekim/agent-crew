#!/usr/bin/env python3
"""Validate planned runtime stages against the agent capability manifest.

Inputs:
  --pipeline PATH     pipeline.json emitted by analyst/planner.
  --manifest PATH     capability manifest; defaults to core/policies.
  --agent-dir PATH    optional existing custom/system agent directories.

Outputs:
  text or JSON report with per-stage failures.

Exit codes:
  0 - pipeline capability preflight passed
  1 - pipeline violates runtime capability policy
  2 - invalid arguments or unreadable structured input

Example:
  python3 core/scripts/pipeline-capability-check.py --pipeline /tmp/pipeline.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from quality_loop_lib import stage_agents


AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
DESTRUCTIVE_CUSTOM_NAME_RE = re.compile(r"(devops|deploy|release|push|merge|rollback|delete|destroy|ops)", re.I)
CAPABILITY_PROFILE_RE = re.compile(r"^capability_profile\s*[:=]\s*\"?([a-z][a-z0-9-]*)\"?\s*$", re.MULTILINE)


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "JSON root must be an object"
    return data, None


def existing_agent_names(agent_dirs: list[Path]) -> set[str]:
    names: set[str] = set()
    for directory in agent_dirs:
        if not directory.is_dir():
            continue
        for pattern in ("*.md", "*.toml"):
            for path in directory.glob(pattern):
                if path.is_file():
                    names.add(path.stem)
    return names


def existing_agent_profiles(agent_dirs: list[Path]) -> dict[str, str]:
    profiles: dict[str, str] = {}
    for directory in agent_dirs:
        if not directory.is_dir():
            continue
        for pattern in ("*.md", "*.toml"):
            for path in directory.glob(pattern):
                if not path.is_file():
                    continue
                head = "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:80])
                match = CAPABILITY_PROFILE_RE.search(head)
                if match:
                    profiles[path.stem] = match.group(1)
    return profiles


def planned_dynamic_agents(pipeline: dict[str, Any]) -> tuple[set[str], dict[str, str], list[dict[str, Any]]]:
    planned: set[str] = set()
    profiles: dict[str, str] = {}
    failures: list[dict[str, Any]] = []
    entries = pipeline.get("needs_creation") or []
    if not isinstance(entries, list):
        failures.append(failure("needs_creation", None, "needs_creation_not_array", "needs_creation must be an array."))
        return planned, profiles, failures

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            failures.append(failure("needs_creation", None, "needs_creation_entry_not_object", f"entry {index} must be an object."))
            continue
        name = str(entry.get("name", ""))
        if not AGENT_NAME_RE.match(name):
            failures.append(failure("needs_creation", None, "invalid_dynamic_agent_name", f"entry {index} name={name!r}"))
            continue
        planned.add(name)
        profile = entry.get("capability_profile")
        if profile is not None:
            if isinstance(profile, str) and AGENT_NAME_RE.match(profile):
                profiles[name] = profile
            else:
                failures.append(
                    failure("needs_creation", None, "invalid_custom_capability_profile", f"entry {index} capability_profile={profile!r}", name)
                )
    return planned, profiles, failures


def all_stage_agents(pipeline: dict[str, Any]) -> list[str]:
    agents: list[str] = []
    for stage in pipeline.get("stages") or []:
        agents.extend(stage_agents(stage))
    return agents


def failure(scope: str, stage_index: int | None, code: str, detail: str, agent: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "scope": scope,
        "code": code,
        "detail": detail,
    }
    if stage_index is not None:
        item["stage_index"] = stage_index
    if agent:
        item["agent"] = agent
    return item


def is_solo_stage(agents: list[str], expected: str) -> bool:
    return agents == [expected]


def custom_profiles(manifest: dict[str, Any]) -> tuple[dict[str, Any], str]:
    profiles = manifest.get("custom_profiles")
    default_profile = manifest.get("default_custom_profile")
    if not isinstance(profiles, dict):
        profiles = {}
    if not isinstance(default_profile, str):
        default_profile = "custom-worker"
    return profiles, default_profile


def validate_stage_policy(
    *,
    agent: str,
    data: dict[str, Any],
    agents: list[str],
    stages: list[Any],
    index: int,
    custom: bool,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    role = data.get("role")
    may_delegate = data.get("may_delegate") is True
    mutates_workflow = data.get("may_mutate_workflow_state") is True
    destructive = data.get("may_execute_destructive") is True

    if role == "component":
        failures.append(
            failure("stage", index, "component_agent_in_runtime_stage", "Supervisor component files are not executable stage agents.", agent)
        )
    if may_delegate:
        failures.append(
            failure("stage", index, "delegating_agent_in_runtime_stage", "Runtime stages must not spawn delegating/orchestrator agents recursively.", agent)
        )
    if mutates_workflow:
        failures.append(
            failure("stage", index, "workflow_state_agent_in_runtime_stage", "Only the supervisor mutates workflow state.", agent)
        )
    if role == "reviewer" and not is_solo_stage(agents, agent):
        failures.append(
            failure("stage", index, "reviewer_stage_must_be_solo", "Reviewer validation must run as a solo stage.", agent)
        )
    if role == "devops":
        if not is_solo_stage(agents, agent):
            failures.append(
                failure("stage", index, "devops_stage_must_be_solo", "DevOps approval-gated work must run as a solo stage.", agent)
            )
        if destructive and data.get("destructive_requires_approval") is not True:
            failures.append(
                failure("stage", index, "devops_missing_approval_requirement", "Destructive devops capability requires approval.", agent)
            )
        next_agents = stage_agents(stages[index + 1]) if index + 1 < len(stages) else []
        if next_agents != ["reviewer"]:
            failures.append(
                failure("stage", index, "devops_stage_requires_followup_reviewer", "DevOps stages must be followed by a solo reviewer stage.", agent)
            )
    if custom and role in {"orchestrator", "planner", "component"}:
        failures.append(
            failure("stage", index, "custom_profile_grants_recursive_authority", "Custom profiles must not grant orchestrator, planner, or component authority.", agent)
        )
    return failures


def validate_pipeline_capabilities(
    pipeline: dict[str, Any],
    manifest: dict[str, Any],
    *,
    custom_agent_names: set[str] | None = None,
    custom_agent_profiles: dict[str, str] | None = None,
) -> dict[str, Any]:
    agents_manifest = manifest.get("agents")
    custom_agent_names = custom_agent_names or set()
    custom_agent_profiles = custom_agent_profiles or {}
    profile_manifest, default_profile = custom_profiles(manifest)
    failures: list[dict[str, Any]] = []

    if manifest.get("schema_version") != 1 or not isinstance(agents_manifest, dict) or not isinstance(profile_manifest, dict):
        return {
            "passed": False,
            "failures": [failure("manifest", None, "invalid_capability_manifest", "manifest must have schema_version=1, agents object, and custom profile object.")],
            "summary": {"stages": 0, "agents": 0, "custom_agents": 0},
        }

    stages = pipeline.get("stages")
    if not isinstance(stages, list):
        return {
            "passed": False,
            "failures": [failure("pipeline", None, "stages_not_array", "pipeline.stages must be an array.")],
            "summary": {"stages": 0, "agents": 0, "custom_agents": 0},
        }

    planned_dynamic, dynamic_profiles, dynamic_failures = planned_dynamic_agents(pipeline)
    failures.extend(dynamic_failures)
    manifest_agents = set(agents_manifest)
    stage_agent_names = all_stage_agents(pipeline)
    stage_agent_set = set(stage_agent_names)

    for name in sorted(planned_dynamic & manifest_agents):
        failures.append(
            failure(
                "needs_creation",
                None,
                "needs_creation_conflicts_with_manifest_agent",
                "needs_creation must not redefine a manifest-managed agent.",
                name,
            )
        )

    for name in sorted(planned_dynamic - stage_agent_set):
        failures.append(
            failure(
                "needs_creation",
                None,
                "dynamic_agent_not_used_in_stages",
                "Every planned dynamic agent must appear in at least one stage.",
                name,
            )
        )

    for index, stage in enumerate(stages):
        agents = stage_agents(stage)
        if not agents:
            failures.append(failure("stage", index, "empty_stage", "Stage has no executable agents."))
            continue

        duplicates = sorted({agent for agent in agents if agents.count(agent) > 1})
        if duplicates:
            failures.append(failure("stage", index, "duplicate_stage_agent", f"Duplicate agents in one stage: {duplicates}"))

        for agent in agents:
            if agent in agents_manifest:
                data = agents_manifest.get(agent) or {}
                failures.extend(validate_stage_policy(agent=agent, data=data, agents=agents, stages=stages, index=index, custom=False))
                continue

            is_custom = agent in custom_agent_names
            is_dynamic = agent in planned_dynamic
            if not is_custom and not is_dynamic:
                failures.append(
                    failure(
                        "stage",
                        index,
                        "unknown_agent_without_policy_or_creation_plan",
                        "Stage agent must be manifest-managed, an existing custom agent, or listed in needs_creation.",
                        agent,
                    )
                )
                continue

            profile_name = dynamic_profiles.get(agent) or custom_agent_profiles.get(agent) or default_profile
            profile = profile_manifest.get(profile_name)
            if not isinstance(profile, dict):
                failures.append(
                    failure(
                        "stage",
                        index,
                        "unknown_custom_capability_profile",
                        f"Custom/dynamic agent references unknown capability profile {profile_name!r}.",
                        agent,
                    )
                )
                continue

            failures.extend(validate_stage_policy(agent=agent, data=profile, agents=agents, stages=stages, index=index, custom=True))

            explicit_profile = profile_name != default_profile
            if DESTRUCTIVE_CUSTOM_NAME_RE.search(agent) and not (explicit_profile and profile.get("role") == "devops"):
                failures.append(
                    failure(
                        "stage",
                        index,
                        "custom_agent_name_implies_destructive_authority",
                        "Custom/dynamic agents with destructive names need an explicit custom-devops-approved style capability profile.",
                        agent,
                    )
                )
            if "reviewer" in agents or "devops" in agents:
                failures.append(
                    failure(
                        "stage",
                        index,
                        "custom_agent_mixed_with_gated_role",
                        "Custom/dynamic agents must not share a stage with reviewer or devops.",
                        agent,
                    )
                )

    return {
        "passed": not failures,
        "failures": failures,
        "summary": {
            "stages": len(stages),
            "agents": len(stage_agent_names),
            "custom_agents": len([agent for agent in stage_agent_set if agent not in agents_manifest]),
        },
    }


def evaluate(pipeline_path: Path, manifest_path: Path, agent_dirs: list[Path]) -> dict[str, Any]:
    pipeline, pipeline_error = load_json(pipeline_path)
    if pipeline is None:
        return {
            "schema_version": 1,
            "pipeline": str(pipeline_path),
            "manifest": str(manifest_path),
            "passed": False,
            "summary": {"stages": 0, "agents": 0, "custom_agents": 0},
            "failures": [failure("pipeline", None, "pipeline_parse_failed", pipeline_error or "unable to parse pipeline")],
        }

    manifest, manifest_error = load_json(manifest_path)
    if manifest is None:
        return {
            "schema_version": 1,
            "pipeline": str(pipeline_path),
            "manifest": str(manifest_path),
            "passed": False,
            "summary": {"stages": 0, "agents": 0, "custom_agents": 0},
            "failures": [failure("manifest", None, "manifest_parse_failed", manifest_error or "unable to parse manifest")],
        }

    result = validate_pipeline_capabilities(
        pipeline,
        manifest,
        custom_agent_names=existing_agent_names(agent_dirs),
        custom_agent_profiles=existing_agent_profiles(agent_dirs),
    )
    return {
        "schema_version": 1,
        "pipeline": str(pipeline_path),
        "manifest": str(manifest_path),
        **result,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--manifest", default=str(repo_root / "core" / "policies" / "agent-capabilities.json"))
    parser.add_argument("--agent-dir", action="append", default=[])
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    result = evaluate(
        Path(args.pipeline).expanduser().resolve(),
        Path(args.manifest).expanduser().resolve(),
        [Path(item).expanduser().resolve() for item in args.agent_dir],
    )

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        print(("PASS" if result["passed"] else "FAIL") + ": pipeline capability check")
        for item in result["failures"]:
            location = f"stage {item['stage_index']}: " if "stage_index" in item else ""
            agent = f" [{item['agent']}]" if item.get("agent") else ""
            print(f"- {location}{item['code']}{agent}: {item['detail']}")

    if result["passed"]:
        return 0
    if any(item["code"].endswith("_parse_failed") for item in result["failures"]):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
