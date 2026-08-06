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
from collections import Counter
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


def _stage_parallelizable_units(stage):
    if not isinstance(stage, dict):
        return []
    units = stage.get("parallelizable_units") or []
    return [unit for unit in units if isinstance(unit, dict)]


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
            "tdd_parallel": bool(stage.get("tdd_parallel")) if isinstance(stage, dict) else False,
            "streaming_review": bool(stage.get("streaming_review")) if isinstance(stage, dict) else False,
            "qa_mode": str(stage.get("qa_mode") or "") if isinstance(stage, dict) else "",
            "parallelizable_units": [
                {
                    "id": str(unit.get("id") or ""),
                    "files": list(unit.get("files") or []),
                    "brief": str(unit.get("brief") or ""),
                }
                for unit in _stage_parallelizable_units(stage)
            ],
        })

    return len(stages), completed, stage_list, True


# --------------------------------------------------------------------------- #
# Orchestration summary — Memory / DAG / Inbox / Evolution                   #
# --------------------------------------------------------------------------- #

def _read_json_document(path):
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, False, False
    except Exception:
        return {}, path.exists(), False
    return payload if isinstance(payload, dict) else {}, True, isinstance(payload, dict)


def _existing_artifacts(task_dir, rel_paths):
    task_dir = Path(task_dir)
    return [rel for rel in rel_paths if (task_dir / rel).is_file()]


def _state_artifact_present(state_dir, rel_path):
    return (Path(state_dir) / rel_path).is_file()


def _read_jsonl_file(path):
    rows = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _retrieval_rows(retrieval):
    rows = retrieval.get("results")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    provider = retrieval.get("provider_response")
    if isinstance(provider, dict):
        rows = provider.get("results")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _read_memory_orchestration(task_dir):
    context_dir = Path(task_dir) / "context"
    retrieval, retrieval_present, retrieval_valid = _read_json_document(
        context_dir / "memory-retrieval.json"
    )
    usage, usage_present, usage_valid = _read_json_document(
        context_dir / "memory-usage.json"
    )
    feedback, _, _ = _read_json_document(context_dir / "memory-feedback.json")

    decisions = [
        row for row in usage.get("decisions", [])
        if isinstance(row, dict)
    ]
    dispositions = Counter(str(row.get("disposition") or "") for row in decisions)
    retrieved = len(_retrieval_rows(retrieval))
    applied = int(dispositions.get("applied", 0))
    ignored = int(dispositions.get("ignored", 0))
    feedback_sent = len(feedback.get("sent_events") or []) \
        if isinstance(feedback.get("sent_events"), list) else 0
    feedback_failed = len(feedback.get("failed_events") or []) \
        if isinstance(feedback.get("failed_events"), list) else 0
    retrieval_status = str(retrieval.get("status") or "not_present")

    if retrieval_present and not retrieval_valid:
        next_action = "inspect_memory_retrieval"
    elif retrieval_status == "disabled":
        next_action = "memory_disabled"
    elif retrieval_status in ("unavailable", "timeout", "invalid_json",
                              "incompatible_provider", "degraded"):
        next_action = "continue_without_memory"
    elif retrieval_status == "no_results":
        next_action = "no_memory_results"
    elif not retrieval_present:
        next_action = "no_memory_context"
    elif usage_present and not usage_valid:
        next_action = "inspect_memory_usage"
    elif retrieval_status == "ok" and retrieved == 0:
        next_action = "no_memory_results"
    elif retrieved > 0 and not usage_present:
        next_action = "review_memory_usage"
    elif feedback_failed > 0:
        next_action = "review_memory_feedback_failure"
    elif applied > 0 and feedback_sent == 0:
        next_action = "review_memory_feedback"
    else:
        next_action = "memory_context_available"

    return {
        "retrieval_status": retrieval_status,
        "retrieved": retrieved,
        "applied": applied,
        "ignored": ignored,
        "feedback_sent": feedback_sent,
        "feedback_failed": feedback_failed,
        "artifacts": _existing_artifacts(task_dir, [
            "context/memory-retrieval.json",
            "context/memory-usage.json",
            "context/memory-feedback.json",
        ]),
        "next_action": next_action,
    }


