#!/usr/bin/env python3
"""파일 존재와 실행 계획 준비를 구분하는 읽기 전용 supervisor preflight."""
import argparse
import json
from pathlib import Path
import sys


def read_task_metadata(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def requires_initial_planning(path: Path, pipeline: dict) -> bool:
    if "planning_required" in pipeline:
        return pipeline["planning_required"] is True

    placeholder_fields = {
        "schema_version", "task", "mutation_scope", "stages", "completed_stages",
        "stage_agent_status", "checklist_evidence_version",
    }
    if (
        pipeline.keys() - placeholder_fields
        or pipeline.get("schema_version") != 1
        or pipeline.get("stages") != ["supervisor"]
        or pipeline.get("completed_stages") != 0
        or pipeline.get("stage_agent_status") != {"1": {"supervisor": "blocked"}}
    ):
        return False

    task_dir = path.parent
    context = task_dir / "context"
    register = read_task_metadata(task_dir / "register.json")
    bridge = read_task_metadata(context / "host-bridge-invocation.json")
    task = pipeline.get("task")
    return (
        register.get("execution_mode") == "single"
        and register.get("host_bridge_status") == "current_session_required"
        and register.get("current_phase") in (
            "handoff_ready", "phase_0", "phase_1a", "phase_1b_brainstorm", "phase_1c_plan",
        )
        and register.get("approval_status") == "not_required"
        and register.get("task_id") == bridge.get("task_id") == task_dir.name
        and isinstance(task, str) and bool(task)
        and register.get("task") == task
        and bridge.get("status") == bridge.get("failure_class") == "current_session_required"
        and bridge.get("direct_agent") is False
        and not (context / "approval.md").exists()
    )


def start_mode(path):
    if not path.exists():
        return "fresh"
    pipeline = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(pipeline, dict):
        raise ValueError("pipeline must be an object")
    required = pipeline.get("planning_required", False)
    if not isinstance(required, bool):
        raise ValueError("planning_required must be boolean")
    if requires_initial_planning(path, pipeline):
        if pipeline.get("stages") != ["supervisor"] or pipeline.get("completed_stages", 0) != 0:
            raise ValueError("planning placeholder conflicts with execution state")
        return "fresh"
    return "resume"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(start_mode(args.pipeline))
    except (ValueError, OSError) as error:
        print(f"supervisor start blocked: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
