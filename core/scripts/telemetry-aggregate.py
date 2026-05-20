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
    for blocker in blockers or []:
        b = str(blocker)
        if b == "host_bridge_not_invoked" or "host AI bridge" in b:
            guidance.append(
                "Host handoff is ready, but execution has not happened in the "
                "AI prompt runtime. Invoke the host bridge or inspect handoff.md."
            )
        elif b == "supervisor_handoff_not_started":
            guidance.append(
                "The orchestrator created task state, but the supervisor did "
                "not produce progress artifacts. Check host agent availability "
                "and re-run crew:run with this task context if needed."
            )
    if not guidance and current_phase == "supervisor_handoff_pending":
        guidance.append(
            "Supervisor boot is pending; run crew status again shortly. If it "
            "exceeds AGENT_CREW_SUPERVISOR_BOOT_TIMEOUT_SECONDS, treat it as a "
            "host handoff stall."
        )
    if not guidance and status == "blocked":
        guidance.append("Inspect result.md and progress.log for the blocking reason.")
    return guidance


def aggregate_task(state_dir, task_dir):
    """Return a per-task dict with metrics + status. Robust to missing data."""
    task_id = task_dir.name
    reg = read_register(task_dir)
    events = read_progress_buffer(task_dir)
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
    elif result.get("status") in ("completed", "blocked"):
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

    # Stage / retry counts from events.
    stages_total = sum(1 for e in events if e.get("event") == "STAGE")
    retries = sum(1 for e in events if e.get("event") == "RETRY")

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
        "started":           started.get("ts") if started else None,
        "stages_total":      stages_total,
        "stages_completed":  stages_completed,
        "retries":           retries,
        "blockers":          blocked_by,
        "guidance":          guidance_for(blocked_by, status, current_phase),
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
            reg = read_register(p)
            ts = parse_iso_ts((reg or {}).get("schema_version", "") and
                              p.stat().st_mtime)  # fallback to mtime
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
    running = sum(1 for r in rows if r["status"] == "running")

    durations = [r["duration_seconds"] for r in rows
                 if r["duration_seconds"] is not None]
    total_retries = sum(r["retries"] for r in rows)
    total_tokens = sum(r["tokens_total"] for r in rows
                       if r["tokens_total"] is not None)

    by_phase = Counter(r["current_phase"] for r in rows if r["current_phase"])
    by_blocker = Counter()
    for r in rows:
        for b in r["blockers"]:
            by_blocker[b] += 1

    return {
        "tasks_total":             total,
        "tasks_completed":         completed,
        "tasks_blocked":           blocked,
        "tasks_running":           running,
        "mean_duration_seconds":   (statistics.mean(durations)
                                    if durations else None),
        "median_duration_seconds": (statistics.median(durations)
                                    if durations else None),
        "total_retries":           total_retries,
        "total_tokens":            total_tokens,
        "by_phase":                dict(by_phase),
        "by_blocker":              dict(by_blocker),
    }


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
          f"{summary['tasks_running']} running")
    print(f"Duration (completed): "
          f"mean={format_duration(summary['mean_duration_seconds'])}, "
          f"median={format_duration(summary['median_duration_seconds'])}")
    print(f"Retries: {summary['total_retries']} total | "
          f"Tokens: {format_tokens(summary['total_tokens'])} total")
    if summary["by_blocker"]:
        bk = ", ".join(f"{k}={v}" for k, v in summary["by_blocker"].items())
        print(f"Blockers: {bk}")
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
