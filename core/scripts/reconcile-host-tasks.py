#!/usr/bin/env python3
"""Plan host-TaskList reconciliation for a terminal task (issue #128).

When a P4 background fan-out supervisor reaches a terminal state
(`STATUS: completed` or `STATUS: blocked` in `result.md`), every host TaskList
row the framework created for that task should also be transitioned to a
terminal status — the parent host task (`{TASK_DIR}/host-task-id.txt`) plus
every per-stage child id under `pipeline.json.host_task_ids`.

This script is a **pure planner**. It reads the three input files, derives the
target terminal status from `result.md`, and emits a JSON plan to stdout
describing each `(host_task_id, target_status)` transition that a host-side
wrapper should perform (gated on the `task_tools` capability flag). The script
itself never calls into the host — that separation is what keeps the logic
AI-agnostic and unit-testable.

Exit codes:
  0 — plan emitted successfully (may have an empty `reconcile_plan` if there is
      nothing to reconcile; that is still a valid outcome).
  1 — `result.md` is missing or has no parseable `STATUS:` line.
  2 — `STATUS:` line carries an unrecognized value (not one of
      completed / blocked / CANCELLED).

The plan output (see `--format json`) carries every field a capability-gated
caller needs to issue `TaskGet`/`TaskUpdate` without re-deriving anything:

  {
    "task_id":          "20260529-193454-1",
    "terminal_status":  "completed" | "blocked" | "cancelled",
    "host_status":      "completed" | "blocked",
    "parent_task_id":   "<id or null>",
    "stage_task_ids":   [{"stage_index": 0, "agent_name": "backend",
                          "host_task_id": "..."}, ...],
    "reconcile_plan":   [{"host_task_id": "...", "target_status": "completed",
                          "scope": "parent" | "stage",
                          "stage_index": 0, "agent_name": "backend"}, ...]
  }

The script is referenced from:
  - core/agents/supervisor-retry.md (Phase 3 defensive sweep)
  - core/commands/status.md         (Step 4S.5 collect + snapshot reconcile)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# Canonical canonical form:  STATUS: completed
# Legacy markdown form:      **Status:** completed   (compat — see issue #31)
_STATUS_RE = re.compile(
    r"^(?:\*\*)?status:\*{0,2}\s+\*{0,2}([A-Za-z_-]+)\*{0,2}",
    re.IGNORECASE | re.MULTILINE,
)


def _parse_status(result_md_text: str) -> str | None:
    """Return the lowercase status keyword, or None if nothing parseable."""
    m = _STATUS_RE.search(result_md_text)
    if not m:
        return None
    return m.group(1).strip().lower()


def _load_host_task_ids(pipeline_json: Path) -> list[dict[str, str]]:
    """Best-effort read of pipeline.json's host_task_ids array.

    Returns an empty list when the file is missing, unreadable, or malformed.
    Never raises — the helper must not crash on corrupt state.
    """
    if not pipeline_json.is_file():
        return []
    try:
        data = json.loads(pipeline_json.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("host_task_ids")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for entry in raw:
        if isinstance(entry, dict):
            # Coerce values to strings so downstream callers can rely on the type
            out.append({str(k): str(v) for k, v in entry.items() if v is not None})
        else:
            out.append({})
    return out


def _load_parent_task_id(host_task_id_file: Path) -> str | None:
    if not host_task_id_file.is_file():
        return None
    try:
        text = host_task_id_file.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return text or None


def build_plan(task_dir: Path) -> dict[str, Any]:
    """Build the reconcile plan for `task_dir`.

    Raises:
        FileNotFoundError: when result.md is missing.
        ValueError: when result.md has no parseable STATUS or unknown value.
    """
    result_md = task_dir / "result.md"
    pipeline_json = task_dir / "pipeline.json"
    parent_id_file = task_dir / "host-task-id.txt"

    if not result_md.is_file():
        raise FileNotFoundError(f"result.md not found at {result_md}")

    text = result_md.read_text(encoding="utf-8", errors="replace")
    status = _parse_status(text)
    if status is None:
        raise ValueError(f"no parseable STATUS line in {result_md}")

    # Map result.md status to host TaskList terminal status.
    # CANCELLED → host "completed" so the row clears (matches supervisor Step 2b).
    if status == "completed":
        terminal_status = "completed"
        host_status = "completed"
    elif status == "blocked":
        terminal_status = "blocked"
        host_status = "blocked"
    elif status == "cancelled":
        terminal_status = "cancelled"
        host_status = "completed"
    else:
        raise ValueError(f"unrecognized STATUS {status!r} in {result_md}")

    parent_task_id = _load_parent_task_id(parent_id_file)
    raw_stage_ids = _load_host_task_ids(pipeline_json)

    # Flatten host_task_ids into a uniform list, preserving stage index and the
    # agent name from each entry's dict key. Iterate by .values() so custom
    # agent names round-trip correctly without any builtin-name allow-list.
    stage_task_ids: list[dict[str, Any]] = []
    for i, entry in enumerate(raw_stage_ids):
        if not isinstance(entry, dict):
            continue
        for agent_name, host_task_id in entry.items():
            if not host_task_id:
                continue
            stage_task_ids.append(
                {
                    "stage_index": i,
                    "agent_name":  agent_name,
                    "host_task_id": host_task_id,
                }
            )

    # Compose the wrapper-consumable plan. Each action carries everything a
    # capability-gated caller needs to issue TaskGet/TaskUpdate without
    # re-deriving anything from the source files.
    plan: list[dict[str, Any]] = []
    if parent_task_id:
        plan.append(
            {
                "scope":          "parent",
                "host_task_id":   parent_task_id,
                "target_status":  host_status,
            }
        )
    for entry in stage_task_ids:
        plan.append(
            {
                "scope":          "stage",
                "stage_index":    entry["stage_index"],
                "agent_name":     entry["agent_name"],
                "host_task_id":   entry["host_task_id"],
                "target_status":  host_status,
            }
        )

    return {
        "task_id":         task_dir.name,
        "terminal_status": terminal_status,
        "host_status":     host_status,
        "parent_task_id":  parent_task_id,
        "stage_task_ids":  stage_task_ids,
        "reconcile_plan":  plan,
    }


def _render_text(plan: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"reconcile plan for task_id={plan['task_id']}")
    lines.append(
        f"  terminal_status={plan['terminal_status']}  "
        f"host_status={plan['host_status']}"
    )

    actions = plan["reconcile_plan"]
    if not actions:
        lines.append("  (no host TaskList rows to reconcile)")
        return "\n".join(lines) + "\n"

    lines.append(f"  {len(actions)} row(s) to transition:")
    for a in actions:
        if a["scope"] == "parent":
            lines.append(
                f"    parent  {a['host_task_id']:<32}  → {a['target_status']}"
            )
        else:
            label = f"stage[{a['stage_index']}].{a['agent_name']}"
            lines.append(
                f"    {label:<28}  {a['host_task_id']:<28}  → {a['target_status']}"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reconcile-host-tasks",
        description="Plan host TaskList reconciliation for a terminal task.",
    )
    parser.add_argument(
        "--task-dir", required=True,
        help="Path to the agent-crew task directory (contains result.md, "
             "pipeline.json, host-task-id.txt).",
    )
    parser.add_argument(
        "--format", choices=("json", "text"), default="json",
        help="Output format (default: json).",
    )
    args = parser.parse_args(argv)

    task_dir = Path(args.task_dir).resolve()

    try:
        plan = build_plan(task_dir)
    except FileNotFoundError as exc:
        # rc=1 — result.md missing
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        msg = str(exc)
        # rc=2 — unrecognized status; rc=1 — unparseable status
        if "unrecognized STATUS" in msg:
            print(msg, file=sys.stderr)
            return 2
        print(msg, file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(_render_text(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
