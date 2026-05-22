#!/usr/bin/env python3
"""Deterministic local runtime helpers for the crew CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from quality_loop_lib import check_quality_loop, looks_mutating_task


def utc_now_z() -> str:
    """Return the progress-buffer timestamp format used by supervisor."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def load_json(path: Path, fallback: dict | None = None) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback or {})
    return data if isinstance(data, dict) else dict(fallback or {})


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def append_progress(task_dir: Path, row: dict) -> None:
    append_jsonl(task_dir / "progress.buffer.jsonl", row)


def render_completed_result(task: str, task_id: str, completion_path: str, note: str) -> str:
    lines = [
        f"# {task}",
        "",
        "STATUS: completed",
        f"TASK_ID: {task_id}",
        "MEASUREMENTS: host bridge completion recorded 1 automatic completion event",
        f"EVIDENCE: {completion_path}",
        "UNCERTAINTY: Host bridge command success indicates handoff delivery completed; downstream host prompt quality still depends on the active runtime.",
    ]
    if note:
        lines.append(f"NOTE: {note}")
    return "\n".join(lines).rstrip() + "\n"


def render_quality_loop_blocked_result(
    task: str,
    task_id: str,
    failures: list[str],
    evidence_path: str,
) -> str:
    return (
        f"# {task}\n\n"
        "STATUS: blocked\n"
        f"TASK_ID: {task_id}\n"
        "MEASUREMENTS: runtime quality-loop validation ran 1 check, 0 retries\n"
        "BLOCKER: missing_quality_loop_pipeline\n"
        f"EVIDENCE: {evidence_path}\n"
        "EVIDENCE: context/quality-loop-runtime-check.json\n"
        "DETAIL: Host bridge or fake-host completion cannot mark a mutating "
        "implementation task completed until the pipeline trace proves TDD, "
        "review, remediation/refactor after rejection, and reviewer approval.\n"
        "FAILURES: " + ", ".join(failures) + "\n"
        "UNCERTAINTY: Host bridge execution may have run outside this process, "
        "but it did not leave the required provider-neutral quality-loop state.\n"
    )


def host_bridge_next_line(task_dir: Path, task_id: str) -> str:
    return (
        f"NEXT: Continue with {task_dir / 'handoff.md'}, then run "
        f"`crew repair {task_id} --status completed --note \"<summary>\"`.\n"
    )


def mark_quality_loop_blocked(
    task_dir: Path,
    register: dict,
    pipeline: dict,
    quality_result: dict,
    evidence_path: str,
) -> None:
    now = utc_now_z()
    failures = list(quality_result.get("failures", []))
    check_path = task_dir / "context" / "quality-loop-runtime-check.json"
    write_json(check_path, quality_result)

    register.update({
        "current_phase": "blocked",
        "blocked_by": ["missing_quality_loop_pipeline"],
        "host_bridge_status": "quality_blocked",
        "host_bridge_completion_path": str(task_dir / evidence_path),
        "host_bridge_completed_at": now,
    })
    pipeline.setdefault("completed_stages", 0)

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    (task_dir / "result.md").write_text(
        render_quality_loop_blocked_result(
            register.get("task", task_dir.name),
            register.get("task_id", task_dir.name),
            failures,
            evidence_path,
        ),
        encoding="utf-8",
    )

    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now} | QUALITY_BLOCKED | missing_quality_loop_pipeline\n")
        handle.write(f"{now} | STATUS | blocked\n")

    append_progress(
        task_dir,
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', task_dir.name)}.{task_dir.name}.0.0",
            "task_id": task_dir.name,
            "session_id": register.get("session_id", ""),
            "event": "QUALITY_BLOCKED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "failed",
            "detail": "missing_quality_loop_pipeline",
            "files": [evidence_path, "context/quality-loop-runtime-check.json", "result.md"],
        },
    )