def _read_dag_orchestration(task_dir, stage_list, pipeline_present):
    current = next((stage for stage in stage_list if stage["marker"] == "current"), {})
    parallel_units = sum(len(stage.get("parallelizable_units") or []) for stage in stage_list)
    if not pipeline_present:
        next_action = "inspect_pipeline"
    elif stage_list and not current:
        next_action = "pipeline_complete"
    elif current:
        next_action = "continue_current_stage"
    elif parallel_units:
        next_action = "review_parallel_units"
    else:
        next_action = "inspect_pipeline"
    return {
        "stages": len(stage_list),
        "current_stage": current.get("index", 0) if current else 0,
        "current_stage_agents": list(current.get("agents") or []),
        "parallel_units": parallel_units,
        "tdd_parallel_stages": sum(1 for stage in stage_list if stage.get("tdd_parallel")),
        "streaming_review_stages": sum(1 for stage in stage_list if stage.get("streaming_review")),
        "artifacts": _existing_artifacts(task_dir, ["pipeline.json"]),
        "next_action": next_action,
    }


def _read_inbox_orchestration(task_dir):
    events = telemetry.read_progress_buffer(Path(task_dir))
    delegations = _read_jsonl_file(Path(task_dir) / "delegation.jsonl")
    event_names = Counter(str(row.get("event") or "") for row in events)
    terminal_events = sum(
        event_names.get(name, 0)
        for name in ("STAGE_DONE", "STAGE_FANOUT_UNIT_DONE", "STAGE_FANOUT_DONE", "COMPLETED", "BLOCKED")
    )
    fanout_events = sum(
        count for event, count in event_names.items()
        if event.startswith("STAGE_FANOUT")
    )
    if delegations:
        next_action = "review_delegations"
    elif fanout_events:
        next_action = "review_fanout_events"
    elif events:
        next_action = "review_progress_events"
    else:
        next_action = "no_inbox_events"
    return {
        "events": len(events),
        "terminal_events": terminal_events,
        "fanout_events": fanout_events,
        "delegations": len(delegations),
        "artifacts": _existing_artifacts(task_dir, [
            "progress.buffer.jsonl",
            "delegation.jsonl",
        ]),
        "next_action": next_action,
    }


def _proposal_refs_task(proposal, task_dir):
    evidence_refs = proposal.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        return False

    task_id = Path(task_dir).name
    task_context_prefix = f"tasks/{task_id}/context/"
    for ref in evidence_refs:
        if not isinstance(ref, str):
            continue
        normalized = ref.replace("\\", "/")
        if normalized.startswith(task_context_prefix):
            return True
        if normalized.endswith(f"/{task_context_prefix}"):
            return True
        if f"/{task_context_prefix}" in normalized:
            return True
    return False


def _pending_evolution_proposals(proposals, task_dir):
    return [
        item for item in proposals.get("proposals", [])
        if (
            isinstance(item, dict)
            and item.get("status") == "approval_required"
            and _proposal_refs_task(item, task_dir)
        )
    ] if isinstance(proposals.get("proposals"), list) else []


