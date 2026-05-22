"""Provider-neutral quality-loop validation helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path


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
STATUS_COMPLETED_RE = re.compile(r"^STATUS\s*:\s*completed\b", re.I | re.M)
QUALITY_BYPASS_RE = re.compile(r"^QUALITY_BYPASS_REASON\s*:", re.I | re.M)
TDD_EVENT_RE = re.compile(
    r"\b(TDD|RED|GREEN|REFACTOR|pytest|JUnit|MockK|tests?\s+passed|"
    r"STAGE_TDD_PARALLEL_DONE)\b",
    re.I,
)
REVIEW_APPROVED_RE = re.compile(
    r"\b(REVIEW:\s*APPROVED|APPROVED|REVIEW_APPROVED|final_verdict=ok)\b",
    re.I,
)
REVIEW_REJECTED_RE = re.compile(
    r"\b(STATUS:\s*REJECTED|REVIEW:\s*NEEDS_CHANGES|NEEDS_CHANGES|"
    r"reviewer_rejected|CHANGES_REQUESTED)\b",
    re.I,
)

NON_IMPLEMENTER_AGENTS = {
    "analyst",
    "devops",
    "documenter",
    "historian",
    "issuer",
    "planner",
    "requirements",
    "resolver",
    "reviewer",
    "scribe",
    "supervisor",
    "test-writer",
}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def looks_mutating_task(text: str) -> bool:
    return bool(MUTATING_TASK_RE.search(text or ""))


def stage_agents(stage) -> list[str]:
    if isinstance(stage, str):
        return [stage]
    if isinstance(stage, list):
        return [str(agent) for agent in stage]
    if isinstance(stage, dict):
        agents = stage.get("agents") or []
        if isinstance(agents, list):
            return [str(agent) for agent in agents]
    return []


def is_implementer_agent(agent: str) -> bool:
    name = agent.split(":", 1)[0].strip()
    return bool(name) and name not in NON_IMPLEMENTER_AGENTS


def is_implementation_stage(stage) -> bool:
    return any(is_implementer_agent(agent) for agent in stage_agents(stage))


def is_reviewer_stage(stage) -> bool:
    return "reviewer" in stage_agents(stage)


def is_tdd_capable_stage(stage) -> bool:
    agents = stage_agents(stage)
    if "test-writer" in agents:
        return True
    return isinstance(stage, dict) and bool(stage.get("tdd_parallel")) and is_implementation_stage(stage)


def pipeline_shape(pipeline: dict) -> dict:
    stages = pipeline.get("stages") or []
    implementer_indexes = [idx for idx, stage in enumerate(stages) if is_implementation_stage(stage)]
    reviewer_indexes = [idx for idx, stage in enumerate(stages) if is_reviewer_stage(stage)]
    tdd_indexes = [idx for idx, stage in enumerate(stages) if is_tdd_capable_stage(stage)]

    reviewer_after_implementer = any(
        reviewer_idx > implementer_idx
        for reviewer_idx in reviewer_indexes
        for implementer_idx in implementer_indexes
    )
    return {
        "stage_count": len(stages),
        "implementer_indexes": implementer_indexes,
        "reviewer_indexes": reviewer_indexes,
        "tdd_indexes": tdd_indexes,
        "has_implementation_stage": bool(implementer_indexes),
        "has_reviewer_stage": bool(reviewer_indexes),
        "has_tdd_stage": bool(tdd_indexes),
        "has_reviewer_after_implementer": reviewer_after_implementer,
    }


def event_text(row: dict) -> str:
    return " ".join(
        str(row.get(key, ""))
        for key in ("event", "status", "agent", "detail")
    )


def event_is_implementer_done(row: dict) -> bool:
    agent = str(row.get("agent", ""))
    return (
        is_implementer_agent(agent)
        and str(row.get("status", "")).lower() == "completed"
        and str(row.get("event", "")).startswith("STAGE")
    )


def event_is_tdd_done(row: dict) -> bool:
    agent = str(row.get("agent", ""))
    status = str(row.get("status", "")).lower()
    if agent == "test-writer" and status == "completed":
        return True
    return bool(TDD_EVENT_RE.search(event_text(row)))


def event_is_reviewer_approved(row: dict) -> bool:
    agent = str(row.get("agent", ""))
    text = event_text(row)
    return (
        (agent == "reviewer" and bool(REVIEW_APPROVED_RE.search(text)))
        or "STAGE_STREAMING_REVIEW_DONE" in text and "final_verdict=ok" in text
    )


def event_is_reviewer_rejected(row: dict) -> bool:
    agent = str(row.get("agent", ""))
    text = event_text(row)
    return (
        agent == "reviewer" and bool(REVIEW_REJECTED_RE.search(text))
    ) or "reviewer_rejected" in text


def task_description(task_dir: Path, register: dict, pipeline: dict, result_text: str) -> str:
    if register.get("task"):
        return str(register["task"])
    if pipeline.get("task"):
        return str(pipeline["task"])
    match = re.search(r"^#\s+(.+)$", result_text, re.M)
    return match.group(1) if match else ""


def is_completed(target_status: str | None, register: dict, result_text: str) -> bool:
    if target_status is not None:
        return target_status == "completed"
    return register.get("current_phase") == "completed" or bool(STATUS_COMPLETED_RE.search(result_text))


def rejection_followups(events: list[dict], rejected_index: int) -> dict:
    later = events[rejected_index + 1:]
    implementer_index = next(
        (idx for idx, row in enumerate(later) if event_is_implementer_done(row)),
        None,
    )
    tdd_index = next(
        (idx for idx, row in enumerate(later) if event_is_tdd_done(row)),
        None,
    )
    approval_index = next(
        (idx for idx, row in enumerate(later) if event_is_reviewer_approved(row)),
        None,
    )
    ordered = (
        implementer_index is not None
        and tdd_index is not None
        and approval_index is not None
        and approval_index > max(implementer_index, tdd_index)
    )
    return {
        "implementer_retry": implementer_index is not None,
        "tdd_retry": tdd_index is not None,
        "reviewer_reapproval": approval_index is not None,
        "ordered": ordered,
    }


def check_quality_loop(
    task_dir: Path,
    *,
    target_status: str | None = None,
    require_rework_cycle: bool = False,
) -> dict:
    task_dir = Path(task_dir)
    register = load_json(task_dir / "register.json")
    pipeline = load_json(task_dir / "pipeline.json")
    result_text = load_text(task_dir / "result.md")
    task = task_description(task_dir, register, pipeline, result_text)
    completed = is_completed(target_status, register, result_text)
    bypassed = bool(QUALITY_BYPASS_RE.search(result_text))
    required = completed and looks_mutating_task(task) and not bypassed

    shape = pipeline_shape(pipeline)
    events = load_jsonl(task_dir / "progress.buffer.jsonl")
    rejection_indexes = [
        idx for idx, row in enumerate(events) if event_is_reviewer_rejected(row)
    ]
    followups = [
        {"event_index": idx, **rejection_followups(events, idx)}
        for idx in rejection_indexes
    ]

    failures: list[str] = []
    if required:
        if not pipeline:
            failures.append("missing_pipeline")
        if not shape["has_implementation_stage"]:
            failures.append("missing_pipeline_implementation_stage")
        if not shape["has_tdd_stage"]:
            failures.append("missing_pipeline_tdd_stage")
        if not shape["has_reviewer_stage"]:
            failures.append("missing_pipeline_reviewer_stage")
        if not shape["has_reviewer_after_implementer"]:
            failures.append("missing_pipeline_reviewer_after_implementer")
        if not events:
            failures.append("missing_progress_events")
        if events and not any(event_is_implementer_done(row) for row in events):
            failures.append("missing_pipeline_implementation_completion")
        if events and not any(event_is_tdd_done(row) for row in events):
            failures.append("missing_pipeline_tdd_event")
        if events and not any(event_is_reviewer_approved(row) for row in events):
            failures.append("missing_pipeline_reviewer_approval")
        if require_rework_cycle and not rejection_indexes:
            failures.append("missing_rework_cycle")
        if any(not item["ordered"] for item in followups):
            failures.append("missing_rework_after_review_rejection")

    return {
        "passed": not failures,
        "required": required,
        "bypassed": bypassed,
        "failures": sorted(set(failures)),
        "task": task,
        "pipeline_shape": shape,
        "event_count": len(events),
        "rejection_indexes": rejection_indexes,
        "rejection_followups": followups,
        "implementer_event_count": sum(1 for row in events if event_is_implementer_done(row)),
        "tdd_event_count": sum(1 for row in events if event_is_tdd_done(row)),
        "reviewer_approval_count": sum(1 for row in events if event_is_reviewer_approved(row)),
    }