def mark_auto_completed(task_dir: Path, register: dict, pipeline: dict,
                        bridge_record: dict, note: str,
                        preserve_quality_state: bool = False) -> None:
    now = utc_now_z()
    completion_path = task_dir / "context" / "host-bridge-completion.json"
    write_json(completion_path, bridge_record)

    register.update({
        "current_phase": "completed",
        "blocked_by": [],
        "host_bridge_status": "auto_completed",
        "host_bridge_completion_path": str(completion_path),
        "host_bridge_completed_at": now,
    })

    stages = pipeline.get("stages") or ["supervisor"]
    pipeline["completed_stages"] = len(stages)
    if preserve_quality_state:
        pipeline.setdefault("stage_agent_status", {})
    else:
        pipeline["stage_agent_status"] = {
            "1": {"supervisor": "completed"}
        }

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    existing_result = load_text(task_dir / "result.md")
    if preserve_quality_state and re.search(r"^STATUS\s*:\s*completed\b", existing_result, re.I | re.M):
        marker = "HOST_BRIDGE: auto_completed"
        addition = (
            "\n" + marker + "\n"
            "EVIDENCE: context/host-bridge-completion.json\n"
        )
        if marker not in existing_result:
            (task_dir / "result.md").write_text(existing_result.rstrip() + addition, encoding="utf-8")
    else:
        (task_dir / "result.md").write_text(
            render_completed_result(
                register.get("task", task_dir.name),
                register.get("task_id", task_dir.name),
                "context/host-bridge-completion.json",
                note,
            ),
            encoding="utf-8",
        )

    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now} | HOST_BRIDGE | auto completed\n")
        handle.write(f"{now} | STATUS | completed\n")

    append_progress(
        task_dir,
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', task_dir.name)}.{task_dir.name}.0.0",
            "task_id": task_dir.name,
            "session_id": register.get("session_id", ""),
            "event": "HOST_BRIDGE",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "completed",
            "detail": "auto host bridge completed",
            "files": ["context/host-bridge-completion.json", "result.md"],
        },
    )
    append_progress(
        task_dir,
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', task_dir.name)}.{task_dir.name}.0.0",
            "task_id": task_dir.name,
            "session_id": register.get("session_id", ""),
            "event": "COMPLETED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "completed",
            "detail": "completed",
            "files": [],
        },
    )


def invoke_host_bridge(command: str, *, task_dir: Path, register: dict,
                       project_root: Path) -> dict:
    env = os.environ.copy()
    env.update({
        "AGENT_CREW_TASK_ID": register["task_id"],
        "AGENT_CREW_TASK_DIR": str(task_dir),
        "AGENT_CREW_HANDOFF_PATH": str(task_dir / "handoff.md"),
        "AGENT_CREW_RESULT_PATH": str(task_dir / "result.md"),
        "AGENT_CREW_PROJECT_ROOT": str(project_root),
    })
    started = datetime.now(timezone.utc)
    proc = subprocess.run(command, shell=True, text=True, capture_output=True, env=env)
    finished = datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "task_id": register["task_id"],
        "command": command,
        "command_display": shlex.split(command)[0] if command.strip() else "",
        "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_at": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }


def asset_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def read_agent_registry(root: Path) -> dict[str, dict]:
    registry_path = root / "rules" / "agent-routing.md"
    agents: dict[str, dict] = {}
    if not registry_path.exists():
        return agents

    in_registry = False
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "## Agent Registry":
            in_registry = True
            continue
        if in_registry and line.startswith("## ") and line.strip() != "## Agent Registry":
            break
        if not in_registry or not line.startswith("|"):
            continue
        if "---" in line or line.startswith("| Agent "):
            continue

        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        name, scope, keywords, safe, reason = cells[:5]
        agents[name] = {
            "scope": scope,
            "keywords": keywords,
            "safe": safe.lower() == "yes",
            "reason": "" if reason == "—" else reason,
        }
    return agents


def looks_mutating(task: str) -> bool:
    return bool(
        re.search(
            r"\b(build|implement|create|add|update|fix|remove|move|change|migrate|"
            r"refactor|replace|extend|integrate|test|deploy|merge|rollback|write|"
            r"save|edit|publish|commit)\b|"
            r"구현|개발|추가|수정|개선|보완|변경|삭제|이동|마이그레이션|"
            r"리팩터|테스트|배포|머지|롤백|반영|저장|발행|고쳐",
            task,
            re.IGNORECASE,
        )
    )


