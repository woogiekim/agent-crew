#!/usr/bin/env bash
# PostToolUse hook: fail closed when a supervisor records stage/completion
# progress before pipeline.json exists. This is a defense-in-depth backstop for
# the supervisor log_progress hard gate.

set -euo pipefail

INPUT="$(cat)"
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"

python3 - "$INPUT" "$AGENT_CREW_HOME" <<'PYEOF'
import json
import os
import re
import subprocess
import sys
from pathlib import Path

raw_input = sys.argv[1] if len(sys.argv) > 1 else ""
agent_crew_home = Path(sys.argv[2]).expanduser()

FORBIDDEN_PROGRESS_RE = re.compile(
    r"\|\s*(STAGE|STAGE_DONE|STAGE_TDD_PARALLEL_STARTED|"
    r"STAGE_TDD_PARALLEL_DONE|STAGE_FANOUT_STARTED|"
    r"STAGE_FANOUT_UNIT_DONE|STAGE_FANOUT_DONE|"
    r"STAGE_STREAMING_REVIEW_STARTED|STAGE_STREAMING_REVIEW_DONE|"
    r"COMPLETED)\s*\|"
)


def block(reason: str) -> None:
    print(
        json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False),
        file=sys.stderr,
        flush=True,
    )
    sys.exit(2)


def load_payload() -> dict:
    try:
        data = json.loads(raw_input)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def candidate_path(payload: dict) -> str:
    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, dict):
        for key in ("cwd", "file_path", "path", "new_path"):
            value = tool_input.get(key)
            if value:
                return str(value)
    return os.getcwd()


def git_root(path_text: str):
    path = Path(path_text).expanduser()
    cwd = path if path.is_dir() else path.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    root = result.stdout.strip()
    return Path(root) if result.returncode == 0 and root else None


def resolved_state_dirs(project_root) -> list[Path]:
    dirs: list[Path] = []
    if project_root is not None:
        resolver = agent_crew_home / "scripts" / "project_state.py"
        if resolver.is_file():
            result = subprocess.run(
                [
                    "python3",
                    str(resolver),
                    "resolve",
                    "--agent-crew-home",
                    str(agent_crew_home),
                    "--project-root",
                    str(project_root),
                    "--prefer-existing-legacy",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                try:
                    state_dir = json.loads(result.stdout).get("state_dir")
                except Exception:
                    state_dir = ""
                if state_dir:
                    dirs.append(Path(state_dir))
        dirs.append(agent_crew_home / "state" / project_root.name)

    state_root = agent_crew_home / "state"
    if state_root.is_dir():
        dirs.extend(path for path in state_root.iterdir() if path.is_dir())

    unique: list[Path] = []
    seen: set[str] = set()
    for path in dirs:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def task_dirs_for_state(state_dir: Path) -> list[Path]:
    tasks_dir = state_dir / "tasks"
    if not tasks_dir.is_dir():
        return []

    markers = list(tasks_dir.glob("active.*"))
    if (tasks_dir / "active").is_file():
        return [path for path in tasks_dir.iterdir() if path.is_dir()]

    dirs: list[Path] = []
    for marker in markers:
        task_id = marker.name.removeprefix("active.")
        task_dir = tasks_dir / task_id
        if task_dir.is_dir():
            dirs.append(task_dir)
    return dirs


def latest_forbidden_line(progress_log: Path) -> str:
    if not progress_log.is_file():
        return ""
    try:
        lines = progress_log.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    for line in reversed(lines[-50:]):
        if "supervisor_pipeline_bypass_prevented" in line:
            continue
        if FORBIDDEN_PROGRESS_RE.search(line):
            return line
    return ""


def write_block_result(task_dir: Path, line: str) -> None:
    result_path = task_dir / "result.md"
    result_path.write_text(
        "\n".join(
            [
                "STATUS: blocked",
                "BLOCKER: supervisor_pipeline_bypass_prevented",
                "DETAIL: PostToolUse supervisor-progress-guard detected stage/completion progress before pipeline.json existed.",
                f"EVIDENCE: {line}",
                "",
            ]
        ),
        encoding="utf-8",
    )


payload = load_payload()
project_root = git_root(candidate_path(payload))

for state_dir in resolved_state_dirs(project_root):
    for task_dir in task_dirs_for_state(state_dir):
        if (task_dir / "pipeline.json").is_file():
            continue
        line = latest_forbidden_line(task_dir / "progress.log")
        if not line:
            continue
        write_block_result(task_dir, line)
        block(
            "[agent-crew] supervisor_pipeline_bypass_prevented: "
            f"{task_dir} recorded progress before pipeline.json: {line}"
        )

sys.exit(0)
PYEOF
