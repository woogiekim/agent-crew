#!/usr/bin/env python3
"""Deterministic local runtime helpers for the crew CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git_root() -> Path:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out:
            return Path(out).resolve()
    except Exception:
        pass
    return Path.cwd().resolve()


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return value[:48] or "task"


def append_jsonl(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_run(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    project_name = project_root.name
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    state_dir = agent_crew_home / "state" / project_name
    tasks_dir = state_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    session_id = now.strftime("%Y%m%d-%H%M%S")
    task_id = f"{session_id}-0"
    index = 0
    while (tasks_dir / task_id).exists():
        index += 1
        task_id = f"{session_id}-{index}"

    task_dir = tasks_dir / task_id
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    result_status = "completed" if args.fake_host_result == "completed" else "blocked"
    current_phase = "completed" if result_status == "completed" else "blocked"
    blocked_by = [] if result_status == "completed" else ["native_agent_execution_not_implemented"]

    register = {
        "schema_version": 1,
        "task_id": task_id,
        "session_id": session_id,
        "task": args.task,
        "branch": f"crew/{slug(args.task)}",
        "project_root": str(project_root),
        "task_dir": str(task_dir),
        "execution_mode": "single",
        "current_phase": current_phase,
        "approval_status": "not_required",
        "verification_status": "skipped",
        "pipeline_path": str(task_dir / "pipeline.json"),
        "handoff_path": str(task_dir / "handoff.md"),
        "progress_log_path": str(task_dir / "progress.log"),
        "progress_buffer_path": str(task_dir / "progress.buffer.jsonl"),
        "result_path": str(task_dir / "result.md"),
        "blocked_by": blocked_by,
    }

    pipeline = {
        "schema_version": 1,
        "task": args.task,
        "stages": ["supervisor"],
        "completed_stages": 1 if result_status == "completed" else 0,
        "stage_agent_status": {
            "1": {"supervisor": "completed" if result_status == "completed" else "blocked"}
        },
    }

    handoff = (
        f"# Supervisor Handoff\n\n"
        f"TASK_ID: {task_id}\n"
        f"TASK: {args.task}\n"
        f"PROJECT_ROOT: {project_root}\n"
        f"MODE: fake-host\n" if args.fake_host_result else
        f"# Supervisor Handoff\n\n"
        f"TASK_ID: {task_id}\n"
        f"TASK: {args.task}\n"
        f"PROJECT_ROOT: {project_root}\n"
        f"MODE: native-cli\n"
        f"STATUS: blocked\n"
        f"BLOCKER: native agent execution is not implemented yet\n"
    )

    result = (
        f"# {args.task}\n\n"
        f"STATUS: {result_status}\n"
        f"TASK_ID: {task_id}\n"
        f"BRANCH: {register['branch']}\n"
    )
    if result_status == "blocked":
        result += "BLOCKER: native agent execution is not implemented yet\n"

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    (task_dir / "handoff.md").write_text(handoff, encoding="utf-8")
    (task_dir / "result.md").write_text(result, encoding="utf-8")
    (task_dir / "progress.log").write_text(
        f"[{now.isoformat()}] STARTED {args.task}\n"
        f"[{now.isoformat()}] STATUS {result_status}\n",
        encoding="utf-8",
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": now.isoformat(),
            "trace_id": task_id,
            "task_id": task_id,
            "event": "STARTED",
            "detail": args.task,
        },
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": task_id,
            "task_id": task_id,
            "event": "STATUS",
            "detail": result_status,
        },
    )

    print(f"TASK_ID: {task_id}")
    print(f"TASK_DIR: {task_dir}")
    print(f"STATUS: {result_status}")
    if result_status == "blocked":
        print("BLOCKER: native agent execution is not implemented yet")
        return 3
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="agent-crew deterministic runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="create deterministic crew run state")
    run.add_argument("task")
    run.add_argument("--project-root")
    run.add_argument("--fake-host-result", choices=["completed"], default=None)
    run.set_defaults(func=command_run)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