def auto_route_agent(task: str, agents: dict[str, dict]) -> tuple[str | None, str]:
    lowered = task.lower()
    route_patterns = [
        ("historian", ["어떤 에이전트", "방금", "what just", "what ran", "what agent", "this session", "this branch"]),
        ("backend", ["api", "endpoint", "server", "database", "schema", "domain", "service", "repository", "entity"]),
        ("frontend", ["component", " page", " ui ", " css", "style", "layout", "button", "form", "modal", "react", "vue"]),
        ("designer", ["wireframe", "mockup", "figma", "prototype", "sketch"]),
        ("planner", ["design", "architecture", "plan", "decompose", "structure", "diagram"]),
        ("analyst", ["explain", "investigate", "understand", "trace", "audit", "explore", "리뷰", "검토", "평가"]),
        ("documenter", ["docs", "readme", "documentation", "guide", "reference", "changelog"]),
        ("learning-mentor", ["teach", "learn", "concept", "pattern", "tutorial", "example"]),
    ]
    for name, tokens in route_patterns:
        if name in agents and any(token in lowered or token in task for token in tokens):
            return name, f"matched {name} keywords"
    return None, "no direct-agent routing rule matched"


def command_run(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    project_name = project_root.name
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    state_dir = agent_crew_home / "state" / project_name
    tasks_dir = state_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    now_z = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    session_id = now.strftime("%Y%m%d-%H%M%S")
    task_id = f"{session_id}-0"
    index = 0
    while (tasks_dir / task_id).exists():
        index += 1
        task_id = f"{session_id}-{index}"

    task_dir = tasks_dir / task_id
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    fake_completed_requested = args.fake_host_result == "completed"
    fake_quality_blocked = fake_completed_requested and looks_mutating_task(args.task)
    result_status = "completed" if fake_completed_requested and not fake_quality_blocked else "blocked"
    current_phase = "completed" if result_status == "completed" else "blocked"
    blocked_by = []
    if fake_quality_blocked:
        blocked_by = ["missing_quality_loop_pipeline"]
    elif result_status != "completed":
        blocked_by = ["host_bridge_not_invoked"]
    blocked_next = host_bridge_next_line(task_dir, task_id)
    quality_next = (
        "NEXT: A mutating implementation task can only be auto-completed after "
        "the host runtime leaves pipeline-level quality-loop evidence in "
        "pipeline.json and progress.buffer.jsonl.\n"
    )

    bridge_command = args.host_bridge_command or os.environ.get("AGENT_CREW_HOST_BRIDGE_COMMAND", "")
    if fake_quality_blocked:
        host_bridge_status = "quality_blocked"
    elif result_status == "completed":
        host_bridge_status = "fake_completed"
    else:
        host_bridge_status = "pending" if bridge_command else "not_invoked"

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
        "verification_status": "failed" if fake_quality_blocked else "skipped",
        "pipeline_path": str(task_dir / "pipeline.json"),
        "handoff_path": str(task_dir / "handoff.md"),
        "progress_log_path": str(task_dir / "progress.log"),
        "progress_buffer_path": str(task_dir / "progress.buffer.jsonl"),
        "result_path": str(task_dir / "result.md"),
        "blocked_by": blocked_by,
        "host_bridge_status": host_bridge_status,
        "repair_command": f"crew repair {task_id} --status completed --note \"<summary>\"",
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
        f"BLOCKER: host AI bridge has not completed this handoff\n"
        f"REPAIR: crew repair {task_id} --status completed --note \"<summary>\"\n"
    )

    result = (
        f"# {args.task}\n\n"
        f"STATUS: {result_status}\n"
        f"TASK_ID: {task_id}\n"
        f"BRANCH: {register['branch']}\n"
    )
    if result_status == "blocked":
        if fake_quality_blocked:
            result += "BLOCKER: missing_quality_loop_pipeline\n"
            result += (
                "DETAIL: fake-host completion for mutating implementation "
                "tasks is blocked unless the quality loop is actually recorded.\n"
            )
            result += quality_next
        else:
            result += "BLOCKER: host AI bridge has not completed this handoff\n"
            result += blocked_next

    write_json(task_dir / "register.json", register)
    write_json(task_dir / "pipeline.json", pipeline)
    (task_dir / "handoff.md").write_text(handoff, encoding="utf-8")
    (task_dir / "result.md").write_text(result, encoding="utf-8")
    progress_status = "completed" if result_status == "completed" else "failed"
    (task_dir / "progress.log").write_text(
        f"{now_z} | STARTED | {args.task}\n"
        f"{now_z} | STATUS | {result_status}\n",
        encoding="utf-8",
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": now_z,
            "trace_id": f"{session_id}.{task_id}.0.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STARTED",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": "started",
            "detail": args.task,
            "files": [],
        },
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": utc_now_z(),
            "trace_id": f"{session_id}.{task_id}.0.0",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STATUS",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": progress_status,
            "detail": result_status,
            "files": [],
        },
    )

    if fake_quality_blocked:
        quality_result = check_quality_loop(task_dir, target_status="completed")
        mark_quality_loop_blocked(
            task_dir,
            register,
            pipeline,
            quality_result,
            "pipeline.json",
        )

    if result_status == "blocked" and bridge_command:
        bridge_record = invoke_host_bridge(
            bridge_command,
            task_dir=task_dir,
            register=register,
            project_root=project_root,
        )
        write_json(task_dir / "context" / "host-bridge-invocation.json", bridge_record)
        if bridge_record["returncode"] == 0:
            latest_register = load_json(task_dir / "register.json", register)
            latest_pipeline = load_json(task_dir / "pipeline.json", pipeline)
            if looks_mutating_task(str(latest_register.get("task", args.task))):
                quality_result = check_quality_loop(task_dir, target_status="completed")
                if not quality_result["passed"]:
                    mark_quality_loop_blocked(
                        task_dir,
                        latest_register,
                        latest_pipeline,
                        quality_result,
                        "context/host-bridge-invocation.json",
                    )
                    print(f"TASK_ID: {task_id}")
                    print(f"TASK_DIR: {task_dir}")
                    print("STATUS: blocked")
                    print("BLOCKER: missing_quality_loop_pipeline")
                    print("HOST_BRIDGE: quality_blocked")
                    return 3

                write_json(task_dir / "context" / "quality-loop-runtime-check.json", quality_result)
                latest_register = load_json(task_dir / "register.json", latest_register)
                latest_pipeline = load_json(task_dir / "pipeline.json", latest_pipeline)
                mark_auto_completed(
                    task_dir,
                    latest_register,
                    latest_pipeline,
                    bridge_record,
                    "Automatic host bridge command completed successfully after quality-loop validation.",
                    preserve_quality_state=True,
                )
                print(f"TASK_ID: {task_id}")
                print(f"TASK_DIR: {task_dir}")
                print("STATUS: completed")
                print("HOST_BRIDGE: auto_completed")
                return 0

            mark_auto_completed(
                task_dir,
                register,
                pipeline,
                bridge_record,
                "Automatic host bridge command completed successfully.",
            )
            print(f"TASK_ID: {task_id}")
            print(f"TASK_DIR: {task_dir}")
            print("STATUS: completed")
            print("HOST_BRIDGE: auto_completed")
            return 0

        register["host_bridge_status"] = "failed"
        register["host_bridge_completion_path"] = str(task_dir / "context" / "host-bridge-invocation.json")
        write_json(task_dir / "register.json", register)

    print(f"TASK_ID: {task_id}")
    print(f"TASK_DIR: {task_dir}")
    print(f"STATUS: {result_status}")
    if result_status == "blocked":
        if fake_quality_blocked:
            print("BLOCKER: missing_quality_loop_pipeline")
            print(quality_next.rstrip())
        else:
            print("BLOCKER: host AI bridge has not completed this handoff")
            print(blocked_next.rstrip())
        return 3
    return 0


