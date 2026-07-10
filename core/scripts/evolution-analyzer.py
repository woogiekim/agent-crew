#!/usr/bin/env python3
"""
evolution-analyzer.py - Provider-neutral post-task learning report generator.

Purpose:
  Read one completed task directory and emit a deterministic evolution report
  that records reusable-work signals without creating or registering assets.

Inputs:
  --task-dir DIR          Task directory to analyze.
  --state-dir DIR         Optional state dir. Defaults to env-derived resolver.
  --task-id ID            Alternative to --task-dir; resolves DIR/tasks/ID.
  --format json|markdown  Stdout format when no output file is requested.
  --json-output PATH      Optional JSON artifact path to write.
  --markdown-output PATH  Optional markdown artifact path to write.

Outputs:
  JSON and/or markdown. Writes report artifacts only inside the task directory
  when output paths are provided.

Exit codes:
  0 - report generated
  3 - invalid args / missing task directory
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def _load_telemetry_module():
    path = SCRIPT_DIR / "telemetry-aggregate.py"
    spec = importlib.util.spec_from_file_location("telemetry_aggregate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load telemetry module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("telemetry_aggregate", module)
    spec.loader.exec_module(module)
    return module


telemetry = _load_telemetry_module()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def resolve_state_dir(override: str | None) -> Path:
    if override:
        return Path(override)
    return telemetry.resolve_state_dir(None)


def resolve_task_dir(args: argparse.Namespace, state_dir: Path) -> Path:
    if args.task_dir:
        return Path(args.task_dir)
    if args.task_id:
        return state_dir / "tasks" / args.task_id
    raise ValueError("either --task-dir or --task-id is required")


def stage_agents(stage: Any) -> list[str]:
    if isinstance(stage, str):
        return [stage]
    if isinstance(stage, list):
        return [item for item in stage if isinstance(item, str)]
    if isinstance(stage, dict):
        agents = stage.get("agents")
        if isinstance(agents, str):
            return [agents]
        if isinstance(agents, list):
            return [item for item in agents if isinstance(item, str)]
    return []


def stage_skills(stage: Any) -> list[str]:
    if not isinstance(stage, dict):
        return []
    skills = stage.get("skills") or stage.get("selected_skills")
    if isinstance(skills, str):
        return [skills]
    if isinstance(skills, list):
        return [item for item in skills if isinstance(item, str)]
    return []


def pipeline_reused_assets(task_dir: Path) -> list[dict[str, str]]:
    pipeline = read_json(task_dir / "pipeline.json")
    stages = pipeline.get("stages")
    if not isinstance(stages, list):
        return []

    assets: dict[tuple[str, str], dict[str, str]] = {}
    for stage in stages:
        for agent in stage_agents(stage):
            assets.setdefault(
                ("agent", agent),
                {
                    "asset_type": "agent",
                    "name": agent,
                    "evidence_ref": "pipeline.json",
                },
            )
        for skill in stage_skills(stage):
            assets.setdefault(
                ("skill", skill),
                {
                    "asset_type": "skill",
                    "name": skill,
                    "evidence_ref": "pipeline.json",
                },
            )
    return [assets[key] for key in sorted(assets)]


def changed_files_from_events(events: list[dict[str, Any]], register: dict[str, Any]) -> list[str]:
    files: set[str] = set()
    for key in ("changed_files", "modified_files", "files"):
        value = register.get(key)
        if isinstance(value, list):
            files.update(str(item) for item in value if str(item).strip())

    for event in events:
        value = event.get("files")
        if isinstance(value, list):
            files.update(str(item) for item in value if str(item).strip())

    return sorted(files)


def skill_content_audit_signal(task_dir: Path) -> dict[str, Any]:
    payload = read_json(task_dir / "context" / "skill-content-audit.json")
    if not payload:
        return {
            "available": False,
            "shallow_finding_count": 0,
            "effective_followup_count": 0,
        }

    shallow = payload.get("shallow_findings")
    followups = payload.get("effective_followups")
    return {
        "available": True,
        "shallow_finding_count": len(shallow) if isinstance(shallow, list) else 0,
        "effective_followup_count": len(followups) if isinstance(followups, list) else 0,
    }


def observed_patterns(row: dict[str, Any], loop_backs: int,
                      skill_audit: dict[str, Any]) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    retries = int(row.get("retries") or 0)
    blockers = list(row.get("blockers") or [])

    if retries > 0:
        patterns.append({
            "kind": "retry",
            "summary": f"{retries} retry event(s) were recorded during the task.",
            "evidence_refs": ["progress.buffer.jsonl"],
        })
    if loop_backs > 0:
        patterns.append({
            "kind": "review_loop_back",
            "summary": f"{loop_backs} reviewer NEEDS_CHANGES loop-back(s) were recorded.",
            "evidence_refs": ["progress.buffer.jsonl"],
        })
    if blockers:
        patterns.append({
            "kind": "blocker",
            "summary": "Task recorded blocker signal(s): " + ", ".join(sorted(blockers)),
            "evidence_refs": ["register.json", "result.md"],
        })
    if int(skill_audit.get("shallow_finding_count") or 0) > 0:
        patterns.append({
            "kind": "skill_content_depth",
            "summary": "Skill content audit found shallow skill material.",
            "evidence_refs": ["context/skill-content-audit.json"],
        })

    return patterns


def rejected_candidates(patterns: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not patterns:
        return []

    if any(pattern["kind"] == "review_loop_back" for pattern in patterns):
        asset_type = "skill"
        name = "review-loop-hardening"
    elif any(pattern["kind"] == "blocker" for pattern in patterns):
        asset_type = "workflow"
        name = "blocker-recovery-playbook"
    else:
        asset_type = "workflow"
        name = "retry-reduction-playbook"

    return [{
        "asset_type": asset_type,
        "name": name,
        "reason": "A single task produced a reusable-work signal, but one task is not enough evidence to create or register a new asset.",
        "rejection_reason": "insufficient_repeated_evidence",
        "required_evidence": "Collect repeated evidence from at least two independent tasks before proposing a generated asset.",
    }]


def learning_summary(meaningful: bool, patterns: list[dict[str, Any]]) -> str:
    if not meaningful:
        return (
            "No reusable asset candidate produced; the task completed without "
            "retry, blocker, reviewer loop-back, or skill-content-depth signals."
        )

    kinds = ", ".join(pattern["kind"] for pattern in patterns)
    return (
        "Reusable-work signals were observed (" + kinds + "), but automatic "
        "asset generation is disabled in this first slice. Treat the report as "
        "evidence for future registry-reviewed proposals only."
    )


def build_report(state_dir: Path, task_dir: Path) -> dict[str, Any]:
    row = telemetry.aggregate_task(state_dir, task_dir)
    events = telemetry.read_progress_buffer(task_dir)
    register = telemetry.read_register(task_dir) or {}
    loop_backs = telemetry.count_reviewer_loop_backs(events)
    skill_audit = skill_content_audit_signal(task_dir)
    patterns = observed_patterns(row, loop_backs, skill_audit)
    meaningful = bool(patterns)

    return {
        "schema_version": 1,
        "task_id": row.get("task_id") or task_dir.name,
        "task": row.get("task") or register.get("task") or "",
        "generation_mode": "report_only",
        "meaningful": meaningful,
        "signals": {
            "retries": int(row.get("retries") or 0),
            "reviewer_loop_backs": loop_backs,
            "blockers": list(row.get("blockers") or []),
            "changed_files": changed_files_from_events(events, register),
            "skill_content_audit": skill_audit,
        },
        "reused_assets": pipeline_reused_assets(task_dir),
        "observed_patterns": patterns,
        "asset_candidates": [],
        "rejected_candidates": rejected_candidates(patterns),
        "learning_summary": learning_summary(meaningful, patterns),
        "guardrails": {
            "asset_writes": "disabled",
            "generator_invoked": False,
            "verification_bypass": False,
        },
    }


def markdown_list(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def to_markdown(report: dict[str, Any]) -> str:
    signals = report["signals"]
    skill_audit = signals["skill_content_audit"]
    reused = [
        f"{asset['asset_type']}: {asset['name']} ({asset['evidence_ref']})"
        for asset in report["reused_assets"]
    ]
    patterns = [
        f"{pattern['kind']}: {pattern['summary']}"
        for pattern in report["observed_patterns"]
    ]
    rejected = [
        f"{item['asset_type']}: {item['name']} - {item['rejection_reason']}"
        for item in report["rejected_candidates"]
    ]

    return "\n".join([
        "# Learning Report",
        "",
        f"Task: {report['task_id']}",
        f"Mode: {report['generation_mode']}",
        f"Meaningful signals: {str(report['meaningful']).lower()}",
        "",
        "## Summary",
        "",
        report["learning_summary"],
        "",
        "## Signals",
        "",
        f"- Retries: {signals['retries']}",
        f"- Reviewer loop-backs: {signals['reviewer_loop_backs']}",
        f"- Blockers: {', '.join(signals['blockers']) if signals['blockers'] else 'none'}",
        f"- Changed files: {', '.join(signals['changed_files']) if signals['changed_files'] else 'none'}",
        (
            "- Skill content audit: "
            f"available={str(skill_audit['available']).lower()}, "
            f"shallow={skill_audit['shallow_finding_count']}, "
            f"effective_followups={skill_audit.get('effective_followup_count', 0)}"
        ),
        "",
        "## Reused Assets",
        "",
        markdown_list(reused),
        "",
        "## Observed Patterns",
        "",
        markdown_list(patterns),
        "",
        "## Asset Candidates",
        "",
        "- None; automatic asset creation is disabled.",
        "",
        "## Rejected Candidates",
        "",
        markdown_list(rejected),
        "",
        "## Guardrails",
        "",
        "- Asset writes: disabled",
        "- Generator invoked: false",
        "- Verification bypass: false",
        "",
    ])


def write_report_outputs(report: dict[str, Any], args: argparse.Namespace) -> None:
    if args.json_output:
        write_text(
            Path(args.json_output),
            json.dumps(report, indent=2, sort_keys=True) + "\n",
        )
    if args.markdown_output:
        write_text(Path(args.markdown_output), to_markdown(report))


def output_path_inside_task_dir(output_path: str, task_dir: Path) -> bool:
    path = Path(output_path).resolve(strict=False)
    root = task_dir.resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def validate_output_paths(args: argparse.Namespace, task_dir: Path) -> None:
    for output_path in (args.json_output, args.markdown_output):
        if output_path and not output_path_inside_task_dir(output_path, task_dir):
            raise ValueError(
                "output path must be inside the task directory; "
                f"got {output_path}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="agent-crew evolution report analyzer")
    parser.add_argument("--state-dir")
    parser.add_argument("--task-dir")
    parser.add_argument("--task-id")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    try:
        state_dir = resolve_state_dir(args.state_dir)
        task_dir = resolve_task_dir(args, state_dir)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if not task_dir.is_dir():
        print(f"error: task directory not found: {task_dir}", file=sys.stderr)
        return 3

    try:
        validate_output_paths(args, task_dir)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    report = build_report(state_dir, task_dir)
    write_report_outputs(report, args)

    if not args.json_output and not args.markdown_output:
        if args.format == "markdown":
            sys.stdout.write(to_markdown(report))
        else:
            json.dump(report, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
