#!/usr/bin/env python3
"""
telemetry-aggregate.py — Provider-neutral pipeline telemetry aggregator.

Purpose:
  Read per-task progress + cost state under ${STATE_DIR}/tasks/*/ and
  emit per-task and aggregate timing/throughput/cost metrics. Used by
  core/commands/telemetry.md to surface "where does the pipeline spend
  time" and "how often does it retry / get blocked" across runs.

  Read-only by design: never mutates state. Every input is a JSONL
  buffer or a register.json snapshot already written by the supervisor.

Inputs:
  --state-dir DIR     Override STATE_DIR resolution (default: env-derived).
  --task-id ID        Single-task report.
  --session-id ID     All tasks in one session.
  --recent N          N most-recently-modified task directories.
  --since YYYY-MM-DD  Lower bound on task STARTED ts.
  --until YYYY-MM-DD  Upper bound on task STARTED ts.
  --format text|json  Output format (default: text).

Outputs:
  text: aligned table on stdout — per-task lines + an aggregate footer.
  json: a single JSON object {tasks: [...], summary: {...}}.

Exit codes:
  0 — success (zero or more tasks reported).
  3 — invalid args, unreadable state dir, etc.

Sources walked per task:
  - {task_dir}/register.json            (Phase F4 — terminal state)
  - {task_dir}/progress.buffer.jsonl    (Phase F5 — structured events)
  - {state_dir}/cost/{task_id}.jsonl    (Phase 3.3 — per-call tokens)

Absence-tolerant: missing register.json / progress.buffer.jsonl / cost
file means "data not available" for that dimension, not "error". The
aggregator just records `null` for the missing metric and continues.

Metrics computed:
  - Per-task:
    - duration_seconds : STARTED → COMPLETED/blocked wall clock
    - stages_total     : count of PHASE/STAGE events
    - stages_completed : from register.json or pipeline.json
    - retries          : count of RETRY events
    - blockers         : list of BLOCKED detail strings
    - tokens_total     : sum of input + output (cache excluded)
    - status           : completed | blocked | running
    - current_phase    : from register.json
  - Aggregate:
    - tasks_total, tasks_completed, tasks_blocked, tasks_running
    - mean_duration_seconds, median_duration_seconds
    - total_retries, total_tokens
    - operational_quality: success/retry/hallucination-signal/rollback/
      human-intervention/tool-failure rates
    - by_phase_distribution (current_phase histogram)
    - by_blocker (blocked_by counter)
"""

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# --------------------------------------------------------------------------- #
# Resolvers                                                                   #
# --------------------------------------------------------------------------- #

def resolve_state_dir(override):
    if override:
        return Path(override)
    env = os.environ.get("AGENT_CREW_STATE_DIR")
    if env:
        return Path(env)
    home = os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew"))
    project = os.environ.get("AGENT_CREW_PROJECT", "default")
    return Path(home) / "state" / project


def parse_iso_ts(s):
    """Parse a few common ISO-8601 forms; return None on failure."""
    if not s:
        return None
    s = s.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_date_arg(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Per-task aggregation                                                        #
# --------------------------------------------------------------------------- #

def read_register(task_dir):
    p = task_dir / "register.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_task_project_root(task_dir):
    reg = read_register(task_dir) or {}
    value = str(reg.get("project_root") or "").strip()
    if value:
        return value
    return read_text_file(task_dir / "project-root.txt")


def normalize_project_root(value):
    if not value:
        return ""
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(value))))


def path_is_relative_to(path, parent):
    try:
        Path(path).relative_to(parent)
        return True
    except ValueError:
        return False


def task_matches_project_root(task_dir, project_root):
    """Keep legacy unknown-root tasks, but drop explicit foreign checkouts."""
    if not project_root:
        return True

    task_root = normalize_project_root(read_task_project_root(task_dir))
    if not task_root:
        return True

    current_root = normalize_project_root(project_root)
    if task_root == current_root:
        return True

    # Parallel supervisors can record their isolated worktree root while the
    # operator runs status from the main project checkout.
    crew_worktrees = Path(current_root) / ".crew-worktrees"
    if path_is_relative_to(task_root, crew_worktrees):
        return True

    return False