def command_agent(args: argparse.Namespace) -> int:
    root = asset_root(args.asset_root)
    agents = read_agent_registry(root)
    raw_args = list(args.agent_args or [])

    if not raw_args and not args.list and not args.routing:
        print("usage: crew-runtime.py agent [--list|--routing|agent-name task|task]")
        return 0

    if args.list:
        print(f"Available direct agents (source: {root / 'rules' / 'agent-routing.md'})")
        for name in sorted(agents):
            if agents[name]["safe"]:
                print(f"  {name}: {agents[name]['scope']}")
        return 0

    if args.routing:
        registry_path = root / "rules" / "agent-routing.md"
        text = registry_path.read_text(encoding="utf-8")
        start = text.find("## Auto-Routing Rules")
        end = text.find("### Matching semantics", start)
        print(text[start:end].rstrip() if start >= 0 and end > start else text)
        return 0

    if raw_args[0] in agents:
        agent_name = raw_args[0]
        task = " ".join(raw_args[1:]).strip()
        route_reason = "explicit direct-agent request"
    else:
        task = " ".join(raw_args).strip()
        agent_name, route_reason = auto_route_agent(task, agents)

    if not task:
        print("crew agent: task description is required", file=sys.stderr)
        return 2

    if looks_mutating(task):
        print("crew agent: direct invocation is read-only. Use crew run for mutating work.", file=sys.stderr)
        return 2

    if agent_name is None:
        print("crew agent: cannot auto-route this read-only task; specify an agent name or use crew run", file=sys.stderr)
        return 2

    info = agents.get(agent_name)
    if not info:
        print(f"crew agent: unknown agent '{agent_name}'", file=sys.stderr)
        return 2
    if not info["safe"]:
        reason = info["reason"] or "agent requires supervisor context"
        print(f"crew agent: '{agent_name}' cannot be invoked directly. Reason: {reason}", file=sys.stderr)
        return 2

    project_root = Path(args.project_root).resolve() if args.project_root else git_root()
    project_name = project_root.name
    agent_crew_home = Path(os.environ.get("AGENT_CREW_HOME", Path.home() / ".agent-crew")).expanduser()
    state_dir = agent_crew_home / "state" / project_name
    requests_dir = state_dir / "agent-requests"
    requests_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    request_id = f"agent-{now.strftime('%Y%m%d-%H%M%S')}-0"
    index = 0
    while (requests_dir / request_id).exists():
        index += 1
        request_id = f"agent-{now.strftime('%Y%m%d-%H%M%S')}-{index}"

    request_dir = requests_dir / request_id
    request = {
        "schema_version": 1,
        "request_id": request_id,
        "agent": agent_name,
        "task": task,
        "route_reason": route_reason,
        "project_root": str(project_root),
        "request_dir": str(request_dir),
        "status": "handoff_ready",
        "created_at": now.isoformat(),
    }
    handoff = (
        f"# Direct Agent Handoff\n\n"
        f"REQUEST_ID: {request_id}\n"
        f"AGENT: {agent_name}\n"
        f"TASK: {task}\n"
        f"PROJECT_ROOT: {project_root}\n"
        f"MODE: host-prompt-bridge\n"
        f"STATUS: handoff_ready\n"
        f"NEXT: Invoke crew:agent {agent_name!r} with this task inside the host prompt runtime.\n"
    )

    write_json(request_dir / "request.json", request)
    (request_dir / "handoff.md").write_text(handoff, encoding="utf-8")

    print(f"AGENT_REQUEST_ID: {request_id}")
    print(f"AGENT: {agent_name}")
    print(f"REQUEST_DIR: {request_dir}")
    print("STATUS: handoff_ready")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="agent-crew deterministic runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="create deterministic crew run state")
    run.add_argument("task")
    run.add_argument("--project-root")
    run.add_argument("--fake-host-result", choices=["completed"], default=None)
    run.add_argument("--host-bridge-command", default=None)
    run.set_defaults(func=command_run)

    agent = sub.add_parser("agent", help="create deterministic direct-agent handoff")
    agent.add_argument("--project-root")
    agent.add_argument("--asset-root")
    agent.add_argument("--list", action="store_true")
    agent.add_argument("--routing", action="store_true")
    agent.add_argument("agent_args", nargs=argparse.REMAINDER)
    agent.set_defaults(func=command_agent)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
