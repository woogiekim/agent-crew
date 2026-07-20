#!/usr/bin/env bash
# PostToolUse hook: fail closed when a supervisor records stage/completion
# progress before pipeline.json exists. This is a defense-in-depth backstop for
# the supervisor log_progress hard gate.

set -euo pipefail

INPUT=""
IFS= read -r -d '' INPUT || true
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"

has_active_task_marker() {
    if [ -n "${AGENT_CREW_TASK_ID:-}" ]; then
        return 0
    fi

    if [ -n "${AGENT_CREW_STATE_DIR:-}" ]; then
        if [ -f "${AGENT_CREW_STATE_DIR}/tasks/active" ]; then
            return 0
        fi
        if compgen -G "${AGENT_CREW_STATE_DIR}/tasks/active.*" >/dev/null; then
            return 0
        fi
    fi

    if compgen -G "${AGENT_CREW_HOME}/state/*/tasks/active" >/dev/null; then
        return 0
    fi
    compgen -G "${AGENT_CREW_HOME}/state/*/tasks/active.*" >/dev/null
}

# Most Codex/Claude PostToolUse events happen outside an active supervisor
# task. Avoid Python startup entirely until there is state the guard can
# actually inspect. Active-task cases still run the existing fail-closed Python
# verifier below.
if ! has_active_task_marker; then
    exit 0
fi

python3 - "$INPUT" "$AGENT_CREW_HOME" <<'PYEOF'
import json
import hashlib
import os
import re
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
TERMINAL_STATUS_RE = re.compile(
    r"^\s*STATUS:\s*(completed|blocked|cancelled)\s*$",
    re.IGNORECASE | re.MULTILINE,
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
    cwd = (path if path.is_dir() else path.parent).resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def resolved_state_dirs(project_root) -> list[Path]:
    if project_root is None:
        override = os.environ.get("AGENT_CREW_STATE_DIR")
        return [Path(override).expanduser()] if override else []

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", project_root.name.strip()).strip(".-").lower()
    slug = slug or "project"
    digest = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:10]
    keyed = agent_crew_home / "state" / f"{slug}-{digest}"
    legacy = agent_crew_home / "state" / project_root.name

    if keyed.exists() or not legacy.exists():
        return [keyed]
    if legacy_matches_project(legacy, project_root):
        return [legacy]
    return [keyed]


def legacy_matches_project(state_dir: Path, project_root: Path) -> bool:
    evidence_paths = [state_dir / "project.json", state_dir / "project-update.json"]
    evidence_paths.extend(sorted((state_dir / "tasks").glob("*/register.json"))[:25])

    for path in evidence_paths:
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("project_root")
        except Exception:
            continue
        if value:
            try:
                return Path(str(value)).expanduser().resolve() == project_root
            except Exception:
                return False

    for path in sorted((state_dir / "tasks").glob("*/project-root.txt"))[:25]:
        try:
            value = path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        if value:
            try:
                return Path(value).expanduser().resolve() == project_root
            except Exception:
                return False

    return True


def task_dirs_for_state(state_dir: Path) -> list[Path]:
    tasks_dir = state_dir / "tasks"
    if not tasks_dir.is_dir():
        return []

    markers = list(tasks_dir.glob("active.*"))
    dirs: list[Path] = []
    for marker in markers:
        if not marker.is_file():
            continue
        task_id = marker.name.removeprefix("active.")
        if not task_id:
            continue
        task_dir = tasks_dir / task_id
        if task_dir.is_dir():
            dirs.append(task_dir)

    legacy_marker = tasks_dir / "active"
    if legacy_marker.is_file():
        seen_dirs = {path.resolve() for path in dirs}
        task_dirs = [
            path
            for path in tasks_dir.iterdir()
            if (
                path.is_dir()
                and path.resolve() not in seen_dirs
                and not has_terminal_result(path)
            )
        ]
        task_dirs.sort()
        dirs.extend(task_dirs)
    return dirs


def has_terminal_result(task_dir: Path) -> bool:
    result_path = task_dir / "result.md"
    if not result_path.is_file():
        return False
    try:
        result = result_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    return bool(TERMINAL_STATUS_RE.search(result))


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
    result_path = task_dir / "result.violation.md"
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
        if has_terminal_result(task_dir):
            continue
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
