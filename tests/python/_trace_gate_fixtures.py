"""Shared fixtures/helpers for trace-derived repair quality-gate tests.

Not a test module (underscore prefix keeps pytest from collecting it).
Provides real temp-git-repo construction and schema-v1 trace-row writers
(``tool-events.jsonl`` / ``delegation.jsonl`` / cost rows /
``progress.buffer.jsonl`` reviewer-approved events) matching the shapes
emitted by ``core/scripts/crew-runtime.py`` (append_tool_event /
append_delegation) and ``core/hooks/cost-tracker.sh``.

Derived purely from context/prd.md Input/Output Contract and the schema
appenders in crew-runtime.py — NOT from the parallel implementer's
in-progress quality_loop_lib.py / repair-task-state.py additions.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"
QUALITY_LIB = SCRIPTS_DIR / "quality_loop_lib.py"
REPAIR = SCRIPTS_DIR / "repair-task-state.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_quality_lib():
    return load_module(QUALITY_LIB, "quality_loop_lib_trace_under_test")


# --------------------------------------------------------------------------
# git helpers — real temp repos, hermetic (no global config contamination)
# --------------------------------------------------------------------------
def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_AUTHOR_NAME"] = "Trace Test"
    env["GIT_AUTHOR_EMAIL"] = "trace@test.invalid"
    env["GIT_AUTHOR_DATE"] = "2026-07-15T00:00:00Z"
    env["GIT_COMMITTER_NAME"] = "Trace Test"
    env["GIT_COMMITTER_EMAIL"] = "trace@test.invalid"
    env["GIT_COMMITTER_DATE"] = "2026-07-15T00:00:00Z"
    return env


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        env=_git_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def init_git_repo(repo: Path) -> str:
    """Init a repo with one baseline commit; return the baseline HEAD sha."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "baseline")
    return head_sha(repo)


def head_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def commit_file(repo: Path, rel_path: str, content: str, message: str) -> str:
    """Write a file (committed) and return the new HEAD sha."""
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return head_sha(repo)


def write_working_tree_file(repo: Path, rel_path: str, content: str) -> None:
    """Write an uncommitted (working-tree) change."""
    target = repo / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# --------------------------------------------------------------------------
# task-dir / state-dir scaffolding
# --------------------------------------------------------------------------
def make_state_task(
    tmp_path: Path,
    task: str = "Implement a new update gate",
    *,
    task_id: str = "20260715-000000-0",
    project_root: Path | None = None,
    completed: bool = True,
) -> tuple[Path, str, Path]:
    """Create ``state_dir/tasks/{task_id}`` with register/pipeline/result.

    Layout matches ``{STATE_DIR}/tasks/{TASK_ID}`` so that a
    ``{STATE_DIR}/cost/{TASK_ID}.jsonl`` path resolves from ``task_dir``.
    """
    session_id = task_id.rsplit("-", 1)[0]
    state_dir = tmp_path / "state" / "project"
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "context").mkdir(parents=True)
    (state_dir / "cost").mkdir(parents=True, exist_ok=True)

    register: dict = {
        "task_id": task_id,
        "session_id": session_id,
        "task": task,
        "current_phase": "blocked",
        "blocked_by": ["host_bridge_not_invoked"],
    }
    if project_root is not None:
        register["project_root"] = str(project_root)
    (task_dir / "register.json").write_text(
        json.dumps(register) + "\n", encoding="utf-8"
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "task": task,
                "stages": [
                    {"agents": ["backend"], "tdd_parallel": True},
                    "reviewer",
                ],
                "completed_stages": 2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text(
        "STATUS: completed\n" if completed else "STATUS: blocked\n",
        encoding="utf-8",
    )
    (task_dir / "progress.log").write_text("started\n", encoding="utf-8")
    return state_dir, task_id, task_dir


def write_test_checklist_artifacts(task_dir: Path) -> None:
    (task_dir / "context" / "test-checklist.md").write_text(
        "# Test Checklist\n\n"
        "| TC-ID | Category | Given | When | Then | Priority | MUST / SHOULD / SUGGESTION | Reason |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| TC-001 | Normal | a gate | it runs | it accepts | P1 | MUST | required |\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "test-checklist-review.md").write_text(
        "REVIEW: APPROVED\nCHECKLIST_REVIEW_RESULT: approved\n- Missing MUST: none\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "test-case-mapping.md").write_text(
        "# Test Case Mapping\n\n"
        "| TC-ID | Test | Covered | Notes |\n"
        "|---|---|---|---|\n"
        "| TC-001 | tests/test_update_gate.py::test_ok | YES | normal |\n",
        encoding="utf-8",
    )


def write_quality_metrics(task_dir: Path) -> None:
    (task_dir / "context" / "quality-metrics.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hallucination_detected": False,
                "rollback_performed": False,
                "human_intervention_required": False,
                "factuality_review": "passed",
                "evidence_paths": ["context/review.md"],
            }
        ),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# git baselines
# --------------------------------------------------------------------------
def write_start_head(task_dir: Path, sha: str) -> None:
    (task_dir / "context" / "start-head.txt").write_text(sha + "\n", encoding="utf-8")


