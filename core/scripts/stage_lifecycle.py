#!/usr/bin/env python3
"""Provider-neutral lifecycle state for supervisor child invocations.

The helper owns deterministic state and decisions only. Host adapters remain
responsible for spawning, bounded waiting, and interrupting the real child.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_TERMINAL_GRACE_SECONDS = 30
MAX_INHERITED_HISTORY_TURNS = 3

DEFAULT_TIMEOUT_SECONDS = {
    "requirements": 600,
    "brainstorm": 900,
    "architectural_brainstorm": 1800,
    "analysis": 900,
    "planning": 1200,
    "test_writer": 1200,
    "implementation": 1800,
    "qa": 900,
    "reviewer": 900,
    "build_test_subprocess": 1200,
}

READ_ONLY_ARTIFACT_RECOVERY_KINDS = {
    "requirements",
    "brainstorm",
    "architectural_brainstorm",
    "analysis",
    "planning",
    "qa",
    "reviewer",
}

TIMING_FIELDS = {
    "first_output": "first_output_at",
    "artifact_ready": "artifact_ready_at",
    "terminal_completed": "terminal_at",
    "terminal_blocked": "terminal_at",
    "terminal_failed": "terminal_at",
    "timed_out": "terminal_at",
    "interrupted": "terminal_at",
    "parent_resume": "parent_resume_at",
}

TERMINAL_EVENTS = {
    "terminal_completed",
    "terminal_blocked",
    "terminal_failed",
    "timed_out",
    "interrupted",
}


def _parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _elapsed_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    return (_parse_timestamp(end) - _parse_timestamp(start)).total_seconds()


def _refresh_elapsed(state: dict[str, Any]) -> None:
    timing = state["timing"]
    state["elapsed_seconds"] = {
        "dispatch_to_first_output": _elapsed_seconds(
            timing["dispatched_at"], timing["first_output_at"]
        ),
        "first_output_to_artifact": _elapsed_seconds(
            timing["first_output_at"], timing["artifact_ready_at"]
        ),
        "artifact_to_terminal": _elapsed_seconds(
            timing["artifact_ready_at"], timing["terminal_at"]
        ),
        "terminal_to_parent_resume": _elapsed_seconds(
            timing["terminal_at"], timing["parent_resume_at"]
        ),
        "total": _elapsed_seconds(
            timing["dispatched_at"],
            timing["parent_resume_at"] or timing["terminal_at"],
        ),
    }


def _timeout_for(stage_kind: str, timeout_seconds: int | None) -> int:
    if timeout_seconds is not None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds_must_be_non_negative")
        return timeout_seconds
    return DEFAULT_TIMEOUT_SECONDS.get(stage_kind, 1200)


def new_stage_state(
    *,
    stage_index: int,
    agent: str,
    stage_kind: str,
    unit_id: str = "default",
    invocation_id: str = "invocation-1",
    attempt: int = 1,
    mutating: bool | None = None,
    now: str,
    timeout_seconds: int | None = None,
    timeout_enforceable: bool = True,
    terminal_grace_seconds: int = DEFAULT_TERMINAL_GRACE_SECONDS,
    fallback_mode: str = "native",
) -> dict[str, Any]:
    """Create lifecycle state before a child is dispatched."""
    if stage_index < 0:
        raise ValueError("stage_index_must_be_non_negative")
    if terminal_grace_seconds < 0:
        raise ValueError("terminal_grace_seconds_must_be_non_negative")
    if attempt < 1:
        raise ValueError("attempt_must_be_positive")
    _parse_timestamp(now)

    budget = _timeout_for(stage_kind, timeout_seconds)
    deadline = None
    if budget > 0:
        deadline = _format_timestamp(_parse_timestamp(now) + timedelta(seconds=budget))

    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "stage_index": stage_index,
        "agent": agent,
        "stage_kind": stage_kind,
        "unit_id": unit_id,
        "invocation_id": invocation_id,
        "attempt": attempt,
        "mutating": True if mutating is None else mutating,
        "fallback_mode": fallback_mode,
        "status": "dispatched",
        "timing": {
            "dispatched_at": now,
            "first_output_at": None,
            "artifact_ready_at": None,
            "terminal_at": None,
            "parent_resume_at": None,
        },
        "timeout": {
            "seconds": budget,
            "deadline_at": deadline,
            "enforceable": timeout_enforceable,
        },
        "terminal_grace_seconds": terminal_grace_seconds,
        "outcome": {
            "terminal_state": None,
            "terminal_reason": None,
            "timed_out": False,
            "interrupted": False,
        },
        "activity": {
            "subprocess_running": False,
            "last_progress_at": None,
        },
        "events": [
            {
                "event": "dispatched",
                "at": now,
                "reason": "child invocation dispatched",
                "event_id": "",
            }
        ],
        "seen_event_ids": [],
        "elapsed_seconds": {},
    }
    _refresh_elapsed(state)
    return state


def record_event(
    state: dict[str, Any],
    *,
    event: str,
    at: str,
    reason: str,
    event_id: str = "",
) -> dict[str, Any]:
    """Apply one idempotent, monotonic lifecycle event in place."""
    if event_id and event_id in state.get("seen_event_ids", []):
        return state

    current_time = _parse_timestamp(at)
    last_event = state.get("events", [])[-1]
    if current_time < _parse_timestamp(last_event["at"]):
        raise ValueError("event_timestamp_regressed")

    timing_field = TIMING_FIELDS.get(event)
    if timing_field and state["timing"].get(timing_field) is None:
        state["timing"][timing_field] = at

    if event in TERMINAL_EVENTS:
        state["status"] = event
        state["outcome"]["terminal_state"] = event
        state["outcome"]["terminal_reason"] = reason
        state["outcome"]["timed_out"] = (
            state["outcome"].get("timed_out", False) or event == "timed_out"
        )
        state["outcome"]["interrupted"] = (
            state["outcome"].get("interrupted", False) or event == "interrupted"
        )
    elif event == "parent_resume":
        state["status"] = "parent_resumed"
    elif event == "subprocess_started":
        state["activity"]["subprocess_running"] = True
        state["activity"]["last_progress_at"] = at
    elif event == "subprocess_finished":
        state["activity"]["subprocess_running"] = False
        state["activity"]["last_progress_at"] = at
    elif event in {"first_output", "artifact_ready", "progress"}:
        state["status"] = event
        state["activity"]["last_progress_at"] = at

    state["events"].append(
        {"event": event, "at": at, "reason": reason, "event_id": event_id}
    )
    if event_id:
        state.setdefault("seen_event_ids", []).append(event_id)
    _refresh_elapsed(state)
    return state


def preflight_action(state: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when a configured deadline cannot control the host."""
    timeout = state["timeout"]
    if timeout["seconds"] > 0 and not timeout["enforceable"]:
        return {
            "action": "block_before_dispatch",
            "reason": "stage_timeout_unenforceable",
            "retry_allowed": False,
        }
    return {"action": "dispatch", "reason": "preflight_passed", "retry_allowed": False}