def read_progress_buffer(task_dir):
    """Yield normalized event rows from progress.buffer.jsonl."""
    p = task_dir / "progress.buffer.jsonl"
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def read_cost_file(state_dir, task_id):
    p = state_dir / "cost" / f"{task_id}.jsonl"
    if not p.is_file():
        return None
    total_in = total_out = 0
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        total_in += int(d.get("input_tokens") or 0)
        total_out += int(d.get("output_tokens") or 0)
    return {"tokens_in": total_in, "tokens_out": total_out,
            "tokens_total": total_in + total_out}


def read_tool_events(task_dir):
    p = task_dir / "tool-events.jsonl"
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append(row)
    return rows


def phase_runtime_metrics(events):
    """Compute per-phase runtime telemetry from progress buffer events."""
    metrics = []
    active = {}

    def close_metric(key, event, ts):
        current = active.pop(key, None)
        if not current:
            return
        duration = (ts - current["started_ts"]).total_seconds()
        metrics.append({
            "phase": current["phase"],
            "stage": current["stage"],
            "agent": current["agent"],
            "started": current["started"],
            "ended": event.get("ts"),
            "stage_duration_seconds": duration,
            "retries": current["retries"],
            "blocked_handoffs": current["blocked_handoffs"],
            "user_visible_wait_seconds": duration,
        })

    for event in events:
        name = event.get("event")
        ts = parse_iso_ts(event.get("ts", ""))
        if not ts:
            continue

        stage = int(event.get("stage") or 0)
        agent = event.get("agent") or ""
        key = (stage, agent)

        if name in ("STAGE", "PHASE"):
            if name == "PHASE":
                close_metric(key, event, ts)
            active[key] = {
                "phase": event.get("detail", "") or name.lower(),
                "stage": stage,
                "agent": agent,
                "started": event.get("ts"),
                "started_ts": ts,
                "retries": 0,
                "blocked_handoffs": 0,
            }
            continue

        current = active.get(key)
        if not current:
            continue

        if name == "RETRY":
            current["retries"] += 1
        elif name in ("BLOCKED", "COST_BLOCKED", "STAGE_TIMEOUT",
                      "STAGE_FANOUT_BLOCKED"):
            current["blocked_handoffs"] += 1
        elif name in ("STAGE_DONE", "COMPLETED", "STATUS"):
            close_metric(key, event, ts)

    return metrics


TASK_ID_RE = re.compile(r"^\d{8}-\d{6}(?:-\d+)?$")


def is_task_dir(path):
    """Return True for real task directories, excluding stray folders."""
    if TASK_ID_RE.match(path.name):
        return True
    markers = ("register.json", "pipeline.json", "result.md",
               "progress.buffer.jsonl", "progress.log")
    return any((path / marker).exists() for marker in markers)


RESULT_STATUS_RE = re.compile(
    r"^(?:\*\*)?status:\*{0,2}\s+\*{0,2}(\w+)\*{0,2}",
    re.IGNORECASE | re.MULTILINE,
)
RESULT_FIELD_RE = re.compile(
    r"^(?:\*\*)?(description|task|branch|blocker):\*{0,2}\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def read_result_md(task_dir):
    """Return terminal fields parsed from result.md, or {} when absent."""
    p = task_dir / "result.md"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}

    result = {}
    m = RESULT_STATUS_RE.search(text)
    if m:
        status = m.group(1).lower()
        if status == "completed":
            result["status"] = "completed"
            result["current_phase"] = "completed"
        elif status in ("blocked", "cancelled"):
            result["status"] = "blocked"
            result["current_phase"] = "blocked"
            if status == "cancelled":
                result["blockers"] = ["cancelled"]
        else:
            result["status"] = status

    for field, value in RESULT_FIELD_RE.findall(text):
        key = field.lower()
        value = value.strip().strip("*").strip()
        if key in ("description", "task") and value:
            result.setdefault("task", value)
        elif key == "branch" and value:
            result["branch"] = value
        elif key == "blocker" and value:
            result.setdefault("blockers", []).append(value)

    return result


