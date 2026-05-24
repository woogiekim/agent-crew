#!/usr/bin/env python3
"""Repair local task state after a manual host-handoff fallback."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from quality_loop_lib import check_quality_loop


MUTATING_TASK_RE = re.compile(
    r"\b("
    r"build|implement|create|add|update|fix|remove|move|change|migrate|"
    r"refactor|replace|extend|integrate|test|deploy|merge|rollback|write|"
    r"save|edit|publish|commit|resolve|close"
    r")\b|"
    r"구현|개발|추가|수정|개선|보완|변경|삭제|이동|마이그레이션|"
    r"리팩터|테스트|배포|머지|롤백|반영|저장|발행|고쳐|해결",
    re.IGNORECASE,
)

TDD_RE = re.compile(r"\b(TDD|RED|GREEN|test evidence|tests? passed|pytest|JUnit|MockK)\b", re.IGNORECASE)
REVIEW_RE = re.compile(
    r"\b(REVIEW:\s*APPROVED|REVIEW_APPROVED|APPROVED|reviewer approved|"
    r"review findings.*remediated|CHANGES_REQUESTED.*remediated|재리뷰.*승인|리뷰.*승인)\b",
    re.IGNORECASE,
)


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def resolve_task_dir(state_dir: Path, task_id: str) -> Path:
    task_dir = state_dir / "tasks" / task_id
    if not task_dir.is_dir():
        raise SystemExit(f"repair-task-state: task not found: {task_id}")
    return task_dir


def backup_result(task_dir: Path) -> None:
    result = task_dir / "result.md"
    if not result.is_file():
        return

    archive = task_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    target = archive / "result-before-repair.md"
    if not target.exists():
        target.write_text(result.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")


def looks_mutating_task(task: str) -> bool:
    return bool(MUTATING_TASK_RE.search(task or ""))


def resolve_quality_paths(task_dir: Path, paths: list[str]) -> list[Path]:
    candidates = [
        task_dir / "context" / "tdd_log.md",
        task_dir / "context" / "review.md",
        task_dir / "context" / "reviewer.md",
        task_dir / "context" / "quality-loop.md",
        task_dir / "context" / "quality-loop.json",
    ]
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = task_dir / value
        candidates.append(path)
    return candidates


def quality_evidence_status(task_dir: Path, paths: list[str]) -> dict:
    tdd_paths: list[str] = []
    review_paths: list[str] = []
    inspected_paths: list[str] = []
    for path in resolve_quality_paths(task_dir, paths):
        if not path.is_file():
            continue
        inspected_paths.append(str(path))
        rel_name = str(path.relative_to(task_dir)) if path.is_relative_to(task_dir) else str(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        if TDD_RE.search(text):
            tdd_paths.append(rel_name)
        if REVIEW_RE.search(text):
            review_paths.append(rel_name)
    return {
        "required": True,
        "passed": bool(tdd_paths and review_paths),
        "tdd_evidence_paths": sorted(set(tdd_paths)),
        "review_evidence_paths": sorted(set(review_paths)),
        "inspected_paths": sorted(set(inspected_paths)),
    }


def enforce_quality_gate(args: argparse.Namespace, task_dir: Path, register: dict) -> dict:
    task = register.get("task", "")
    required = args.status == "completed" and looks_mutating_task(task)
    if not required:
        return {"required": False, "passed": True, "bypassed": False}

    evidence_paths = list(args.evidence) + list(args.quality_evidence)
    status = quality_evidence_status(task_dir, evidence_paths)
    pipeline_status = check_quality_loop(task_dir, target_status=args.status)
    status["pipeline_gate"] = pipeline_status
    status["pipeline_passed"] = pipeline_status["passed"]
    status["passed"] = bool(status["passed"] and pipeline_status["passed"])
    status["bypassed"] = False
    status["bypass_reason"] = ""
    if status["passed"]:
        return status

    if args.quality_bypass_reason:
        status["bypassed"] = True
        status["bypass_reason"] = args.quality_bypass_reason
        return status

    if status.get("tdd_evidence_paths") and status.get("review_evidence_paths"):
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: missing_quality_loop_pipeline\n"
            "DETAIL: completed repair for a mutating implementation task requires "
            "pipeline-level quality-loop events, not only evidence files.\n"
            "FAILURES: " + ", ".join(pipeline_status.get("failures", [])) + "\n"
            "NEXT: ensure pipeline.json includes TDD-capable implementation and reviewer stages, "
            "and progress.buffer.jsonl proves implementer/TDD completion plus reviewer approval. "
            "If review rejected, the trace must show implementer/TDD retry followed by reviewer re-approval."
        )

    raise SystemExit(
        "STATUS: blocked\n"
        "BLOCKER: missing_quality_loop_evidence\n"
        "DETAIL: completed repair for a mutating implementation task requires "
        "TDD/test evidence, reviewer evidence, and pipeline-level quality-loop events.\n"
        "NEXT: add --quality-evidence paths for TDD/reviewer artifacts, or "
        "record an explicit --quality-bypass-reason."
    )


def render_result(task: str, task_id: str, status: str, note: str, blocker: str,
                  evidence_paths: list[str], memory_ids: list[str],
                  memory_context_reused: bool, quality_gate: dict | None = None) -> str:
    lines = [
        f"# {task or task_id}",
        "",
        f"STATUS: {status}",
        f"TASK_ID: {task_id}",
        "MEASUREMENTS: repaired manual handoff state, 1 repair event recorded, 0 retries",
    ]
    if status in {"blocked", "cancelled"}:
        lines.append(f"BLOCKER: {blocker or status}")
    lines.append(f"EVIDENCE: context/manual-fallback-repair.json")
    for path in evidence_paths:
        lines.append(f"EVIDENCE: {path}")
    if quality_gate and quality_gate.get("required"):
        if quality_gate.get("passed"):
            lines.append("QUALITY_LOOP: passed")
        elif quality_gate.get("bypassed"):
            lines.append("QUALITY_LOOP: bypassed")
            lines.append(f"QUALITY_BYPASS_REASON: {quality_gate.get('bypass_reason')}")
        if "pipeline_passed" in quality_gate:
            lines.append(f"PIPELINE_QUALITY_LOOP: {'passed' if quality_gate.get('pipeline_passed') else 'failed'}")
        pipeline_failures = quality_gate.get("pipeline_gate", {}).get("failures", [])
        if pipeline_failures:
            lines.append("PIPELINE_QUALITY_FAILURES: " + ", ".join(pipeline_failures))
        for path in quality_gate.get("tdd_evidence_paths", []):
            lines.append(f"TDD_EVIDENCE: {path}")
        for path in quality_gate.get("review_evidence_paths", []):
            lines.append(f"REVIEW_EVIDENCE: {path}")
    lines.append("UNCERTAINTY: Manual repair records the current-session outcome; original host bridge execution did not run automatically.")
    if note:
        lines.append(f"NOTE: {note}")
    if memory_ids:
        lines.append("MEMORY_IDS: " + ", ".join(memory_ids))
        lines.append(f"MEMORY_CONTEXT_REUSED: {'yes' if memory_context_reused else 'no'}")
    return "\n".join(lines).rstrip() + "\n"


def repair(args: argparse.Namespace) -> dict:
    state_dir = Path(args.state_dir).expanduser().resolve()
    task_dir = resolve_task_dir(state_dir, args.task_id)
    register_path = task_dir / "register.json"
    pipeline_path = task_dir / "pipeline.json"
    now = utc_now_z()

    register = load_json(register_path)
    pipeline = load_json(pipeline_path)
    quality_gate = enforce_quality_gate(args, task_dir, register)
    previous = {
        "status": register.get("current_phase"),
        "blocked_by": register.get("blocked_by", []),
    }

    status = args.status
    blocker = args.blocker or (
        "manual_fallback_cancelled" if status == "cancelled"
        else "manual_fallback_blocked" if status == "blocked"
        else ""
    )
    blocked_by = [blocker] if status in {"blocked", "cancelled"} and blocker else []
    host_bridge_status = {
        "completed": "manual_fallback_completed",
        "blocked": "manual_fallback_blocked",
        "cancelled": "manual_fallback_cancelled",
    }[status]

    register.update({
        "current_phase": status,
        "blocked_by": blocked_by,
        "host_bridge_status": host_bridge_status,
        "manual_fallback_repaired_at": now,
        "manual_fallback_repair_path": str(task_dir / "context" / "manual-fallback-repair.json"),
    })

    stages = pipeline.get("stages") or ["supervisor"]
    pipeline.update({
        "completed_stages": len(stages) if status == "completed" else int(pipeline.get("completed_stages") or 0),
        "stage_agent_status": {
            "1": {"supervisor": status}
        },
    })

    repair_record = {
        "schema_version": 1,
        "task_id": args.task_id,
        "status": status,
        "blocker": blocker,
        "note": args.note,
        "evidence_paths": args.evidence,
        "memory_ids": args.memory_id,
        "memory_context_reused": args.reused_memory_context,
        "quality_gate": quality_gate,
        "previous": previous,
        "repaired_at": now,
    }

    backup_result(task_dir)
    write_json(register_path, register)
    write_json(pipeline_path, pipeline)
    write_json(task_dir / "context" / "manual-fallback-repair.json", repair_record)
    (task_dir / "result.md").write_text(
        render_result(
            register.get("task", ""),
            args.task_id,
            status,
            args.note,
            blocker,
            args.evidence,
            args.memory_id,
            args.reused_memory_context,
            quality_gate,
        ),
        encoding="utf-8",
    )
    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{now} | REPAIR | manual fallback marked {status}\n")
        handle.write(f"{now} | STATUS | {status}\n")
    terminal_event = {
        "completed": "COMPLETED",
        "blocked": "BLOCKED",
        "cancelled": "CANCELLED",
    }[status]
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', args.task_id)}.{args.task_id}.0.0",
            "task_id": args.task_id,
            "session_id": register.get("session_id", ""),
            "event": "REPAIR",
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": status,
            "detail": args.note or "manual fallback repaired",
            "files": ["context/manual-fallback-repair.json", "result.md"],
        },
    )
    append_jsonl(
        task_dir / "progress.buffer.jsonl",
        {
            "ts": now,
            "trace_id": f"{register.get('session_id', args.task_id)}.{args.task_id}.0.0",
            "task_id": args.task_id,
            "session_id": register.get("session_id", ""),
            "event": terminal_event,
            "stage": 0,
            "agent": "",
            "attempt": 0,
            "status": status,
            "detail": status if status == "completed" else blocker,
            "files": [],
        },
    )
    return repair_record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--status", choices=["completed", "blocked", "cancelled"], default="completed")
    parser.add_argument("--note", default="")
    parser.add_argument("--blocker", default="")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--quality-evidence", action="append", default=[])
    parser.add_argument("--quality-bypass-reason", default="")
    parser.add_argument("--memory-id", action="append", default=[])
    parser.add_argument("--reused-memory-context", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("task_id")
    args = parser.parse_args()

    record = repair(args)
    if args.format == "json":
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(f"STATUS: {record['status']}")
        print(f"TASK_ID: {record['task_id']}")
        print("REPAIR: context/manual-fallback-repair.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
