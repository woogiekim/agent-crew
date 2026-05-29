#!/usr/bin/env python3
"""
smm-aggregate.py — Provider-neutral Shared Mental Model (SMM) single-view.

Purpose:
  Stitch the five currently-fragmented per-task state sources under
  ${STATE_DIR}/tasks/{TASK_ID}/ into one coherent read-only surface, so an
  operator (or a downstream agent) sees the WHOLE pipeline state at a glance
  without opening five files:
    - pipeline.json          (execution graph: stages / completed_stages)
    - progress.log           (human-readable event log)
    - progress.buffer.jsonl  (structured event buffer)
    - register.json          (slim state pointer: phase / approval / verify)
    - handoff.md             (freeform stage handoff narrative)

  Issue #129 Finding #2. crew:status already renders a compact snapshot and
  telemetry-aggregate.py produces a metrics table, but neither unites the whole
  SMM for a task as one block, and neither reads handoff.md. This script adds
  the missing single-view; it is an enriched, on-demand crew:status with clear
  per-task sections for N>1 interleaved parallel runs.

  READ-ONLY by design — named as a renderer (NOT repair-*/update-*) per
  core/scripts/README.md. It reuses telemetry-aggregate.py readers (no net-new
  schema) and never mutates, creates, or deletes any state file.

Inputs:
  --state-dir DIR     Override STATE_DIR resolution (default: env-derived).
  --task-id ID        Single-task view.
  --session-id ID     All tasks in one session.
  --recent N          N most-recently-modified task directories (default 10).
  --project-root P    Exclude task records belonging to another checkout.
  --format text|json  Output format (default: text).

Selection precedence (same as telemetry-aggregate.py):
  --task-id > --session-id > --recent N.

Outputs:
  text: one coherent SMM block per task (session header when len > 1).
  json: {"state_dir": str, "tasks": [<smm dict>, ...]}.

Exit codes:
  0 — success (including zero tasks).
  3 — invalid args / unreadable state dir (matches telemetry-aggregate.py).

Example:
  smm-aggregate.py --state-dir ~/.agent-crew/state/myproj --recent 5
  smm-aggregate.py --task-id 20260529-183718-0 --format json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def _load_telemetry():
    """Import telemetry-aggregate.py by file path to reuse its readers.

    The module name has a hyphen, so it cannot be imported with a plain
    `import`. This mirrors how tests/python/test_telemetry_aggregate.py loads
    it, and keeps SMM free of any duplicated schema/reader logic.
    """
    path = SCRIPT_DIR / "telemetry-aggregate.py"
    spec = importlib.util.spec_from_file_location("telemetry_aggregate", path)
    if not spec or not spec.loader:
        raise ImportError(f"cannot load telemetry-aggregate.py at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("telemetry_aggregate", module)
    spec.loader.exec_module(module)
    return module


telemetry = _load_telemetry()


# --------------------------------------------------------------------------- #
# handoff.md reader — the one source telemetry-aggregate.py does NOT read      #
# --------------------------------------------------------------------------- #

HANDOFF_EXCERPT_LINES = 40


def read_handoff(task_dir):
    """Render handoff.md as a bounded, never-parsed excerpt + heading map.

    Returns a dict with keys (always present):
      present  : bool   — file exists and is readable.
      lines    : int    — total line count (0 when absent).
      headings : [str]  — markdown heading texts (no leading '#'), in order.
      excerpt  : str    — first HANDOFF_EXCERPT_LINES lines joined (bounded).

    Absent / unreadable file degrades to the documented empty defaults; never
    raises. handoff.md is freeform markdown with no schema, so this is a
    bounded render, not a semantic parse.
    """
    empty = {"present": False, "lines": 0, "headings": [], "excerpt": ""}

    path = Path(task_dir) / "handoff.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return empty

    all_lines = text.splitlines()

    headings = []
    for line in all_lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            if heading_text:
                headings.append(heading_text)

    excerpt = "\n".join(all_lines[:HANDOFF_EXCERPT_LINES])

    return {
        "present": True,
        "lines": len(all_lines),
        "headings": headings,
        "excerpt": excerpt,
    }


# --------------------------------------------------------------------------- #
# Stage list — derive per-stage done/current/pending markers                  #
# --------------------------------------------------------------------------- #

def _stage_agents(stage):
    """Normalize a pipeline.json stage entry to its agent-name list."""
    if isinstance(stage, str):
        return [stage]
    if isinstance(stage, list):
        return list(stage)
    if isinstance(stage, dict):
        return list(stage.get("agents", []) or [])
    return []


def _read_pipeline(task_dir):
    """Return (stages_total, stages_completed, stage_list, present)."""
    path = Path(task_dir) / "pipeline.json"
    try:
        pipe = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0, 0, [], False

    stages = pipe.get("stages", []) or []
    completed = int(pipe.get("completed_stages") or 0)

    stage_list = []
    for idx, stage in enumerate(stages):
        index = idx + 1
        if index <= completed:
            marker = "done"
        elif index == completed + 1:
            marker = "current"
        else:
            marker = "pending"
        stage_list.append({
            "index": index,
            "agents": _stage_agents(stage),
            "marker": marker,
        })

    return len(stages), completed, stage_list, True


# --------------------------------------------------------------------------- #
# Recent events — last up to 5 from progress.buffer.jsonl (log fallback)      #
# --------------------------------------------------------------------------- #

RECENT_EVENT_LIMIT = 5


def _read_recent_events(task_dir):
    """Return (events, buffer_present, log_present).

    Each event is {"ts","event","detail"}; up to RECENT_EVENT_LIMIT, newest
    last. Prefers the structured buffer (Phase F5); falls back to progress.log.
    """
    task_dir = Path(task_dir)
    buffer_present = (task_dir / "progress.buffer.jsonl").is_file()
    log_present = (task_dir / "progress.log").is_file()

    rows = telemetry.read_progress_buffer(task_dir)
    if not rows:
        rows = telemetry.read_progress_log(task_dir)

    tail = rows[-RECENT_EVENT_LIMIT:] if rows else []
    events = [
        {
            "ts": r.get("ts", ""),
            "event": r.get("event", ""),
            "detail": r.get("detail", ""),
        }
        for r in tail
    ]
    return events, buffer_present, log_present


# --------------------------------------------------------------------------- #
# build_smm — one coherent SMM dict per task                                  #
# --------------------------------------------------------------------------- #

def build_smm(state_dir, task_dir):
    """Build a single coherent SMM dict for one task.

    Every documented key is always present. No source read may raise — a
    missing or malformed source falls back to its empty default and flips the
    matching sources_present flag to False.

    Status / task / blockers reuse telemetry-aggregate.py's aggregate_task(),
    which already fuses result.md + register.json + the event buffer with the
    correct terminal-state precedence. No schema is re-derived here.
    """
    state_dir = Path(state_dir)
    task_dir = Path(task_dir)

    # Reuse telemetry's fused per-task row (status, task, branch, blockers).
    try:
        row = telemetry.aggregate_task(state_dir, task_dir)
    except Exception:
        row = {}

    register = telemetry.read_register(task_dir) or {}
    register_present = (task_dir / "register.json").is_file()

    stages_total, stages_completed, stage_list, pipeline_present = \
        _read_pipeline(task_dir)

    recent_events, buffer_present, log_present = _read_recent_events(task_dir)

    handoff = read_handoff(task_dir)

    branch = str(register.get("branch") or row.get("branch") or "")

    status = row.get("status") or "unknown"
    if status not in ("completed", "blocked", "cancelled", "running", "unknown"):
        status = "running"

    return {
        "task_id": task_dir.name,
        "task": row.get("task") or register.get("task") or "",
        "branch": branch,
        "status": status,
        "current_phase": str(register.get("current_phase") or ""),
        "approval_status": str(register.get("approval_status") or "not_required"),
        "verification_status": str(register.get("verification_status")
                                   or "not_started"),
        "stages_total": stages_total,
        "stages_completed": stages_completed,
        "stage_list": stage_list,
        "modified_files": list(register.get("modified_files") or []),
        "blocked_by": list(register.get("blocked_by")
                           or row.get("blockers") or []),
        "recent_events": recent_events,
        "handoff": handoff,
        "sources_present": {
            "pipeline": pipeline_present,
            "progress_log": log_present,
            "progress_buffer": buffer_present,
            "register": register_present,
            "handoff": handoff["present"],
        },
    }


# --------------------------------------------------------------------------- #
# render_text — human-readable single-view                                    #
# --------------------------------------------------------------------------- #

_MARKER_GLYPH = {"done": "[x]", "current": "[>]", "pending": "[ ]"}

BLOCK_DELIM = "─" * 72


def _render_block(smm):
    """Render one task's SMM as a clearly-delimited text block."""
    lines = []
    lines.append(f"Task    : {smm['task_id']}")
    if smm.get("task"):
        lines.append(f"          {smm['task']}")
    lines.append(f"Branch  : {smm['branch'] or '—'}")
    lines.append(f"Status  : {smm['status']}")
    lines.append(f"Phase   : {smm['current_phase'] or '—'}")
    lines.append(f"Approval: {smm['approval_status']}    "
                 f"Verify: {smm['verification_status']}")

    lines.append(f"Stages  : {smm['stages_completed']}/{smm['stages_total']}")
    for stage in smm["stage_list"]:
        glyph = _MARKER_GLYPH.get(stage["marker"], "[ ]")
        agents = ", ".join(stage["agents"]) or "?"
        suffix = "  ← current" if stage["marker"] == "current" else ""
        lines.append(f"  {glyph} {stage['index']}. {agents}{suffix}")

    if smm["modified_files"]:
        lines.append(f"Files   : {len(smm['modified_files'])} modified")
        for f in smm["modified_files"]:
            lines.append(f"  - {f}")

    if smm["blocked_by"]:
        lines.append(f"Blocked : {', '.join(str(b) for b in smm['blocked_by'])}")

    handoff = smm["handoff"]
    if handoff["present"]:
        head_summary = "; ".join(handoff["headings"][:6]) or "(no headings)"
        lines.append(f"Handoff : {handoff['lines']} lines | {head_summary}")
    else:
        lines.append("Handoff : (handoff not produced yet)")

    if smm["recent_events"]:
        lines.append("Recent  :")
        for ev in smm["recent_events"]:
            detail = str(ev.get("detail") or "")
            if len(detail) > 60:
                detail = detail[:57].rstrip() + "..."
            lines.append(f"  {ev.get('ts', '')} | {ev.get('event', '')} | {detail}")

    return "\n".join(lines)