def read_text_file(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""


def supervisor_boot_timeout_seconds():
    raw = os.environ.get("AGENT_CREW_SUPERVISOR_BOOT_TIMEOUT_SECONDS", "30")
    try:
        value = int(raw)
    except ValueError:
        value = 30
    return max(value, 0)


def stale_host_bridge_seconds():
    raw = os.environ.get("AGENT_CREW_STALE_HOST_BRIDGE_SECONDS", "600")
    try:
        value = int(raw)
    except ValueError:
        value = 600
    return max(value, 0)


def task_age_seconds(task_dir, started_ts):
    if started_ts:
        return max(0, int((datetime.now(timezone.utc) - started_ts).total_seconds()))
    try:
        mtime = datetime.fromtimestamp(task_dir.stat().st_mtime, tz=timezone.utc)
    except Exception:
        return 0
    return max(0, int((datetime.now(timezone.utc) - mtime).total_seconds()))


def missing_supervisor_boot_state(task_dir, *, has_register, has_events,
                                  has_result):
    """Classify task dirs created before supervisor Phase 0 produced state."""
    if has_register or has_events or has_result:
        return None

    pending = task_dir / "supervisor-pending.txt"
    task_txt = task_dir / "task.txt"
    if not pending.is_file() and not task_txt.is_file():
        return None

    marker = pending if pending.is_file() else task_txt
    age = max(0, int(datetime.now(timezone.utc).timestamp() -
                     marker.stat().st_mtime))
    timeout = supervisor_boot_timeout_seconds()
    if age >= timeout:
        return {
            "status": "blocked",
            "current_phase": "supervisor_handoff_stalled",
            "blockers": ["supervisor_handoff_not_started"],
            "age_seconds": age,
        }
    return {
        "status": "running",
        "current_phase": "supervisor_handoff_pending",
        "blockers": [],
        "age_seconds": age,
    }


def guidance_for(blockers, status, current_phase):
    guidance = []
    if status == "stale_blocked" or current_phase == "stale_host_bridge_fallback":
        guidance.append(
            "Stale host-bridge blocker excluded from current totals. Confirm "
            "the outcome, then run crew cleanup-host-bridge --apply or inspect "
            "context/stale-host-bridge-cleanup.json."
        )
    for blocker in blockers or []:
        b = str(blocker)
        if b == "host_bridge_not_invoked" or "host AI bridge" in b:
            guidance.append(
                "Host handoff is ready. Continue from task_dir/handoff.md, then "
                "run crew repair TASK_ID --status completed --note \"<summary>\"."
            )
        elif b == "supervisor_handoff_not_started":
            guidance.append(
                "Supervisor handoff stalled: supervisor did not produce progress "
                "artifacts. Check host agents, then re-run crew:run if needed."
            )
    if not guidance and current_phase == "supervisor_handoff_pending":
        guidance.append(
            "Supervisor boot is pending. Run crew status again shortly; if it "
            "exceeds the boot timeout, treat it as a host handoff stall."
        )
    if not guidance and status == "blocked":
        guidance.append("Inspect result.md and progress.log for the blocking reason.")
    return list(dict.fromkeys(guidance))


def canonical_blocker(blocker):
    """Normalize equivalent blocker labels for stable task/status summaries."""
    value = str(blocker or "").strip()
    if value == "stale_host_bridge_not_invoked":
        return "host_bridge_not_invoked"
    if value == "host_bridge_not_invoked" or "host AI bridge" in value:
        return "host_bridge_not_invoked"
    return value


def has_host_bridge_blocker(blockers):
    return any(canonical_blocker(blocker) == "host_bridge_not_invoked" for blocker in blockers)


def host_bridge_status(register):
    if not register:
        return "unknown"
    explicit = str(register.get("host_bridge_status") or "").strip()
    if explicit:
        return explicit
    if register.get("manual_fallback_repair_path"):
        return "manual_fallback_completed"
    return "unknown"


def aggregate_task(state_dir, task_dir):
    """Return a per-task dict with metrics + status. Robust to missing data."""
    task_id = task_dir.name
    reg = read_register(task_dir)
    events = read_progress_buffer(task_dir)
    tool_events = read_tool_events(task_dir)
    cost = read_cost_file(state_dir, task_id)
    result = read_result_md(task_dir)
    missing_boot = missing_supervisor_boot_state(
        task_dir,
        has_register=bool(reg),
        has_events=bool(events),
        has_result=bool(result),
    )

    terminal = next((e for e in reversed(events)
                     if e.get("event") in ("COMPLETED", "BLOCKED",
                                           "COST_BLOCKED", "STATUS")), None)

    # Status / current phase. result.md is the strongest terminal signal:
    # older or interrupted runs can leave register.json stuck at phase_0 even
    # after writing a completed/blocked result.
    if missing_boot:
        status = missing_boot["status"]
        current_phase = missing_boot["current_phase"]
        blocked_by = missing_boot["blockers"]
        stages_completed = None
    elif result.get("status") == "completed":
        status = "completed"
        current_phase = result.get("current_phase", status)
        # A completed result.md is authoritative. Older runs can leave
        # register.json stuck at blocked with stale blocker labels; carrying
        # those forward produces false host-bridge guidance.
        blocked_by = list(result.get("blockers", []))
        stages_completed = None
    elif result.get("status") == "blocked":
        status = result["status"]
        current_phase = result.get("current_phase", status)
        blocked_by = list(result.get("blockers", []))
        if reg:
            for blocker in reg.get("blocked_by", []) or []:
                if blocker not in blocked_by:
                    blocked_by.append(blocker)
        stages_completed = None
    elif reg:
        status_value = reg.get("current_phase", "")
        if status_value == "completed":
            status = "completed"
        elif status_value == "blocked":
            status = "blocked"
        elif status_value:
            status = "running"
        else:
            status = "unknown"
        current_phase = reg.get("current_phase", "")
        blocked_by = reg.get("blocked_by", []) or []
        stages_completed = None  # filled from pipeline.json below
    elif terminal:
        if terminal["event"] == "COMPLETED":
            status = "completed"
            current_phase = "completed"
            blocked_by = []
        else:
            status = "blocked"
            current_phase = "blocked"
            blocked_by = [terminal.get("detail", "")[:80]]
        stages_completed = None
    else:
        status = "running"
        current_phase = ""
        blocked_by = []
        stages_completed = None

    # Timing from events.
    started = next((e for e in events if e.get("event") == "STARTED"), None)
    duration_seconds = None
    started_ts = None
    if started:
        started_ts = parse_iso_ts(started.get("ts", ""))
        if terminal and started_ts:
            end_ts = parse_iso_ts(terminal.get("ts", ""))
            if end_ts:
                duration_seconds = (end_ts - started_ts).total_seconds()
    age_seconds = task_age_seconds(task_dir, started_ts)
    stale_seconds = stale_host_bridge_seconds()
    stale_host_bridge = (
        status == "blocked"
        and stale_seconds > 0
        and has_host_bridge_blocker(blocked_by)
        and age_seconds >= stale_seconds
    )
    if stale_host_bridge:
        status = "stale_blocked"
        current_phase = "stale_host_bridge_fallback"
        blocked_by = ["stale_host_bridge_not_invoked"]

    # Stage / retry counts from events.
    stages_total = sum(1 for e in events if e.get("event") == "STAGE")
    retries = sum(1 for e in events if e.get("event") == "RETRY")
    phase_metrics = phase_runtime_metrics(events)
    blocked_handoffs = sum(m["blocked_handoffs"] for m in phase_metrics)
    user_visible_wait_seconds = sum(
        m["user_visible_wait_seconds"] for m in phase_metrics
        if m["user_visible_wait_seconds"] is not None
    ) if phase_metrics else duration_seconds

    # Stages completed from pipeline.json (more reliable than counting events).
    pipeline_path = task_dir / "pipeline.json"
    if pipeline_path.is_file():
        try:
            pipe = json.loads(pipeline_path.read_text(encoding="utf-8"))
            stages_completed = int(pipe.get("completed_stages") or 0)
        except Exception:
            pass

    # Compose row.
    task_field = ""
    if reg:
        task_field = reg.get("task", "")
    if not task_field:
        task_field = result.get("task", "")
    if not task_field and started:
        task_field = started.get("detail", "")
    if not task_field:
        task_field = read_text_file(task_dir / "task.txt")

    return {
        "task_id":           task_id,
        "task":              task_field,
        "status":            status,
        "current_phase":     current_phase,
        "duration_seconds":  duration_seconds,
        "age_seconds":       age_seconds,
        "stale_blocker":     stale_host_bridge,
        "started":           started.get("ts") if started else None,
        "stages_total":      stages_total,
        "stages_completed":  stages_completed,
        "retries":           retries,
        "phase_metrics":     phase_metrics,
        "blocked_handoffs":  blocked_handoffs,
        "user_visible_wait_seconds": user_visible_wait_seconds,
        "blockers":          blocked_by,
        "guidance":          guidance_for(blocked_by, status, current_phase),
        "host_bridge_status": host_bridge_status(reg),
        "tool_events_total": len(tool_events),
        "tool_failures_total": sum(1 for e in tool_events if e.get("status") == "failed"),
        "tokens_in":         (cost or {}).get("tokens_in"),
        "tokens_out":        (cost or {}).get("tokens_out"),
        "tokens_total":      (cost or {}).get("tokens_total"),
    }


# --------------------------------------------------------------------------- #
# Task selection                                                              #
# --------------------------------------------------------------------------- #

def list_task_dirs(state_dir, args):
    tasks_root = state_dir / "tasks"
    if not tasks_root.is_dir():
        return []
    candidates = [p for p in tasks_root.iterdir()
                  if p.is_dir() and is_task_dir(p)]

    # Sort by mtime descending for --recent and stable ordering.
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if args.project_root:
        candidates = [
            p for p in candidates
            if task_matches_project_root(p, args.project_root)
        ]

    if args.task_id:
        return [p for p in candidates if p.name == args.task_id]

    if args.session_id:
        sid = args.session_id
        # session_id is the {YYYYMMDD-HHMMSS} prefix of task_id ("...-0", "...-1").
        return [p for p in candidates if p.name.startswith(sid)]

    if args.recent is not None and args.recent > 0:
        candidates = candidates[: args.recent]

    since_dt = parse_date_arg(args.since)
    until_dt = parse_date_arg(args.until)
    if since_dt or until_dt:
        kept = []
        for p in candidates:
            # Use task_id's date prefix when available.
            try:
                date_part = p.name.split("-")[0]
                ts = datetime.strptime(date_part, "%Y%m%d").replace(
                    tzinfo=timezone.utc)
            except Exception:
                ts = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if since_dt and ts < since_dt:
                continue
            if until_dt and ts > until_dt:
                continue
            kept.append(p)
        candidates = kept

    return candidates


# --------------------------------------------------------------------------- #
# Aggregate summary                                                           #
# --------------------------------------------------------------------------- #

def aggregate_summary(rows):
    total = len(rows)
    completed = sum(1 for r in rows if r["status"] == "completed")
    blocked = sum(1 for r in rows if r["status"] == "blocked")
    stale_blocked = sum(1 for r in rows if r["status"] == "stale_blocked")
    running = sum(1 for r in rows if r["status"] == "running")

    durations = [r["duration_seconds"] for r in rows
                 if r["duration_seconds"] is not None]
    total_retries = sum(r["retries"] for r in rows)
    total_tokens = sum(r["tokens_total"] for r in rows
                       if r["tokens_total"] is not None)
    total_tool_events = sum(r.get("tool_events_total", 0) for r in rows)
    total_tool_failures = sum(r.get("tool_failures_total", 0) for r in rows)

    by_phase = Counter(r["current_phase"] for r in rows if r["current_phase"])
    by_host_bridge_status = Counter(
        r.get("host_bridge_status", "unknown")
        for r in rows
        if r.get("host_bridge_status")
    )
    by_blocker = Counter()
    by_stale_blocker = Counter()
    for r in rows:
        seen_blockers = set()
        for b in r["blockers"]:
            blocker = canonical_blocker(b)
            if not blocker or blocker in seen_blockers:
                continue
            seen_blockers.add(blocker)
            if r["status"] == "stale_blocked" or r.get("stale_blocker"):
                by_stale_blocker[blocker] += 1
                continue
            by_blocker[blocker] += 1

    return {
        "tasks_total":             total,
        "tasks_completed":         completed,
        "tasks_blocked":           blocked,
        "tasks_stale_blocked":     stale_blocked,
        "tasks_running":           running,
        "mean_duration_seconds":   (statistics.mean(durations)
                                    if durations else None),
        "median_duration_seconds": (statistics.median(durations)
                                    if durations else None),
        "total_retries":           total_retries,
        "total_tokens":            total_tokens,
        "total_tool_events":       total_tool_events,
        "total_tool_failures":     total_tool_failures,
        "by_phase":                dict(by_phase),
        "by_host_bridge_status":   dict(by_host_bridge_status),
        "by_blocker":              dict(by_blocker),
        "by_stale_blocker":        dict(by_stale_blocker),
        "operational_quality":     operational_quality_metrics(rows),
    }


def rate(numerator, denominator):
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def row_signal_text(row):
    return " ".join(
        [str(row.get("task") or ""), *[str(b) for b in row.get("blockers", [])]]
    ).lower()


def has_hallucination_signal(row):
    text = row_signal_text(row)
    return "hallucination" in text or "환각" in text


def has_rollback_signal(row):
    text = row_signal_text(row)
    return any(token in text for token in ("rollback", "roll back", "revert", "롤백", "되돌리"))


def has_human_intervention_signal(row):
    host_status = str(row.get("host_bridge_status") or "")
    return host_status.startswith("manual_fallback_")


def operational_quality_metrics(rows):
    current_rows = [
        r for r in rows
        if r.get("status") not in {"running", "stale_blocked"}
    ]
    denominator = len(current_rows)
    completed = sum(1 for r in current_rows if r.get("status") == "completed")
    retried = sum(1 for r in current_rows if int(r.get("retries") or 0) > 0)
    hallucination = sum(1 for r in current_rows if has_hallucination_signal(r))
    rollback = sum(1 for r in current_rows if has_rollback_signal(r))
    human = sum(1 for r in current_rows if has_human_intervention_signal(r))
    tool_failures = sum(int(r.get("tool_failures_total") or 0) for r in current_rows)
    tool_events = sum(int(r.get("tool_events_total") or 0) for r in current_rows)

    return {
        "denominator_tasks": denominator,
        "success_rate": rate(completed, denominator),
        "retry_rate": rate(retried, denominator),
        "hallucination_signal_rate": rate(hallucination, denominator),
        "rollback_frequency": rollback,
        "rollback_rate": rate(rollback, denominator),
        "human_intervention_rate": rate(human, denominator),
        "tool_failure_rate": rate(tool_failures, tool_events),
        "tasks_with_retry": retried,
        "hallucination_signal_tasks": hallucination,
        "human_intervention_tasks": human,
        "tool_failures": tool_failures,
        "tool_events": tool_events,
    }


def stale_state_counts(state_dir):
    tasks_root = state_dir / "tasks"
    counts = {
        "stale_active_markers": 0,
        "stale_supervisor_pending_sentinels": 0,
    }
    if not tasks_root.is_dir():
        return counts
    counts["stale_active_markers"] = sum(
        1 for path in tasks_root.glob("active*") if path.is_file()
    )
    counts["stale_supervisor_pending_sentinels"] = sum(
        1 for path in tasks_root.glob("*/supervisor-pending.txt") if path.is_file()
    )
    return counts


# --------------------------------------------------------------------------- #
# Output                                                                      #
# --------------------------------------------------------------------------- #

def format_duration(seconds):
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"
    return f"{int(seconds // 3600)}h{int((seconds % 3600) // 60):02d}m"


def format_tokens(n):
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def format_rate(value):
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def render_text(rows, summary):
    if not rows:
        print("(no tasks matched)")
        return

    header = (
        f"{'TASK ID':<24}  {'STATUS':<10}  {'PHASE':<14}  "
        f"{'DUR':>8}  {'STAGES':>7}  {'RETRY':>5}  {'TOKENS':>7}  "
        f"TASK"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        stages_disp = "—" if r["stages_completed"] is None \
                      else f"{r['stages_completed']}/{r['stages_total'] or '?'}"
        task_disp = (r["task"] or "")[:60]
        print(
            f"{r['task_id']:<24}  "
            f"{r['status']:<10}  "
            f"{(r['current_phase'] or '—'):<14}  "
            f"{format_duration(r['duration_seconds']):>8}  "
            f"{stages_disp:>7}  "
            f"{r['retries']:>5}  "
            f"{format_tokens(r['tokens_total']):>7}  "
            f"{task_disp}"
        )
    print()
    print(f"Tasks: {summary['tasks_total']} total | "
          f"{summary['tasks_completed']} completed | "
          f"{summary['tasks_blocked']} blocked | "
          f"{summary.get('tasks_stale_blocked', 0)} stale-blocked | "
          f"{summary['tasks_running']} running")
    print(f"Duration (completed): "
          f"mean={format_duration(summary['mean_duration_seconds'])}, "
          f"median={format_duration(summary['median_duration_seconds'])}")
    print(f"Retries: {summary['total_retries']} total | "
          f"Tokens: {format_tokens(summary['total_tokens'])} total")
    print(f"Tool events: {summary.get('total_tool_events', 0)} total | "
          f"{summary.get('total_tool_failures', 0)} failed")
    quality = summary.get("operational_quality") or {}
    if quality:
        print(
            "Operational quality: "
            f"success_rate={format_rate(quality.get('success_rate'))} | "
            f"retry_rate={format_rate(quality.get('retry_rate'))} | "
            f"human_intervention_rate={format_rate(quality.get('human_intervention_rate'))} | "
            f"rollback_frequency={quality.get('rollback_frequency', 0)} | "
            f"hallucination_signal_rate={format_rate(quality.get('hallucination_signal_rate'))}"
        )
    stale_counts = summary.get("stale_state_counts") or {}
    if stale_counts:
        print(
            "Stale state markers: "
            f"active={stale_counts.get('stale_active_markers', 0)} | "
            f"supervisor-pending={stale_counts.get('stale_supervisor_pending_sentinels', 0)}"
        )
    if summary["by_blocker"]:
        bk = ", ".join(f"{k}={v}" for k, v in summary["by_blocker"].items())
        print(f"Blockers: {bk}")
    if summary.get("by_host_bridge_status"):
        hb = ", ".join(f"{k}={v}" for k, v in summary["by_host_bridge_status"].items())
        print(f"Host bridge: {hb}")
    if summary.get("by_stale_blocker"):
        bk = ", ".join(f"{k}={v}" for k, v in summary["by_stale_blocker"].items())
        print(f"Stale blockers: {bk}")
    guidance_rows = [
        (r["task_id"], r["guidance"])
        for r in rows
        if r.get("guidance")
    ]
    if guidance_rows:
        print("Guidance:")
        for task_id, guidance in guidance_rows:
            print(f"  {task_id}: {' '.join(guidance)}")


# --------------------------------------------------------------------------- #
# Driver                                                                      #
# --------------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(
        description="agent-crew pipeline telemetry aggregator")
    p.add_argument("--state-dir")
    p.add_argument("--task-id")
    p.add_argument("--session-id")
    p.add_argument("--recent", type=int, default=10,
                   help="N most-recent task directories (default 10; "
                        "ignored when --task-id or --session-id given)")
    p.add_argument("--project-root",
                   help="Current project root; excludes task records that "
                        "explicitly belong to another checkout with the same "
                        "basename")
    p.add_argument("--since", help="YYYY-MM-DD lower bound on task start date")
    p.add_argument("--until", help="YYYY-MM-DD upper bound on task start date")
    p.add_argument("--format", choices=["text", "json"], default="text")
    args = p.parse_args()

    state_dir = resolve_state_dir(args.state_dir)
    if not state_dir.is_dir():
        print(f"error: state dir not found: {state_dir}", file=sys.stderr)
        return 3

    task_dirs = list_task_dirs(state_dir, args)
    rows = [aggregate_task(state_dir, p) for p in task_dirs]
    # Order by start time ascending in output (most chronologically natural).
    rows.sort(key=lambda r: r["started"] or "")
    summary = aggregate_summary(rows)
    summary["stale_state_counts"] = stale_state_counts(state_dir)

    if args.format == "json":
        payload = {
            "state_dir": str(state_dir),
            "tasks":     rows,
            "summary":   summary,
        }
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        render_text(rows, summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
