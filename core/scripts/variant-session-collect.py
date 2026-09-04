#!/usr/bin/env python3
"""Collect completed crew run variants into a comparison summary."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


STATUS_RE = re.compile(
    r"^(?:\*\*)?status:\*{0,2}\s+\*{0,2}(\w+)\*{0,2}",
    re.IGNORECASE | re.MULTILINE,
)
FIELD_RE = re.compile(
    r"^(?:\*\*)?(summary|description|branch|blocker):\*{0,2}\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def result_fields(task_dir: Path) -> dict:
    path = task_dir / "result.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"status": "running", "summary": "result.md not available yet", "blockers": []}

    fields: dict[str, object] = {"status": "running", "summary": "", "blockers": []}
    status_match = STATUS_RE.search(text)
    if status_match:
        status = status_match.group(1).strip().lower()
        fields["status"] = status if status in {"completed", "blocked", "cancelled"} else status

    blockers: list[str] = []
    for key, value in FIELD_RE.findall(text):
        normalized_key = key.lower()
        normalized_value = value.strip().strip("*").strip()
        if normalized_key in {"summary", "description"} and normalized_value:
            fields["summary"] = normalized_value
        elif normalized_key == "branch" and normalized_value:
            fields["branch"] = normalized_value
        elif normalized_key == "blocker" and normalized_value:
            blockers.append(normalized_value)

    fields["blockers"] = blockers
    if not fields["summary"]:
        fields["summary"] = "No summary recorded in result.md"
    return fields


def render_summary(session: dict) -> str:
    lines = [
        "# Candidate Variants",
        "",
        f"Session: {session.get('session_id', 'Unknown')}",
        f"Base task: {session.get('base_task') or 'Unknown'}",
        "session_type: \"variants\"",
        f"selection_status: {session.get('selection_status') or 'pending'}",
        "",
        "| # | Task | Strategy | Branch | Status | Summary |",
        "|---|---|---|---|---|---|",
    ]

    for task in session.get("tasks", []):
        summary = str(task.get("summary") or "").replace("|", "\\|")
        lines.append(
            "| {index} | {task_id} | {strategy} | {branch} | {status} | {summary} |".format(
                index=task.get("variant_index") or "?",
                task_id=task.get("task_id") or "Unknown",
                strategy=task.get("variant_strategy") or task.get("variant_id") or "variant",
                branch=task.get("branch") or "Unknown",
                status=task.get("status") or "running",
                summary=summary or "No summary recorded",
            )
        )

    lines.extend(
        [
            "",
            "Do not merge all completed branches. Select one candidate implementation first.",
            "",
        ]
    )
    return "\n".join(lines)


def require_variants_session(state_dir: Path) -> tuple[dict | None, Path, str | None]:
    session_path = state_dir / "session.json"
    session = load_json(session_path)
    if not session:
        return None, session_path, "No session.json found.\n"
    if session.get("session_type") != "variants":
        return None, session_path, "No variants session found.\n"
    return session, session_path, None


def collect_variants(state_dir: Path) -> tuple[int, str]:
    session, session_path, message = require_variants_session(state_dir)
    if session is None:
        return 0, message or "No variants session to collect.\n"

    changed = False
    terminal_count = 0
    for task in session.get("tasks", []):
        task_dir_value = str(task.get("task_dir") or "").strip()
        fields = (
            result_fields(Path(task_dir_value))
            if task_dir_value
            else {"status": "running", "summary": "task_dir not recorded", "blockers": []}
        )
        status = str(fields.get("status") or "running")
        if task.get("status") != status:
            task["status"] = status
            changed = True
        if fields.get("branch") and task.get("branch") != fields["branch"]:
            task["branch"] = fields["branch"]
            changed = True
        summary = str(fields.get("summary") or "")
        if task.get("summary") != summary:
            task["summary"] = summary
            changed = True
        blockers = fields.get("blockers") or []
        if blockers and task.get("blockers") != blockers:
            task["blockers"] = blockers
            changed = True
        if status in {"completed", "blocked", "cancelled"}:
            terminal_count += 1

    tasks = session.get("tasks", [])
    if tasks and terminal_count == len(tasks) and session.get("status") != "completed":
        session["status"] = "completed"
        changed = True
    session["selection_status"] = session.get("selection_status") or "pending"
    if "selected_task_id" not in session:
        session["selected_task_id"] = None
        changed = True

    summary = render_summary(session)
    (state_dir / "variant-summary.md").write_text(summary, encoding="utf-8")
    if changed:
        write_json(session_path, session)

    return 0, summary


def select_variant(state_dir: Path, task_id: str) -> tuple[int, str]:
    session, session_path, message = require_variants_session(state_dir)
    if session is None:
        return 2, message or "No variants session to select.\n"

    selected = None
    for task in session.get("tasks", []):
        if str(task.get("task_id") or "") == task_id:
            selected = task
            break
    if selected is None:
        return 2, f"Variant task not found: {task_id}\n"

    session["selection_status"] = "selected"
    session["selected_task_id"] = task_id
    session["selected_variant_id"] = selected.get("variant_id")
    session["selected_variant_strategy"] = selected.get("variant_strategy")
    write_json(session_path, session)

    lines = [
        "Variant selected",
        f"selection_status: {session['selection_status']}",
        f"selected_task_id: {session['selected_task_id']}",
        f"selected_variant: {session.get('selected_variant_strategy') or session.get('selected_variant_id') or 'variant'}",
        f"branch: {selected.get('branch') or 'Unknown'}",
        "",
        "No branch mutation was performed.",
        "",
    ]
    return 0, "\n".join(lines)


def apply_variant(state_dir: Path) -> tuple[int, str]:
    session, _session_path, message = require_variants_session(state_dir)
    if session is None:
        return 2, message or "No variants session to apply.\n"
    if session.get("selection_status") != "selected" or not session.get("selected_task_id"):
        return 2, "No selected variant. Run crew variants select TASK_ID first.\n"

    selected_task_id = str(session.get("selected_task_id"))
    selected = None
    for task in session.get("tasks", []):
        if str(task.get("task_id") or "") == selected_task_id:
            selected = task
            break
    if selected is None:
        return 2, f"Selected variant task not found: {selected_task_id}\n"

    lines = [
        "Variant apply plan",
        f"session_id: {session.get('session_id') or 'Unknown'}",
        f"selected_task_id: {selected_task_id}",
        f"selected_variant: {selected.get('variant_strategy') or selected.get('variant_id') or 'variant'}",
        f"branch: {selected.get('branch') or 'Unknown'}",
        f"project_root: {selected.get('project_root') or 'Unknown'}",
        f"base_project_root: {selected.get('base_project_root') or selected.get('project_root') or 'Unknown'}",
        "",
        "No branch mutation was performed.",
        "Apply requires an explicit approval-bound branch operation in a later step.",
        "",
    ]
    return 0, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="manage crew run variants")
    parser.add_argument("action", nargs="?", default="collect", choices=["collect", "select", "apply"])
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--task-id")
    args = parser.parse_args(argv)

    if args.action == "select":
        if not args.task_id:
            parser.error("select requires --task-id")
        code, output = select_variant(Path(args.state_dir), args.task_id)
    elif args.action == "apply":
        code, output = apply_variant(Path(args.state_dir))
    else:
        code, output = collect_variants(Path(args.state_dir))
    print(output, end="" if output.endswith("\n") else "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