def render_text(smm_list):
    """Render a list of SMM dicts to a human-readable string.

    - Empty input → a string containing "(no tasks matched)".
    - len > 1 → a session header line containing the substring "tasks" and the
      count, then one delimited block per task so interleaved N>1 runs read
      cleanly.
    - Absent handoff renders the literal "(handoff not produced yet)" token.
    """
    if not smm_list:
        return "(no tasks matched)"

    parts = []

    if len(smm_list) > 1:
        parts.append(f"Shared Mental Model — {len(smm_list)} tasks")
        parts.append(BLOCK_DELIM)

    for idx, smm in enumerate(smm_list):
        parts.append(_render_block(smm))
        if idx != len(smm_list) - 1:
            parts.append(BLOCK_DELIM)

    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Driver                                                                      #
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="agent-crew Shared Mental Model (SMM) single-view "
                    "(read-only aggregated crew:status)")
    parser.add_argument("--state-dir")
    parser.add_argument("--task-id")
    parser.add_argument("--session-id")
    parser.add_argument("--recent", type=int, default=10,
                        help="N most-recent task directories (default 10; "
                             "ignored when --task-id or --session-id given)")
    parser.add_argument("--project-root",
                        help="Current project root; excludes task records that "
                             "explicitly belong to another checkout")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state_dir = telemetry.resolve_state_dir(args.state_dir)
    if not state_dir.is_dir():
        print(f"error: state dir not found: {state_dir}", file=sys.stderr)
        return 3

    task_dirs = telemetry.list_task_dirs(state_dir, args)
    smm_list = [build_smm(state_dir, td) for td in task_dirs]
    # Order by task_id ascending (chronological by construction).
    smm_list.sort(key=lambda s: s["task_id"])

    if args.format == "json":
        payload = {"state_dir": str(state_dir), "tasks": smm_list}
        json.dump(payload, sys.stdout, indent=2, default=str, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(render_text(smm_list))

    return 0


if __name__ == "__main__":
    sys.exit(main())