def _terminal_text_state(terminal_text: str) -> str | None:
    if "STATUS: completed" in terminal_text:
        return "terminal_completed"
    if "STATUS: BLOCKED" in terminal_text or "STATUS: blocked" in terminal_text:
        return "terminal_blocked"
    if "STATUS: failed" in terminal_text:
        return "terminal_failed"
    return None


def decide_next_action(
    state: dict[str, Any],
    *,
    now: str,
    terminal_text: str = "",
    host_status: str = "unknown",
    required_artifacts_verified: bool = False,
    subprocess_running: bool = False,
    recent_progress: bool = False,
) -> dict[str, Any]:
    """Return the next supervisor action without mutating task state."""
    now_dt = _parse_timestamp(now)
    terminal_state = state["outcome"].get("terminal_state") or _terminal_text_state(
        terminal_text
    )
    if terminal_state == "terminal_completed":
        return {
            "action": "resume_parent",
            "reason": "terminal_completed",
            "retry_allowed": False,
        }
    if terminal_state in {"terminal_blocked", "terminal_failed", "timed_out"}:
        return {
            "action": "block",
            "reason": terminal_state,
            "retry_allowed": False,
        }

    timeout = state["timeout"]
    if timeout["seconds"] > 0 and not timeout["enforceable"]:
        return {
            "action": "block_before_dispatch",
            "reason": "stage_timeout_unenforceable",
            "retry_allowed": False,
        }
    deadline_at = timeout.get("deadline_at")
    if deadline_at and now_dt >= _parse_timestamp(deadline_at):
        return {
            "action": "interrupt_and_block",
            "reason": "stage_timeout",
            "retry_allowed": False,
        }

    artifact_ready_at = state["timing"].get("artifact_ready_at")
    if required_artifacts_verified and artifact_ready_at:
        child_active = (
            subprocess_running
            or state["activity"].get("subprocess_running")
            or recent_progress
            or host_status in {"running", "in_progress", "pending"}
        )
        if child_active:
            return {
                "action": "wait",
                "reason": "child_activity_in_progress",
                "retry_allowed": False,
            }
        grace_deadline = _parse_timestamp(artifact_ready_at) + timedelta(
            seconds=state["terminal_grace_seconds"]
        )
        if now_dt < grace_deadline:
            return {
                "action": "wait",
                "reason": "terminal_grace_active",
                "retry_allowed": False,
            }
        if not state.get("mutating", True):
            return {
                "action": "interrupt_and_accept_verified_artifact",
                "reason": "terminal_only_missing_after_verified_artifact",
                "retry_allowed": False,
            }
        return {
            "action": "interrupt_and_block",
            "reason": "mutating_terminal_missing_after_verified_artifact",
            "retry_allowed": False,
        }

    if host_status in {"error", "completed", "cancelled"}:
        retry_allowed = not state.get("mutating", True)
        return {
            "action": "retry" if retry_allowed else "interrupt_and_block",
            "reason": "terminal_missing_after_host_exit",
            "retry_allowed": retry_allowed,
        }
    return {
        "action": "wait",
        "reason": "terminal_and_artifact_pending",
        "retry_allowed": False,
    }