def write_pre_run_head(task_dir: Path, sha: str) -> None:
    (task_dir / "pre-run-head.txt").write_text(sha + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# tool-events.jsonl (schema v1 per crew-runtime.append_tool_event)
# --------------------------------------------------------------------------
def tool_event_row(
    *,
    trace_id: str = "20260715-000000.t.1.1",
    tool_name: str = "Bash",
    action_summary: str = "pytest tests/",
    started_at: str,
    ended_at: str,
    status: str = "completed",
    exit_code: int | None = 0,
    failure_class: str = "none",
) -> dict:
    return {
        "schema_version": 1,
        "trace_id": trace_id,
        "tool_name": tool_name,
        "action_summary": action_summary,
        "started_at": started_at,
        "ended_at": ended_at,
        "status": status,
        "exit_code": exit_code,
        "token_usage_ref": "cost/task.jsonl",
        "failure_class": failure_class,
    }


def write_tool_events(task_dir: Path, rows: list[dict]) -> None:
    with (task_dir / "tool-events.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def red_then_green_rows(
    *,
    command: str = "pytest tests/test_update_gate.py",
    red_start: str = "2026-07-15T00:00:01Z",
    red_end: str = "2026-07-15T00:00:02Z",
    green_start: str = "2026-07-15T00:00:05Z",
    green_end: str = "2026-07-15T00:00:06Z",
) -> list[dict]:
    return [
        tool_event_row(
            action_summary=command,
            started_at=red_start,
            ended_at=red_end,
            status="failed",
            exit_code=1,
            failure_class="test_failed",
        ),
        tool_event_row(
            action_summary=command,
            started_at=green_start,
            ended_at=green_end,
            status="completed",
            exit_code=0,
            failure_class="none",
        ),
    ]


def host_bridge_row(*, started_at: str, ended_at: str) -> dict:
    return tool_event_row(
        tool_name="host_bridge_command",
        action_summary="crew host bridge reviewer",
        started_at=started_at,
        ended_at=ended_at,
        status="completed",
        exit_code=0,
    )


# --------------------------------------------------------------------------
# delegation.jsonl (schema per crew-runtime.append_delegation)
# --------------------------------------------------------------------------
def delegation_row(
    *,
    agent_role: str,
    ts: str = "2026-07-15T00:00:03Z",
    trace_id: str = "20260715-000000.t.2.1",
    span_id: str = "span-2",
    parent_span_id: str = "span-1",
    unit_id: str = "u1",
    delegated_by: str = "supervisor",
    status: str = "completed",
) -> dict:
    return {
        "ts": ts,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "agent_role": agent_role,
        "unit_id": unit_id,
        "delegated_by": delegated_by,
        "status": status,
    }


def write_delegation(task_dir: Path, rows: list[dict]) -> None:
    with (task_dir / "delegation.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


# --------------------------------------------------------------------------
# cost row (per cost-tracker.sh) — {STATE_DIR}/cost/{TASK_ID}.jsonl
# --------------------------------------------------------------------------
def write_cost_rows(task_dir: Path, rows: list[dict]) -> None:
    task_id = task_dir.name
    cost_dir = task_dir.parent.parent / "cost"
    cost_dir.mkdir(parents=True, exist_ok=True)
    with (cost_dir / f"{task_id}.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def cost_row(*, agent: str, ts: str = "2026-07-15T00:00:04Z") -> dict:
    return {
        "ts": ts,
        "task_id": "task",
        "session_id": "20260715-000000",
        "agent": agent,
        "stage": 2,
        "model": "test",
        "tier": "unknown",
        "input_tokens": 10,
        "output_tokens": 5,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
    }


# --------------------------------------------------------------------------
# progress.buffer.jsonl reviewer-approved event
# --------------------------------------------------------------------------
def reviewer_approved_event(
    *,
    ts: str = "2026-07-15T00:00:03Z",
    task_id: str = "20260715-000000-0",
) -> dict:
    session_id = task_id.rsplit("-", 1)[0]
    return {
        "ts": ts,
        "trace_id": f"{session_id}.{task_id}.2.1",
        "task_id": task_id,
        "session_id": session_id,
        "event": "STAGE_DONE",
        "stage": 2,
        "agent": "reviewer",
        "attempt": 1,
        "status": "completed",
        "detail": "reviewer - REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
        "files": [],
    }


def implementer_and_reviewer_events(
    *,
    task_id: str = "20260715-000000-0",
    include_test_file: bool = True,
    reviewer_ts: str = "2026-07-15T00:00:03Z",
) -> list[dict]:
    """Baseline progress buffer: test-writer + backend + reviewer-approved."""
    session_id = task_id.rsplit("-", 1)[0]
    trace = f"{session_id}.{task_id}"
    return [
        {
            "ts": "2026-07-15T00:00:00Z",
            "trace_id": f"{trace}.1.1",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "test-writer",
            "attempt": 1,
            "status": "completed",
            "detail": "TDD RED GREEN REFACTOR, 3 tests passed",
            "files": ["tests/test_update_gate.py"] if include_test_file else [],
        },
        {
            "ts": "2026-07-15T00:00:01Z",
            "trace_id": f"{trace}.1.1",
            "task_id": task_id,
            "session_id": session_id,
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "backend",
            "attempt": 1,
            "status": "completed",
            "detail": "backend - N/A",
            "files": [],
        },
        reviewer_approved_event(ts=reviewer_ts, task_id=task_id),
    ]


def write_progress_buffer(task_dir: Path, rows: list[dict]) -> None:
    with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
