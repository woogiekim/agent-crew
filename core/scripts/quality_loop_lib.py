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
STRONG_MUTATING_TASK_RE = re.compile(
    r"\b("
    r"build|implement|create|add|update|fix|remove|move|change|migrate|"
    r"refactor|replace|extend|integrate|deploy|merge|rollback|write|"
    r"save|edit|publish|commit|resolve|close"
    r")\b|"
    r"구현|개발|추가|수정|개선|보완|변경|삭제|이동|마이그레이션|"
    r"리팩터|배포|머지|롤백|반영|저장|발행|고쳐|해결",
    re.IGNORECASE,
)
READ_ONLY_TASK_RE = re.compile(
    r"\b("
    r"read-only|readonly|non-mutating|nonmutating|no[- ]write|"
    r"inspect|investigate|analyze|analyse|review|validate|validation|"
    r"check|audit|status|diagnostic|diagnostics"
    r")\b|"
    r"읽기\s*전용|조회|분석|검토|확인|진단",
    re.IGNORECASE,
)
NON_MUTATING_CONSTRAINT_RE = re.compile(
    r"\b("
    r"do\s+not|don't|dont|must\s+not|should\s+not|never|without|no"
    r")\s+("
    r"build|implement|create|add|update|fix|remove|move|change|migrate|"
    r"refactor|replace|extend|integrate|deploy|merge|rollback|write|"
    r"save|edit|publish|commit|push|resolve|close|mutate"
    r")\b",
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
QUALITY_METRICS_RE = re.compile(r"\bQUALITY_METRICS\s*:\s*(\S+)", re.I)
REVIEW_REJECTED_RE = re.compile(
    r"\b(STATUS:\s*REJECTED|REVIEW:\s*NEEDS_CHANGES|NEEDS_CHANGES|"
    r"reviewer_rejected|CHANGES_REQUESTED)\b",
    re.I,
)

NON_IMPLEMENTER_AGENTS = {
    "analyst",
    "devops",
    "designer",
    "documenter",
    "historian",
    "issuer",
    "planner",
    "qa-owner",
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
    value = text or ""
    constrained_value = NON_MUTATING_CONSTRAINT_RE.sub("", value)
    if READ_ONLY_TASK_RE.search(value) and not STRONG_MUTATING_TASK_RE.search(constrained_value):
        return False
    return bool(MUTATING_TASK_RE.search(constrained_value))


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


def stage_implementer_agents(stage) -> list[str]:
    return [agent for agent in stage_agents(stage) if is_implementer_agent(agent)]


def is_implementation_stage(stage) -> bool:
    return bool(stage_implementer_agents(stage))


def is_reviewer_stage(stage) -> bool:
    return "reviewer" in stage_agents(stage)


def is_single_reviewer_stage(stage) -> bool:
    return stage_agents(stage) == ["reviewer"]


def is_qa_verify_stage(stage) -> bool:
    return (
        isinstance(stage, dict)
        and stage_agents(stage) == ["qa-owner"]
        and str(stage.get("qa_mode", "")).lower() == "verify"
    )


def is_qa_plan_stage(stage) -> bool:
    return (
        isinstance(stage, dict)
        and stage_agents(stage) == ["qa-owner"]
        and str(stage.get("qa_mode", "")).lower() == "plan"
    )


def has_quality_gate_after_implementer(stages: list, idx: int) -> bool:
    if idx + 1 >= len(stages):
        return False
    if is_single_reviewer_stage(stages[idx + 1]):
        return True
    return (
        is_qa_verify_stage(stages[idx + 1])
        and idx + 2 < len(stages)
        and is_single_reviewer_stage(stages[idx + 2])
    )


def is_tdd_capable_stage(stage) -> bool:
    agents = stage_agents(stage)
    if "test-writer" in agents:
        return True
    return (
        isinstance(stage, dict)
        and bool(stage.get("tdd_parallel"))
        and len(stage_implementer_agents(stage)) == 1
    )


def pipeline_shape(pipeline: dict) -> dict:
    stages = pipeline.get("stages") or []
    implementer_indexes = [idx for idx, stage in enumerate(stages) if is_implementation_stage(stage)]
    reviewer_indexes = [idx for idx, stage in enumerate(stages) if is_reviewer_stage(stage)]
    qa_plan_indexes = [idx for idx, stage in enumerate(stages) if is_qa_plan_stage(stage)]
    qa_verify_indexes = [idx for idx, stage in enumerate(stages) if is_qa_verify_stage(stage)]
    tdd_indexes = [idx for idx, stage in enumerate(stages) if is_tdd_capable_stage(stage)]
    implementer_indexes_without_immediate_reviewer = [
        idx for idx in implementer_indexes
        if idx + 1 >= len(stages) or not is_single_reviewer_stage(stages[idx + 1])
    ]
    implementer_indexes_without_quality_gate = [
        idx for idx in implementer_indexes
        if not has_quality_gate_after_implementer(stages, idx)
    ]
    qa_verify_indexes_without_following_reviewer = [
        idx for idx in qa_verify_indexes
        if idx + 1 >= len(stages) or not is_single_reviewer_stage(stages[idx + 1])
    ]

    reviewer_after_implementer = any(
        reviewer_idx > implementer_idx
        for reviewer_idx in reviewer_indexes
        for implementer_idx in implementer_indexes
    )
    return {
        "stage_count": len(stages),
        "implementer_indexes": implementer_indexes,
        "reviewer_indexes": reviewer_indexes,
        "qa_plan_indexes": qa_plan_indexes,
        "qa_verify_indexes": qa_verify_indexes,
        "tdd_indexes": tdd_indexes,
        "has_implementation_stage": bool(implementer_indexes),
        "has_reviewer_stage": bool(reviewer_indexes),
        "has_qa_plan_stage": bool(qa_plan_indexes),
        "has_qa_verify_stage": bool(qa_verify_indexes),
        "has_tdd_stage": bool(tdd_indexes),
        "has_reviewer_after_implementer": reviewer_after_implementer,
        "implementer_indexes_without_immediate_reviewer": implementer_indexes_without_immediate_reviewer,
        "has_reviewer_after_each_implementer": not implementer_indexes_without_immediate_reviewer,
        "implementer_indexes_without_quality_gate": implementer_indexes_without_quality_gate,
        "has_quality_gate_after_each_implementer": not implementer_indexes_without_quality_gate,
        "qa_verify_indexes_without_following_reviewer": qa_verify_indexes_without_following_reviewer,
        "has_reviewer_after_each_qa_verify": not qa_verify_indexes_without_following_reviewer,
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


def event_quality_metrics_path(row: dict) -> str:
    match = QUALITY_METRICS_RE.search(event_text(row))
    return match.group(1).strip() if match else ""


def resolve_event_quality_metrics_path(path_text: str, task_dir: Path | None) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    if task_dir is None:
        return None
    if path_text.startswith("context/"):
        return task_dir / path_text
    return task_dir / path.name


def quality_metrics_schema_errors(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["malformed_quality_metrics_json"]
    except Exception:
        return ["unreadable_quality_metrics_artifact"]

    if not isinstance(payload, dict):
        return ["quality_metrics_not_object"]

    allowed_fields = {
        "schema_version",
        "hallucination_detected",
        "rollback_performed",
        "human_intervention_required",
        "factuality_review",
        "evidence_paths",
        "notes",
    }
    errors: list[str] = []
    if payload.get("schema_version") != 1 or isinstance(payload.get("schema_version"), bool):
        errors.append("invalid_quality_metrics_schema_version")

    unexpected = sorted(set(payload) - allowed_fields)
    if unexpected:
        errors.append("unexpected_quality_metrics_fields")

    for key in ("hallucination_detected", "rollback_performed", "human_intervention_required"):
        if key in payload and not isinstance(payload[key], bool):
            errors.append(f"invalid_quality_metrics_{key}")

    if "factuality_review" in payload and payload["factuality_review"] not in {
        "not_applicable",
        "passed",
        "failed",
        "inconclusive",
    }:
        errors.append("invalid_quality_metrics_factuality_review")

    if "evidence_paths" in payload:
        evidence_paths = payload["evidence_paths"]
        if not isinstance(evidence_paths, list) or not all(isinstance(item, str) for item in evidence_paths):
            errors.append("invalid_quality_metrics_evidence_paths")

    if "notes" in payload and not isinstance(payload["notes"], str):
        errors.append("invalid_quality_metrics_notes")

    return errors


def event_quality_metrics_errors(row: dict, task_dir: Path | None = None) -> list[str]:
    path_text = event_quality_metrics_path(row)
    if not path_text:
        return ["missing_quality_metrics_pointer"]
    resolved = resolve_event_quality_metrics_path(path_text, task_dir)
    if resolved is None:
        return []
    if not resolved.is_file():
        return ["missing_quality_metrics_artifact"]
    return quality_metrics_schema_errors(resolved)


def event_has_quality_metrics(row: dict, task_dir: Path | None = None) -> bool:
    return not event_quality_metrics_errors(row, task_dir)


def event_is_reviewer_approved(row: dict, task_dir: Path | None = None) -> bool:
    agent = str(row.get("agent", ""))
    text = event_text(row)
    approved = (
        (agent == "reviewer" and bool(REVIEW_APPROVED_RE.search(text)))
        or "STAGE_STREAMING_REVIEW_DONE" in text and "final_verdict=ok" in text
    )
    return approved and event_has_quality_metrics(row, task_dir)


def event_is_reviewer_rejected(row: dict) -> bool:
    agent = str(row.get("agent", ""))
    text = event_text(row)
    return (
        agent == "reviewer" and bool(REVIEW_REJECTED_RE.search(text))
    ) or "reviewer_rejected" in text


def event_stage(row: dict) -> int | None:
    try:
        return int(row.get("stage"))
    except Exception:
        return None


def event_attempt(row: dict) -> int:
    try:
        return int(row.get("attempt"))
    except Exception:
        return 0


def reviewer_rework_target_stage(pipeline: dict, reviewer_stage: int | None) -> int | None:
    if not reviewer_stage:
        return None
    stages = pipeline.get("stages") or []
    reviewer_idx = reviewer_stage - 1
    previous_idx = reviewer_idx - 1
    if previous_idx < 0 or previous_idx >= len(stages):
        return None
    if is_implementation_stage(stages[previous_idx]):
        return previous_idx + 1
    if is_qa_verify_stage(stages[previous_idx]):
        implementation_idx = previous_idx - 1
        if implementation_idx >= 0 and is_implementation_stage(stages[implementation_idx]):
            return implementation_idx + 1
    return previous_idx + 1 if reviewer_stage > 1 else None


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


def rejection_followups(events: list[dict], rejected_index: int, pipeline: dict | None = None) -> dict:
    rejected = events[rejected_index]
    rejected_stage = event_stage(rejected)
    rejected_attempt = event_attempt(rejected)
    target_stage = reviewer_rework_target_stage(pipeline or {}, rejected_stage)
    later = events[rejected_index + 1:]
    implementer_candidates = [
        (idx, row)
        for idx, row in enumerate(later)
        if event_is_implementer_done(row)
        and (target_stage is None or event_stage(row) == target_stage)
        and event_attempt(row) > rejected_attempt
    ]
    tdd_candidates = [
        (idx, row)
        for idx, row in enumerate(later)
        if event_is_tdd_done(row)
        and (target_stage is None or event_stage(row) == target_stage)
        and event_attempt(row) > rejected_attempt
    ]
    approval_candidates = [
        (idx, row)
        for idx, row in enumerate(later)
        if event_is_reviewer_approved(row, None)
        and (rejected_stage is None or event_stage(row) == rejected_stage)
        and event_attempt(row) > rejected_attempt
    ]
    implementer_index = next(
        (idx for idx, _row in implementer_candidates),
        None,
    )
    tdd_index = next(
        (idx for idx, _row in tdd_candidates),
        None,
    )
    approval_index = next(
        (idx for idx, _row in approval_candidates),
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
        "rejected_stage": rejected_stage,
        "rejected_attempt": rejected_attempt,
        "target_implementation_stage": target_stage,
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
        {"event_index": idx, **rejection_followups(events, idx, pipeline)}
        for idx in rejection_indexes
    ]
    approved_events = [
        row for row in events
        if str(row.get("agent", "")) == "reviewer"
        and bool(REVIEW_APPROVED_RE.search(event_text(row)))
    ]
    valid_approval_events = [
        row for row in approved_events
        if event_is_reviewer_approved(row, task_dir)
    ]
    approval_metric_errors = [
        error
        for row in approved_events
        for error in event_quality_metrics_errors(row, task_dir)
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
        if not shape["has_quality_gate_after_each_implementer"]:
            failures.append("missing_pipeline_reviewer_after_each_implementer")
        if not shape["has_reviewer_after_each_qa_verify"]:
            failures.append("missing_pipeline_reviewer_after_qa_verify")
        if not events:
            failures.append("missing_progress_events")
        if events and not any(event_is_implementer_done(row) for row in events):
            failures.append("missing_pipeline_implementation_completion")
        if events and not any(event_is_tdd_done(row) for row in events):
            failures.append("missing_pipeline_tdd_event")
        if events and approved_events and not valid_approval_events:
            failures.append("missing_reviewer_quality_metrics_artifact")
        if any(error.startswith("invalid_") or error in {
            "malformed_quality_metrics_json",
            "quality_metrics_not_object",
            "unexpected_quality_metrics_fields",
            "unreadable_quality_metrics_artifact",
        } for error in approval_metric_errors):
            failures.append("invalid_reviewer_quality_metrics_artifact")
        if events and not valid_approval_events:
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
        "reviewer_approval_count": len(valid_approval_events),
        "reviewer_approved_without_quality_metrics_count": len(approved_events) - len(valid_approval_events),
        "reviewer_quality_metrics_errors": sorted(set(approval_metric_errors)),
    }