def _read_evolution_orchestration(task_dir, state_dir):
    report, report_present, report_valid = _read_json_document(
        Path(task_dir) / "context" / "evolution-report.json"
    )
    proposals, proposals_present, proposals_valid = _read_json_document(
        Path(state_dir) / "learning-candidates" / "proposals.json"
    )
    pending_proposals = _pending_evolution_proposals(proposals, task_dir)
    proposal = report.get("proposal")
    proposal_status = "none"
    if pending_proposals:
        proposal_status = "approval_required"
    elif proposals_present and not proposals_valid:
        proposal_status = "unknown"
    if isinstance(proposal, dict):
        proposal_status = str(proposal.get("status") or "unknown")
    elif report and proposal_status == "none":
        proposal_status = str(report.get("proposal") or "none")
    patterns = report.get("observed_patterns")
    observed_patterns = len(patterns) if isinstance(patterns, list) else 0
    if report_present and not report_valid:
        next_action = "inspect_evolution_report"
    elif proposals_present and not proposals_valid:
        next_action = "inspect_evolution_proposals"
    elif pending_proposals:
        next_action = "review_evolution_proposal"
    elif not report_present:
        next_action = "no_evolution_report"
    elif proposal_status == "approval_required":
        next_action = "review_evolution_proposal"
    elif observed_patterns > 0 and proposal_status == "none":
        next_action = "review_evolution_patterns"
    else:
        next_action = "evolution_report_available"
    artifacts = _existing_artifacts(task_dir, [
        "context/evolution-report.json",
        "context/evolution-report.md",
        "context/evolution-proposals-summary.txt",
    ])
    if pending_proposals or (proposals_present and not proposals_valid):
        artifacts.append("learning-candidates/proposals.json")
    return {
        "report_present": bool(report),
        "observed_patterns": observed_patterns,
        "proposal": proposal_status,
        "artifacts": artifacts,
        "next_action": next_action,
    }


def _build_orchestration_summary(state_dir, task_dir, stage_list, pipeline_present):
    return {
        "memory": _read_memory_orchestration(task_dir),
        "dag": _read_dag_orchestration(task_dir, stage_list, pipeline_present),
        "inbox": _read_inbox_orchestration(task_dir),
        "evolution": _read_evolution_orchestration(task_dir, state_dir),
    }


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
        "orchestration": _build_orchestration_summary(
            state_dir,
            task_dir,
            stage_list,
            pipeline_present,
        ),
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

    orchestration = smm.get("orchestration") or {}
    memory = orchestration.get("memory") or {}
    dag = orchestration.get("dag") or {}
    inbox = orchestration.get("inbox") or {}
    evolution = orchestration.get("evolution") or {}
    lines.append("Orchestration:")
    lines.append(
        "  Memory: "
        f"status={memory.get('retrieval_status', 'not_present')} "
        f"retrieved={memory.get('retrieved', 0)} "
        f"applied={memory.get('applied', 0)} "
        f"ignored={memory.get('ignored', 0)} "
        f"feedback_sent={memory.get('feedback_sent', 0)} "
        f"artifacts={','.join(memory.get('artifacts') or []) or 'none'} "
        f"next={memory.get('next_action', 'none')}"
    )
    lines.append(
        "  DAG: "
        f"stages={dag.get('stages', 0)} "
        f"current={dag.get('current_stage', 0)} "
        f"agents={','.join(dag.get('current_stage_agents') or []) or 'none'} "
        f"parallel_units={dag.get('parallel_units', 0)} "
        f"tdd_parallel={dag.get('tdd_parallel_stages', 0)} "
        f"artifacts={','.join(dag.get('artifacts') or []) or 'none'} "
        f"next={dag.get('next_action', 'none')}"
    )
    lines.append(
        "  Inbox: "
        f"events={inbox.get('events', 0)} "
        f"terminal={inbox.get('terminal_events', 0)} "
        f"fanout={inbox.get('fanout_events', 0)} "
        f"delegations={inbox.get('delegations', 0)} "
        f"artifacts={','.join(inbox.get('artifacts') or []) or 'none'} "
        f"next={inbox.get('next_action', 'none')}"
    )
    lines.append(
        "  Evolution: "
        f"report={'present' if evolution.get('report_present') else 'none'} "
        f"patterns={evolution.get('observed_patterns', 0)} "
        f"proposal={evolution.get('proposal', 'none')} "
        f"artifacts={','.join(evolution.get('artifacts') or []) or 'none'} "
        f"next={evolution.get('next_action', 'none')}"
    )

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