def build_child_context(
    *,
    task_dir: str,
    project_root: str,
    handoff_path: str,
    acceptance_criteria: list[str],
    skill_paths: list[str],
    verified_artifact_paths: list[str],
    branch: str,
    permissions: list[str],
    history_turns: int = 0,
    history_reason: str = "",
) -> dict[str, Any]:
    """Build the bounded path-only context passed to a child invocation."""
    if history_turns < 0:
        raise ValueError("history_turns_must_be_non_negative")
    if history_turns > 0 and not history_reason.strip():
        raise ValueError("history_reason_required")
    if history_turns > MAX_INHERITED_HISTORY_TURNS:
        raise ValueError("history_turn_limit_exceeded")

    context: dict[str, Any] = {
        "fork_turns": "none" if history_turns == 0 else str(history_turns),
        "task_dir": task_dir,
        "project_root": project_root,
        "handoff_path": handoff_path,
        "acceptance_criteria": acceptance_criteria,
        "skill_paths": skill_paths,
        "verified_artifact_paths": verified_artifact_paths,
        "branch": branch,
        "permissions": permissions,
    }
    if history_turns > 0:
        context["history_reason"] = history_reason
    return context


def lifecycle_state_path(
    directory: Path,
    *,
    stage_index: int,
    unit_id: str,
    invocation_id: str,
    attempt: int,
) -> Path:
    """Return a collision-free path for fan-out units and retries."""
    def safe(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
        return normalized or "default"

    return directory / (
        f"stage-{stage_index}-unit-{safe(unit_id)}-"
        f"invocation-{safe(invocation_id)}-attempt-{attempt}.json"
    )


def bounded_lifecycle_policy(
    *,
    classification: str,
    requirements_complete: bool,
    risk_tags: list[str],
) -> dict[str, Any]:
    """Select the small-Bounded lifecycle without weakening quality gates."""
    protected_risks = {"security", "migration", "destructive", "architectural"}
    normalized_risks = {item.strip().lower() for item in risk_tags}
    optimized = (
        classification.strip().lower() == "bounded"
        and requirements_complete
        and not normalized_risks.intersection(protected_risks)
    )
    steps = (
        ["bounded_design_and_plan", "tdd_controller", "independent_reviewer"]
        if optimized
        else [
            "requirements",
            "brainstorm",
            "analysis_and_plan",
            "tdd_controller",
            "qa",
            "independent_reviewer",
        ]
    )
    return {
        "optimized": optimized,
        "sequential_steps": steps,
        "tdd_required": True,
        "independent_review_required": True,
        "reuse_fresh_qa_evidence": optimized,
    }


def write_state_atomic(path: Path, state: dict[str, Any]) -> None:
    """Persist lifecycle state without exposing partial JSON to readers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def load_state(path: Path) -> dict[str, Any] | None:
    """Load state; a missing file is an accepted legacy-task condition."""
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_stage_lifecycle_schema")
    return value


def _read_required_state(path: Path) -> dict[str, Any]:
    state = load_state(path)
    if state is None:
        raise ValueError("stage_lifecycle_state_missing")
    return state


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--state", type=Path, required=True)
    init_parser.add_argument("--stage-index", type=int, required=True)
    init_parser.add_argument("--agent", required=True)
    init_parser.add_argument("--stage-kind", required=True)
    init_parser.add_argument("--unit-id", required=True)
    init_parser.add_argument("--invocation-id", required=True)
    init_parser.add_argument("--attempt", type=int, required=True)
    init_parser.add_argument("--mutating", choices=("true", "false"), required=True)
    init_parser.add_argument("--now", required=True)
    init_parser.add_argument("--timeout-seconds", type=int)
    init_parser.add_argument(
        "--timeout-enforceable", choices=("true", "false"), default="true"
    )
    init_parser.add_argument("--fallback-mode", default="native")

    event_parser = subparsers.add_parser("event")
    event_parser.add_argument("--state", type=Path, required=True)
    event_parser.add_argument("--event", required=True)
    event_parser.add_argument("--at", required=True)
    event_parser.add_argument("--reason", required=True)
    event_parser.add_argument("--event-id", default="")

    decide_parser = subparsers.add_parser("decide")
    decide_parser.add_argument("--state", type=Path, required=True)
    decide_parser.add_argument("--now", required=True)
    decide_parser.add_argument("--terminal-text", default="")
    decide_parser.add_argument("--host-status", default="unknown")
    decide_parser.add_argument("--required-artifacts-verified", action="store_true")
    decide_parser.add_argument("--subprocess-running", action="store_true")
    decide_parser.add_argument("--recent-progress", action="store_true")

    policy_parser = subparsers.add_parser("bounded-policy")
    policy_parser.add_argument("--classification", required=True)
    policy_parser.add_argument("--requirements-complete", action="store_true")
    policy_parser.add_argument("--risk-tag", action="append", default=[])
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "init":
        state = new_stage_state(
            stage_index=args.stage_index,
            agent=args.agent,
            stage_kind=args.stage_kind,
            unit_id=args.unit_id,
            invocation_id=args.invocation_id,
            attempt=args.attempt,
            mutating=args.mutating == "true",
            now=args.now,
            timeout_seconds=args.timeout_seconds,
            timeout_enforceable=args.timeout_enforceable == "true",
            fallback_mode=args.fallback_mode,
        )
        write_state_atomic(args.state, state)
        print(json.dumps(preflight_action(state), sort_keys=True))
        return 0

    if args.command == "bounded-policy":
        policy = bounded_lifecycle_policy(
            classification=args.classification,
            requirements_complete=args.requirements_complete,
            risk_tags=args.risk_tag,
        )
        print(json.dumps(policy, sort_keys=True))
        return 0

    state = _read_required_state(args.state)
    if args.command == "event":
        record_event(
            state,
            event=args.event,
            at=args.at,
            reason=args.reason,
            event_id=args.event_id,
        )
        write_state_atomic(args.state, state)
        print(json.dumps(state, ensure_ascii=False, sort_keys=True))
        return 0

    decision = decide_next_action(
        state,
        now=args.now,
        terminal_text=args.terminal_text,
        host_status=args.host_status,
        required_artifacts_verified=args.required_artifacts_verified,
        subprocess_running=args.subprocess_running,
        recent_progress=args.recent_progress,
    )
    print(json.dumps(decision, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
