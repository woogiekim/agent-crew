#!/usr/bin/env python3
"""Repair local task state after a manual host-handoff fallback."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from quality_loop_lib import check_quality_loop, looks_mutating_task as shared_looks_mutating_task
from task_capability_lib import required_capabilities_for_task


QUALITY_GATED_TASK_RE = re.compile(
    r"\b("
    r"implement|create|add|update|fix|remove|move|change|migrate|"
    r"refactor|replace|extend|integrate|test|write|edit|improve"
    r")\b|"
    r"구현|개발|추가|수정|개선|보완|변경|삭제|이동|마이그레이션|"
    r"리팩터|테스트|작성|편집",
    re.IGNORECASE,
)
NON_PRODUCTION_ARTIFACT_RE = re.compile(
    r"\b("
    r"readme|docs?|documentation|guide|quick[-_ ]?start|release\s+notes?|"
    r"changelog|markdown|md|commentary|summary|report"
    r")\b|문서|릴리즈\s*노트|변경\s*로그|요약|보고서",
    re.IGNORECASE,
)
ARTIFACT_CODE_OWNER_RE = re.compile(
    r"\b(?:"
    r"readme|docs?|documentation|changelog|report"
    r")\s+(?:generator|parser|renderer|exporter|builder|processor|tool|service|module|pipeline)\b|"
    r"\b(?:generator|parser|renderer|exporter|builder|processor|tool|service|module|pipeline)"
    r"\s+(?:for\s+)?(?:readme|docs?|documentation|changelog|report)\b|"
    r"(?:문서|보고서|변경\s*로그).*(?:생성기|파서|렌더러|익스포터|도구|서비스|모듈)",
    re.IGNORECASE,
)
ARTIFACT_CODE_OWNER_OUTPUT_RE = re.compile(
    r"\b(?:write|edit|create|update|fix)\b.*"
    r"(?:generator|parser|renderer|exporter|builder|processor|tool|service|module|pipeline).*"
    r"\b(?:readme|docs?|documentation|guide|changelog|report)\b|"
    r"(?:생성기|파서|렌더러|익스포터|도구|서비스|모듈).*(?:문서|가이드|보고서)",
    re.IGNORECASE,
)
OPERATIONAL_UPDATE_RE = re.compile(
    r"\b("
    r"merge|push|commit|install|refresh|sync|update\s+(?:global|local|installed|runtime|agent-crew)\b|"
    r"(?:global|local|installed|runtime|agent-crew)\s+(?:assets?|install|update)"
    r")\b|머지|푸시|커밋|설치|동기화|글로벌\s*업데이트|설치본\s*업데이트",
    re.IGNORECASE,
)
OPERATIONAL_ASSET_UPDATE_RE = re.compile(
    r"\b("
    r"update\s+(?:(?:installed|runtime|global|local|agent-crew)\s+){1,3}assets?|"
    r"(?:(?:installed|runtime|global|local|agent-crew)\s+){1,3}assets?\s+update"
    r")\b|설치본\s*런타임\s*에셋|런타임\s*에셋\s*업데이트",
    re.IGNORECASE,
)
ASSET_SOURCE_CODE_RE = re.compile(
    r"\bassets?\s+(?:source\s+)?code\b|\bsource\s+code\s+assets?\b|에셋.*(?:소스|코드)",
    re.IGNORECASE,
)
EXPLICIT_CODE_CHANGE_RE = re.compile(
    r"\b("
    r"code|source|implementation|production[-_ ]?code|runtime\s+code"
    r")\b|코드|소스|구현|프로덕션\s*코드|운영\s*코드|런타임\s*코드",
    re.IGNORECASE,
)
IMPLEMENTATION_INTENT_RE = re.compile(
    r"\b("
    r"implement|create|add|update|fix|remove|move|change|migrate|"
    r"refactor|replace|extend|integrate|test|improve"
    r")\b|구현|개발|추가|수정|개선|보완|변경|삭제|이동|마이그레이션|"
    r"리팩터|테스트|고쳐|해결",
    re.IGNORECASE,
)
DOMAIN_CHANGE_RE = re.compile(
    r"\b("
    r"api|backend|frontend|database|schema|service|component|function|"
    r"class|module|library|script|cli|hook|adapter|pipeline|gate|bug|logic|behavior|runtime"
    r")\b|백엔드|프론트엔드|데이터베이스|스키마|서비스|컴포넌트|함수|"
    r"클래스|모듈|스크립트|훅|어댑터|파이프라인|게이트|버그|로직|동작|런타임",
    re.IGNORECASE,
)

TDD_RE = re.compile(r"\b(TDD|RED|GREEN|test evidence|tests? passed|pytest|JUnit|MockK)\b", re.IGNORECASE)
RED_PHASE_RE = re.compile(
    r"\b("
    r"tdd[-_ ]?red|red[-_ ]?phase|expected\s+(?:failing|failure)|"
    r"failed\s+as\s+expected|focused\s+test[^\n]*fail|"
    r"fail(?:ed|ing)\s+test[^\n]*(?:before|pre[-_ ]?implementation)"
    r")\b|레드\s*페이즈|실패\s*테스트",
    re.IGNORECASE,
)
TDD_EXCEPTION_RE = re.compile(
    r"\b("
    r"tdd[-_ ]?exception|red[-_ ]?phase\s+exception|"
    r"no\s+runnable\s+test\s+harness|no\s+test\s+harness|"
    r"cannot\s+produce\s+red|red\s+failure\s+cannot|unrunnable\s+test"
    r")\b|테스트\s*하네스.*없|레드.*예외",
    re.IGNORECASE,
)
REFACTOR_PHASE_RE = re.compile(
    r"\b("
    r"tdd[-_ ]?refactor|refactor[-_ ]?phase|"
    r"red\s*(?:->|→)\s*green\s*(?:->|→)\s*refactor|"
    r"post[-_ ]?refactor(?:\s+verification)?|"
    r"refactor(?:ed|ing)?[^\n]*(?:verified|verification|tests?\s+passed|no[-_ ]?op|complete)"
    r")\b|리팩터(?:링)?[^\n]*(?:검증|완료|테스트|무변경)",
    re.IGNORECASE,
)
REVIEW_RE = re.compile(
    r"\b(REVIEW:\s*APPROVED|REVIEW_APPROVED|APPROVED|reviewer approved|"
    r"review findings.*remediated|CHANGES_REQUESTED.*remediated|재리뷰.*승인|리뷰.*승인)\b",
    re.IGNORECASE,
)
SPECIALIST_DISPATCH_RE = re.compile(
    r"\b("
    r"selected_agent|specialist_agent|agent_selected|delegated_to|"
    r"selected_skill|skill_loaded|skill_context|dispatcher"
    r")\b|전문\s*에이전트|에이전트\s*스킬|스킬\s*선택|위임",
    re.IGNORECASE,
)
COMMIT_MUTATION_RE = re.compile(
    r"\b("
    r"git\s+commit|crew:?commit|commit(?:\s+(?:message|checkpoint|changes?))?|"
    r"amend|reword|squash"
    r")\b|커밋",
    re.IGNORECASE,
)
SKILL_LOAD_RE = re.compile(
    r"\b("
    r"skill[-_ ]?load|loaded\s+(?:skill|before)|skill_loaded|"
    r"read\s+.+skills?/.+\.md|applied\s+rule"
    r")\b|스킬\s*(?:로드|사용|적용)",
    re.IGNORECASE,
)
TDD_SKILL_PATH_RE = re.compile(r"(?:^|[/`\\])tdd\.md\b", re.IGNORECASE)
TDD_SKILL_SELECTION_RE = re.compile(r"\bselected_skill\s*[:=]\s*.*\btdd\b|\btdd_parallel\b|\bTDD\b", re.IGNORECASE)
LEGACY_AGENT_CAPABILITIES = {
    "git-committer": [
        "vcs.commit.message.compose",
        "vcs.history.local_mutation",
    ],
}
SPECIALIST_FIELD_RE = re.compile(
    r"\s*[-*]?\s*("
    r"selected_agent|selected_agents|selected_user_agent|selected_user_agents|"
    r"selected_handler|selected_handlers|"
    r"selected_subagent|selected_subagents|selected_skill|selected_skills|"
    r"selection_reason|execution_mode"
    r")\s*[:=]\s*(.+)",
    re.IGNORECASE,
)
SKILL_USE_RE = re.compile(r"\b(skill[-_ ]?use|applied_rules|evidence_refs|output_files|verification)\b", re.IGNORECASE)
SKILL_USE_REQUIRED_FIELDS = ("applied_rules", "evidence_refs", "output_files", "verification")
SKILL_PLAN_RE = re.compile(r"\b(skill[-_ ]?plan|task_interpretation|planned_application|rule_id|invariant)\b", re.IGNORECASE)
SKILL_PLAN_RULE_FIELDS = ("task_interpretation", "planned_application")
SKILL_UNDERSTANDING_RULE_FIELDS = (
    "artifact_refs",
    "diff_refs",
    "verification",
    "adversarial_checks",
    "reviewer_status",
)
COMPLETED_CAPABILITY_STATES = {"completed", "succeeded", "success", "passed", "approved", "done"}


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


def scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def append_progress_log(task_dir: Path, event: str, detail: str) -> None:
    with (task_dir / "progress.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_now_z()} | {event} | {detail}\n")


def run_python_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        capture_output=True,
    )


def pending_proposal_count(proposals_path: Path) -> int:
    payload = load_json(proposals_path)
    return sum(
        1
        for item in payload.get("proposals") or []
        if isinstance(item, dict) and item.get("status") == "approval_required"
    )


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip(".-")


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
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


def relative_context_ref(path: Path, task_dir: Path) -> str:
    try:
        return str(path.relative_to(task_dir))
    except ValueError:
        return str(path)


def existing_mistake_event_identities(task_dir: Path) -> set[tuple[str, str]]:
    identities: set[tuple[str, str]] = set()
    for event in load_jsonl(task_dir / "context" / "mistake-events.jsonl"):
        if event.get("event_type") != "mistake_correction":
            continue
        pattern_key = str(event.get("pattern_key") or "").strip()
        if not pattern_key:
            continue
        provenance = event.get("provenance") if isinstance(event.get("provenance"), dict) else {}
        source_ref = str(provenance.get("source_ref") or "").strip()
        if source_ref:
            identities.add((pattern_key, source_ref))
        for evidence_ref in event.get("evidence_refs") or []:
            evidence = str(evidence_ref).strip()
            if evidence:
                identities.add((pattern_key, evidence))
    return identities


def finding_source_ref(finding: dict) -> str:
    finding_id = str(finding.get("id") or "").strip()
    if not finding_id:
        return ""
    return f"context/finding-register.json#{finding_id}"


def finding_artifact_ref(finding: dict) -> str:
    source = finding.get("source")
    if isinstance(source, dict):
        artifact = str(source.get("artifact") or "").strip()
        if artifact:
            return artifact
    if isinstance(source, str) and source.strip():
        return source.strip()
    return ""


def finding_target_assets(finding: dict) -> list[str]:
    assets: list[str] = []
    seen: set[str] = set()
    affected = finding.get("affected")
    if not isinstance(affected, list):
        return assets
    for item in affected:
        if not isinstance(item, dict):
            continue
        file_ref = str(item.get("file") or "").strip()
        if file_ref and file_ref not in seen:
            seen.add(file_ref)
            assets.append(file_ref)
    return assets


def finding_pattern_key(finding: dict) -> str:
    learning = finding.get("learning")
    if isinstance(learning, dict):
        explicit = str(learning.get("pattern_key") or "").strip()
        if explicit:
            return slug(explicit)

    finding_id = slug(str(finding.get("id") or ""))
    assets = finding_target_assets(finding)
    if not (finding_id and assets):
        return ""
    asset_key = slug(assets[0])[:80]
    return f"review-finding-{asset_key}-{finding_id}"


def finding_correction_event(finding: dict, task_dir: Path, now: str):
    source_ref = finding_source_ref(finding)
    artifact_ref = finding_artifact_ref(finding)
    pattern_key = finding_pattern_key(finding)
    title = str(finding.get("title") or "").strip()
    recommended_fix = str(finding.get("recommended_fix") or "").strip()
    resolution_note = str(finding.get("resolution_note") or "").strip()
    target_assets = finding_target_assets(finding)
    verification = finding.get("verification")

    if not (
        source_ref
        and artifact_ref
        and pattern_key
        and title
        and recommended_fix
        and (resolution_note or isinstance(verification, dict))
        and target_assets
    ):
        return None

    evidence_refs = [source_ref, artifact_ref, "context/manual-fallback-repair.json"]
    quality_evidence = task_dir / "context" / "quality-evidence.md"
    if quality_evidence.is_file():
        evidence_refs.append(relative_context_ref(quality_evidence, task_dir))

    return {
        "schema_version": 1,
        "event_type": "mistake_correction",
        "recorded_at": now,
        "surface": "current_session_fallback",
        "mistake_type": "review_learning_not_ingested",
        "pattern_key": pattern_key,
        "original_decision": title,
        "corrected_decision": resolution_note or recommended_fix,
        "correction_source": "reviewer_finding_register",
        "summary": f"Fixed reviewer finding: {title}",
        "evidence_refs": sorted(dict.fromkeys(evidence_refs)),
        "target_assets": target_assets,
        "non_blocking": True,
        "provenance": {
            "source_ref": source_ref,
            "explicit_reviewer_finding": True,
            "inferred": False,
        },
    }


def materialize_current_session_fallback_learning(
    task_dir: Path,
    *,
    original_host_bridge_status: str,
    status: str,
    now: str,
) -> dict:
    result = {
        "status": "skipped",
        "recorded": 0,
        "skipped_existing": 0,
        "skipped_insufficient": 0,
        "source": "context/finding-register.json",
        "errors": [],
    }
    if status != "completed":
        result["reason"] = "repair_status_not_completed"
        return result
    if original_host_bridge_status != "current_session_required":
        result["reason"] = "not_current_session_fallback"
        return result

    register = load_json(task_dir / "context" / "finding-register.json")
    findings = register.get("findings") if isinstance(register, dict) else None
    if not isinstance(findings, list):
        result["reason"] = "finding_register_missing"
        return result

    identities = existing_mistake_event_identities(task_dir)
    writable_events: list[dict] = []
    for finding in findings:
        if not isinstance(finding, dict):
            result["skipped_insufficient"] += 1
            continue
        if str(finding.get("status") or "").strip() != "fixed":
            continue
        event = finding_correction_event(finding, task_dir, now)
        if not event:
            result["skipped_insufficient"] += 1
            continue
        identity = (event["pattern_key"], event["provenance"]["source_ref"])
        if identity in identities:
            result["skipped_existing"] += 1
            continue
        identities.add(identity)
        writable_events.append(event)

    if not writable_events:
        result["status"] = "completed"
        return result

    try:
        for event in writable_events:
            append_jsonl(task_dir / "context" / "mistake-events.jsonl", event)
    except Exception:
        result["status"] = "failed"
        result["errors"].append("learning_materialization_failed")
        return result

    result["status"] = "completed"
    result["recorded"] = len(writable_events)
    append_progress_log(
        task_dir,
        "EVOLUTION_LEARNING_MATERIALIZED",
        f"source=context/finding-register.json recorded={len(writable_events)}",
    )
    return result


def run_evolution_closeout(
    args: argparse.Namespace,
    state_dir: Path,
    task_dir: Path,
    *,
    original_host_bridge_status: str = "",
) -> dict:
    status = {
        "analyzer": "skipped",
        "proposals": "skipped",
        "pending_proposals": 0,
        "artifacts": [],
        "errors": [],
        "learning_materialization": {
            "status": "skipped",
            "recorded": 0,
            "skipped_existing": 0,
            "skipped_insufficient": 0,
            "errors": [],
        },
    }
    if args.status != "completed":
        status["reason"] = "repair_status_not_completed"
        return status
    if os.environ.get("AGENT_CREW_EVOLUTION_MODE", "report") == "off":
        status["reason"] = "disabled"
        append_progress_log(task_dir, "EVOLUTION_ANALYZER_SKIPPED", "reason=disabled")
        append_progress_log(task_dir, "EVOLUTION_PROPOSALS_SKIPPED", "reason=disabled")
        return status

    context_dir = task_dir / "context"
    analyzer = scripts_dir() / "evolution-analyzer.py"
    aggregate = scripts_dir() / "evolution-proposal-aggregate.py"
    summary = scripts_dir() / "evolution-proposal-summary.py"
    report_json = context_dir / "evolution-report.json"
    report_md = context_dir / "evolution-report.md"
    proposals_json = state_dir / "learning-candidates" / "proposals.json"
    proposals_summary = context_dir / "evolution-proposals-summary.txt"

    materialization = materialize_current_session_fallback_learning(
        task_dir,
        original_host_bridge_status=original_host_bridge_status,
        status=args.status,
        now=utc_now_z(),
    )
    status["learning_materialization"] = materialization
    status["errors"].extend(materialization.get("errors") or [])
    if materialization.get("status") == "failed":
        append_progress_log(task_dir, "EVOLUTION_LEARNING_MATERIALIZATION_FAILED", "non_blocking=true")

    if analyzer.is_file():
        result = run_python_script(
            analyzer,
            "--state-dir", str(state_dir),
            "--task-dir", str(task_dir),
            "--json-output", str(report_json),
            "--markdown-output", str(report_md),
        )
        if result.returncode == 0 and report_json.is_file() and report_md.is_file():
            status["analyzer"] = "completed"
            status["artifacts"].extend([
                "context/evolution-report.json",
                "context/evolution-report.md",
            ])
            append_progress_log(
                task_dir,
                "EVOLUTION_ANALYZER",
                "mode=repair artifacts=context/evolution-report.json,context/evolution-report.md",
            )
        else:
            status["analyzer"] = "failed"
            status["errors"].append("evolution_analyzer_failed")
            append_progress_log(task_dir, "EVOLUTION_ANALYZER_FAILED", "non_blocking=true")
    else:
        status["reason"] = "analyzer_script_missing"
        append_progress_log(task_dir, "EVOLUTION_ANALYZER_SKIPPED", "reason=script_missing")

    if not (aggregate.is_file() and summary.is_file()):
        status["proposals"] = "skipped"
        status["errors"].append("proposal_script_missing")
        append_progress_log(task_dir, "EVOLUTION_PROPOSALS_SKIPPED", "reason=script_missing")
        return status

    aggregate_result = run_python_script(
        aggregate,
        "--state-dir", str(state_dir),
        "--output", str(proposals_json),
        "--format", "json",
    )
    if aggregate_result.returncode != 0:
        status["proposals"] = "failed"
        status["errors"].append("proposal_aggregate_failed")
        append_progress_log(task_dir, "EVOLUTION_PROPOSALS_FAILED", "non_blocking=true")
        return status

    count = pending_proposal_count(proposals_json)
    status["pending_proposals"] = count
    if count <= 0:
        proposals_summary.unlink(missing_ok=True)
        status["proposals"] = "skipped"
        append_progress_log(task_dir, "EVOLUTION_PROPOSALS_SKIPPED", "reason=no_repeated_evidence")
        return status

    summary_result = run_python_script(
        summary,
        "--proposals", str(proposals_json),
        "--format", "text",
    )
    if summary_result.returncode != 0:
        status["proposals"] = "failed"
        status["errors"].append("proposal_summary_failed")
        append_progress_log(task_dir, "EVOLUTION_PROPOSALS_FAILED", "non_blocking=true")
        return status

    proposals_summary.write_text(summary_result.stdout, encoding="utf-8")
    status["proposals"] = "completed"
    status["artifacts"].extend([
        "learning-candidates/proposals.json",
        "context/evolution-proposals-summary.txt",
    ])
    append_progress_log(
        task_dir,
        "EVOLUTION_PROPOSALS",
        f"pending={count} output=learning-candidates/proposals.json summary=context/evolution-proposals-summary.txt",
    )
    return status


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
    return shared_looks_mutating_task(task or "")


def looks_quality_gated_task(task: str) -> bool:
    text = task or ""
    if not looks_mutating_task(text):
        return False
    if not QUALITY_GATED_TASK_RE.search(text):
        return False
    if ARTIFACT_CODE_OWNER_OUTPUT_RE.search(text):
        return False
    if ARTIFACT_CODE_OWNER_RE.search(text):
        return True
    if (
        NON_PRODUCTION_ARTIFACT_RE.search(text)
        and not ASSET_SOURCE_CODE_RE.search(text)
        and not ARTIFACT_CODE_OWNER_RE.search(text)
    ):
        return False
    if EXPLICIT_CODE_CHANGE_RE.search(text):
        return True
    if OPERATIONAL_ASSET_UPDATE_RE.search(text):
        return False
    if OPERATIONAL_UPDATE_RE.search(text) and not (
        IMPLEMENTATION_INTENT_RE.search(text) and DOMAIN_CHANGE_RE.search(text)
    ):
        return False

    return not NON_PRODUCTION_ARTIFACT_RE.search(text)


def looks_commit_mutation_task(task: str) -> bool:
    return bool(COMMIT_MUTATION_RE.search(task or ""))


def evidence_name(task_dir: Path, path: Path) -> str:
    return str(path.relative_to(task_dir)) if path.is_relative_to(task_dir) else str(path)


def inspect_evidence_file(task_dir: Path, path: Path, inspected_paths: list[str]) -> tuple[str, str] | None:
    if not path.is_file():
        return None

    inspected_paths.append(str(path))
    return evidence_name(task_dir, path), path.read_text(encoding="utf-8", errors="replace")


def resolve_quality_paths(task_dir: Path, paths: list[str]) -> list[Path]:
    candidates = [
        task_dir / "context" / "tdd-red.md",
        task_dir / "context" / "tdd-red.json",
        task_dir / "context" / "tdd-exception.md",
        task_dir / "context" / "tdd-exception.json",
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


def resolve_refactor_paths(task_dir: Path, paths: list[str]) -> list[Path]:
    candidates = [
        task_dir / "context" / "tdd-refactor.md",
        task_dir / "context" / "tdd-refactor.json",
    ]
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = task_dir / value
        if "refactor" in path.name.lower():
            candidates.append(path)
    return candidates


def quality_evidence_status(task_dir: Path, paths: list[str]) -> dict:
    tdd_paths: list[str] = []
    red_phase_paths: list[str] = []
    exception_paths: list[str] = []
    refactor_phase_paths: list[str] = []
    review_paths: list[str] = []
    inspected_paths: list[str] = []
    for path in resolve_quality_paths(task_dir, paths):
        inspected = inspect_evidence_file(task_dir, path, inspected_paths)
        if inspected is None:
            continue

        rel_name, text = inspected
        if TDD_RE.search(text):
            tdd_paths.append(rel_name)
        if RED_PHASE_RE.search(text):
            red_phase_paths.append(rel_name)
        if TDD_EXCEPTION_RE.search(text):
            exception_paths.append(rel_name)
        if REVIEW_RE.search(text):
            review_paths.append(rel_name)
    for path in resolve_refactor_paths(task_dir, paths):
        inspected = inspect_evidence_file(task_dir, path, inspected_paths)
        if inspected is None:
            continue

        rel_name, text = inspected
        if REFACTOR_PHASE_RE.search(text):
            refactor_phase_paths.append(rel_name)
    return {
        "required": True,
        "passed": bool(tdd_paths and review_paths),
        "tdd_evidence_paths": sorted(set(tdd_paths)),
        "red_phase_evidence_paths": sorted(set(red_phase_paths)),
        "tdd_exception_paths": sorted(set(exception_paths)),
        "refactor_phase_evidence_paths": sorted(set(refactor_phase_paths)),
        "review_evidence_paths": sorted(set(review_paths)),
        "inspected_paths": sorted(set(inspected_paths)),
    }


def resolve_specialist_paths(task_dir: Path, paths: list[str]) -> list[Path]:
    candidates = [
        task_dir / "context" / "specialist-dispatch.md",
        task_dir / "context" / "specialist-dispatch.json",
        task_dir / "context" / "codex-skill-context.md",
        task_dir / "context" / "requirements.md",
    ]
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = task_dir / value
        candidates.append(path)
    return candidates


def specialist_dispatch_status(task_dir: Path, paths: list[str]) -> dict:
    matched_paths: list[str] = []
    inspected_paths: list[str] = []
    incomplete_paths: dict[str, list[str]] = {}
    selected_agents: list[str] = []
    selected_user_agents: list[str] = []
    selected_subagents: list[str] = []
    selected_skills: list[str] = []
    selected_handlers: dict[str, set[str]] = {}
    for path in resolve_specialist_paths(task_dir, paths):
        inspected = inspect_evidence_file(task_dir, path, inspected_paths)
        if inspected is None:
            continue

        rel_name, text = inspected
        parsed = specialist_fields_from_text(text)
        if parsed:
            missing = [
                field
                for field in ("selected_agent", "selection_reason", "execution_mode")
                if not parsed.get(field)
            ]
            if missing:
                incomplete_paths[rel_name] = missing
                continue

            matched_paths.append(rel_name)
            selected_agents.extend(parsed.get("selected_agent", []))
            selected_user_agents.extend(parsed.get("selected_user_agent", []))
            selected_subagents.extend(parsed.get("selected_subagents", []))
            selected_skills.extend(parsed.get("selected_skill", []))
            for capability, handlers in parsed.get("selected_handlers", {}).items():
                selected_handlers.setdefault(capability, set()).update(handlers)
        elif SPECIALIST_DISPATCH_RE.search(text):
            incomplete_paths[rel_name] = ["selected_agent", "selection_reason", "execution_mode"]
    return {
        "required": True,
        "passed": bool(matched_paths) and not incomplete_paths,
        "matched_paths": sorted(set(matched_paths)),
        "incomplete_paths": {path: sorted(set(fields)) for path, fields in incomplete_paths.items()},
        "missing_fields": [] if matched_paths or incomplete_paths else [
            "selected_agent",
            "selection_reason",
            "execution_mode",
        ],
        "selected_agents": sorted(set(selected_agents)),
        "selected_user_agents": sorted(set(selected_user_agents)),
        "selected_subagents": sorted(set(selected_subagents)),
        "selected_skills": sorted(set(selected_skills)),
        "selected_handlers": {
            capability: sorted(handlers)
            for capability, handlers in sorted(selected_handlers.items())
        },
        "inspected_paths": sorted(set(inspected_paths)),
        "advisory": False,
        "reason": "",
        "bypassed": False,
        "bypass_reason": "",
    }


def legacy_commit_capability_provider_paths(task_dir: Path, register: dict) -> list[str]:
    candidates: list[Path] = []
    project_root = str(register.get("project_root") or "").strip()
    if project_root:
        root = Path(project_root).expanduser()
        candidates.extend(
            [
                root / ".agent-crew" / "agents" / "git-committer.md",
                root / ".codex" / "agents" / "git-committer.toml",
            ]
        )

    agent_crew_home = Path(
        os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew"))
    ).expanduser()
    candidates.extend(
        [
            agent_crew_home / "user" / "agents" / "git-committer.md",
            agent_crew_home / "system" / "agents" / "git-committer.md",
            agent_crew_home / "agents" / "git-committer.md",
        ]
    )

    local_state = task_dir.parent.parent
    candidates.append(local_state / "agents" / "git-committer.md")

    return [str(path) for path in candidates if path.is_file()]


def normalize_agent_name(value: str) -> str:
    raw = value.strip().strip("`'\"")
    if not raw:
        return ""

    name = Path(raw).name
    for suffix in (".md", ".toml"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.lower()


def split_handler_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(split_handler_values(item))
        return values
    return [
        normalize_agent_name(part)
        for part in split_specialist_values(str(value))
        if normalize_agent_name(part)
    ]


def selected_handlers_from_value(value: object) -> dict[str, list[str]]:
    handlers: dict[str, list[str]] = {}
    if value is None:
        return handlers
    if isinstance(value, dict):
        items = [{"capability": capability, "handler": handler} for capability, handler in value.items()]
    elif isinstance(value, list):
        items = value
    else:
        items = [value]

    for item in items:
        capability = ""
        handler_values: list[str] = []
        if isinstance(item, dict):
            capability = str(item.get("capability") or "").strip()
            handler_values = split_handler_values(item.get("handler") or item.get("handlers"))
        else:
            text = str(item or "").strip()
            if "=" in text:
                capability, raw_handler = text.split("=", 1)
                capability = capability.strip()
                handler_values = split_handler_values(raw_handler)
        if not capability:
            continue
        handlers.setdefault(capability, [])
        for handler in handler_values:
            if handler and handler not in handlers[capability]:
                handlers[capability].append(handler)
    return handlers


def merge_completed_handler_maps(target: dict[str, list[str]], source: dict[str, list[str]]) -> dict[str, list[str]]:
    for capability, handlers in source.items():
        target.setdefault(capability, [])
        for handler in handlers:
            normalized = normalize_agent_name(handler)
            if normalized and normalized not in target[capability]:
                target[capability].append(normalized)
    return target


def completed_handlers_from_result_item(item: object, *, default_completed: bool = False) -> dict[str, list[str]]:
    if not isinstance(item, dict):
        if default_completed:
            return selected_handlers_from_value(item)
        return {}

    nested: dict[str, list[str]] = {}
    for key in ("handler_results", "capability_results"):
        if key in item:
            merge_completed_handler_maps(
                nested,
                completed_handlers_from_value(item.get(key), default_completed=False),
            )
    if "completed_handlers" in item:
        merge_completed_handler_maps(
            nested,
            completed_handlers_from_value(item.get("completed_handlers"), default_completed=True),
        )

    capability = str(item.get("capability") or "").strip()
    state = str(item.get("state") or "").strip().lower()
    handlers = split_handler_values(item.get("handler") or item.get("handlers"))
    if capability and handlers and (default_completed or state in COMPLETED_CAPABILITY_STATES):
        merge_completed_handler_maps(nested, {capability: handlers})
    return nested


def completed_handlers_from_value(value: object, *, default_completed: bool = False) -> dict[str, list[str]]:
    completed: dict[str, list[str]] = {}
    if value is None:
        return completed
    if isinstance(value, dict):
        if "capability" in value or any(
            key in value for key in ("handler_results", "capability_results", "completed_handlers")
        ):
            return completed_handlers_from_result_item(value, default_completed=default_completed)
        if default_completed:
            return selected_handlers_from_value(value)
        return completed
    if isinstance(value, list):
        for item in value:
            merge_completed_handler_maps(
                completed,
                completed_handlers_from_value(item, default_completed=default_completed),
            )
        return completed
    if default_completed:
        return selected_handlers_from_value(value)
    return completed


def merge_handler_maps(target: dict[str, list[str]], source: dict[str, list[str]]) -> dict[str, list[str]]:
    for capability, handlers in source.items():
        target.setdefault(capability, [])
        for handler in handlers:
            normalized = normalize_agent_name(handler)
            if normalized and normalized not in target[capability]:
                target[capability].append(normalized)
    return target


def legacy_agent_handlers(values: object) -> dict[str, list[str]]:
    handlers: dict[str, list[str]] = {}
    for agent in split_handler_values(values):
        for capability in LEGACY_AGENT_CAPABILITIES.get(agent, []):
            handlers.setdefault(capability, [])
            if agent not in handlers[capability]:
                handlers[capability].append(agent)
    return handlers


def apply_legacy_agent_translation(fields: dict[str, list[str] | str]) -> dict[str, list[str] | str]:
    selected_user_agents = fields.get("selected_user_agent", [])
    if not isinstance(selected_user_agents, list):
        return fields

    existing_handlers = fields.get("selected_handlers", {})
    handlers = existing_handlers if isinstance(existing_handlers, dict) else {}
    handlers = merge_handler_maps(handlers, legacy_agent_handlers(selected_user_agents))
    if handlers:
        fields["selected_handlers"] = handlers
    else:
        fields.pop("selected_handlers", None)
    return fields


def required_capabilities_from_context(task_dir: Path, register: dict) -> list[str]:
    capabilities: list[str] = []

    def add_many(values: object) -> None:
        if isinstance(values, str):
            iterable = split_specialist_values(values)
        elif isinstance(values, list):
            iterable = [str(value) for value in values]
        else:
            iterable = []
        for value in iterable:
            capability = value.strip()
            if capability and capability not in capabilities:
                capabilities.append(capability)

    add_many(register.get("required_capabilities"))
    add_many(required_capabilities_for_task(str(register.get("task") or "")))
    for path in (
        task_dir / "context" / "required-capabilities.json",
        task_dir / "context" / "input-normalization.json",
    ):
        payload = load_json(path)
        if payload:
            add_many(payload.get("required_capabilities"))
    return capabilities


def resolve_capability_result_paths(task_dir: Path, paths: list[str]) -> list[Path]:
    context_dir = task_dir / "context"
    candidates = [
        context_dir / "handler-results.json",
        context_dir / "capability-results.json",
    ]
    capabilities_dir = context_dir / "capabilities"
    if capabilities_dir.is_dir():
        candidates.extend(sorted(capabilities_dir.glob("*.json")))
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = task_dir / value
        candidates.append(path)
    return candidates


def capability_completion_status(task_dir: Path, paths: list[str]) -> dict:
    matched_paths: list[str] = []
    inspected_paths: list[str] = []
    completed_handlers: dict[str, set[str]] = {}
    for path in resolve_capability_result_paths(task_dir, paths):
        inspected = inspect_evidence_file(task_dir, path, inspected_paths)
        if inspected is None:
            continue

        rel_name, text = inspected
        parsed: dict[str, list[str]] = {}
        try:
            parsed = completed_handlers_from_value(json.loads(text))
        except Exception:
            parsed = {}
        if not parsed:
            for line in text.splitlines():
                match = re.match(
                    r"\s*[-*]?\s*(?:completed_handler|completed_handlers|handler_result|capability_result)\s*[:=]\s*(.+)",
                    line,
                    re.I,
                )
                if match:
                    merge_completed_handler_maps(
                        parsed,
                        completed_handlers_from_value(match.group(1), default_completed=True),
                    )
        if not parsed:
            continue

        matched_paths.append(rel_name)
        for capability, handlers in parsed.items():
            completed_handlers.setdefault(capability, set()).update(handlers)
    return {
        "required": True,
        "passed": bool(matched_paths),
        "matched_paths": sorted(set(matched_paths)),
        "inspected_paths": sorted(set(inspected_paths)),
        "completed_handlers": {
            capability: sorted(handlers)
            for capability, handlers in sorted(completed_handlers.items())
        },
    }


def capability_selected(capability: str, specialist_gate: dict) -> bool:
    selected_handlers = specialist_gate.get("selected_handlers", {})
    handlers = [normalize_agent_name(handler) for handler in selected_handlers.get(capability, [])]
    return bool(handlers)


def capability_satisfied(capability: str, specialist_gate: dict, completion_gate: dict) -> bool:
    selected_handlers = {
        normalize_agent_name(handler)
        for handler in specialist_gate.get("selected_handlers", {}).get(capability, [])
    }
    completed_handlers = {
        normalize_agent_name(handler)
        for handler in completion_gate.get("completed_handlers", {}).get(capability, [])
    }
    return bool(selected_handlers.intersection(completed_handlers))


def enforce_required_capability_gate(
    args: argparse.Namespace,
    task_dir: Path,
    register: dict,
    specialist_gate: dict,
) -> dict:
    host_bridge_status = str(register.get("host_bridge_status") or "")
    current_session_fallback = host_bridge_status == "current_session_required"
    required_capabilities = required_capabilities_from_context(task_dir, register)
    capability_specialist_gate = specialist_gate
    if required_capabilities and not specialist_gate.get("selected_handlers"):
        capability_specialist_gate = specialist_dispatch_status(
            task_dir,
            list(args.evidence) + list(args.specialist_evidence),
        )
    completion_gate = capability_completion_status(
        task_dir,
        list(args.evidence) + list(args.specialist_evidence),
    )
    required = bool(args.status == "completed" and current_session_fallback and required_capabilities)
    missing_selection = [
        capability
        for capability in required_capabilities
        if not capability_selected(capability, capability_specialist_gate)
    ]
    missing_completion = [
        capability
        for capability in required_capabilities
        if capability_selected(capability, capability_specialist_gate)
        and not capability_satisfied(capability, capability_specialist_gate, completion_gate)
    ]
    status = {
        "required": required,
        "passed": not missing_selection and not missing_completion,
        "required_capabilities": required_capabilities,
        "missing_capabilities": missing_selection,
        "missing_completion_capabilities": missing_completion,
        "selected_handlers": capability_specialist_gate.get("selected_handlers", {}),
        "completed_handlers": completion_gate.get("completed_handlers", {}),
        "completion_evidence_paths": completion_gate.get("matched_paths", []),
        "advisory": False,
        "reason": "",
        "bypassed": False,
        "bypass_reason": "",
    }
    if not required or (not missing_selection and not missing_completion):
        return status

    if args.specialist_bypass_reason:
        status["bypassed"] = True
        status["bypass_reason"] = args.specialist_bypass_reason
        return status

    status["advisory"] = True
    status["reason"] = (
        "required capability coverage is incomplete; repair records this gap "
        "without requiring separate handler proof artifacts"
    )
    return status


def enforce_commit_specialist_gate(
    args: argparse.Namespace,
    task_dir: Path,
    register: dict,
    specialist_gate: dict,
) -> dict:
    task = register.get("task", "")
    host_bridge_status = str(register.get("host_bridge_status") or "")
    current_session_fallback = host_bridge_status == "current_session_required"
    available_paths = legacy_commit_capability_provider_paths(task_dir, register)
    required_capabilities = required_capabilities_for_task(task)
    required = bool(
        args.status == "completed"
        and current_session_fallback
        and looks_commit_mutation_task(task)
        and available_paths
        and required_capabilities
    )
    status = {
        "required": required,
        "passed": True,
        "available_paths": available_paths,
        "selected_user_agents": sorted(set(specialist_gate.get("selected_user_agents", []))),
        "selected_handlers": specialist_gate.get("selected_handlers", {}),
        "required_capabilities": required_capabilities,
        "completed_handlers": {},
        "completion_evidence_paths": [],
        "advisory": False,
        "reason": "",
        "bypassed": False,
        "bypass_reason": "",
    }
    if not required:
        return status

    completion_gate = capability_completion_status(
        task_dir,
        list(args.evidence) + list(args.specialist_evidence),
    )
    status["completed_handlers"] = completion_gate.get("completed_handlers", {})
    status["completion_evidence_paths"] = completion_gate.get("matched_paths", [])
    missing_selection = [
        capability
        for capability in required_capabilities
        if not capability_selected(capability, specialist_gate)
    ]
    missing_completion = [
        capability
        for capability in required_capabilities
        if capability_selected(capability, specialist_gate)
        and not capability_satisfied(capability, specialist_gate, completion_gate)
    ]
    if not missing_selection and not missing_completion:
        return status

    status["passed"] = False
    status["missing_capabilities"] = missing_selection
    status["missing_completion_capabilities"] = missing_completion
    if args.specialist_bypass_reason:
        status["bypassed"] = True
        status["bypass_reason"] = args.specialist_bypass_reason
        return status

    status["advisory"] = True
    status["reason"] = (
        "commit capability coverage is incomplete; repair records this gap "
        "without requiring separate handler proof artifacts"
    )
    return status


def split_specialist_values(value: str) -> list[str]:
    cleaned = value.strip().strip("[]")
    parts = re.split(r"[,|]", cleaned)
    values = [
        part.strip().strip("'\"`")
        for part in parts
        if part.strip().strip("'\"`")
    ]
    return [
        value for value in values
        if not value.lower().startswith(("none", "n/a", "null", "reason"))
    ]


def normalize_skill_name(value: str) -> str:
    raw = value.strip().strip("`")
    if not raw:
        return ""
    name = Path(raw).name
    if name.endswith(".md"):
        return name
    if "/" not in raw and "\\" not in raw:
        return f"{raw}.md"
    return f"{name}.md" if name else ""


def specialist_fields_from_text(text: str) -> dict[str, list[str] | str]:
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        return specialist_fields_from_json(payload)

    fields: dict[str, list[str] | str] = {}
    for line in text.splitlines():
        match = SPECIALIST_FIELD_RE.match(line)
        if not match:
            continue

        key = match.group(1).lower()
        value = match.group(2).strip()
        if key in {"selection_reason", "execution_mode"}:
            fields[key] = value
            continue
        if key in {"selected_handler", "selected_handlers"}:
            existing_handlers = fields.get("selected_handlers", {})
            handlers = existing_handlers if isinstance(existing_handlers, dict) else {}
            for capability, selected in selected_handlers_from_value(value).items():
                handlers.setdefault(capability, [])
                for handler in selected:
                    if handler not in handlers[capability]:
                        handlers[capability].append(handler)
            fields["selected_handlers"] = handlers
            continue

        canonical = {
            "selected_agents": "selected_agent",
            "selected_user_agents": "selected_user_agent",
            "selected_subagent": "selected_subagents",
            "selected_skill": "selected_skill",
            "selected_skills": "selected_skill",
        }.get(key, key)
        existing = fields.get(canonical, [])
        values = existing if isinstance(existing, list) else []
        values.extend(split_specialist_values(value))
        fields[canonical] = values
    return apply_legacy_agent_translation(fields)


def specialist_fields_from_json(payload: dict) -> dict[str, list[str] | str]:
    fields: dict[str, list[str] | str] = {}
    for source, canonical in (
        ("selected_agent", "selected_agent"),
        ("selected_agents", "selected_agent"),
        ("selected_user_agent", "selected_user_agent"),
        ("selected_user_agents", "selected_user_agent"),
        ("selected_subagent", "selected_subagents"),
        ("selected_subagents", "selected_subagents"),
        ("selected_skill", "selected_skill"),
        ("selected_skills", "selected_skill"),
    ):
        value = payload.get(source)
        if value is None:
            continue

        values = value if isinstance(value, list) else [value]
        existing = fields.get(canonical, [])
        current = existing if isinstance(existing, list) else []
        for item in values:
            current.extend(split_specialist_values(str(item)))
        fields[canonical] = current

    for key in ("selection_reason", "execution_mode"):
        value = payload.get(key)
        if value is not None:
            fields[key] = str(value).strip()
    handlers = selected_handlers_from_value(payload.get("selected_handlers") or payload.get("selected_handler"))
    if handlers:
        fields["selected_handlers"] = handlers
    return apply_legacy_agent_translation(fields)


def resolve_skill_load_paths(task_dir: Path, paths: list[str]) -> list[Path]:
    candidates = [
        task_dir / "context" / "skill-load.md",
        task_dir / "context" / "skill-load.json",
        task_dir / "context" / "codex-skill-context.md",
    ]
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = task_dir / value
        candidates.append(path)
    return candidates


def skill_name_from_path(value: str) -> str:
    path = Path(value.strip().strip("`"))
    name = path.name
    if name == "SKILL.md" and path.parent.name:
        return f"{path.parent.name}.md"
    return name


def extract_loaded_skill_paths(text: str) -> list[str]:
    paths: list[str] = []
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    if payload is not None:
        paths.extend(extract_loaded_skill_paths_from_json(payload))

    for line in text.splitlines():
        if not re.match(r"\s*[-*]\s+", line):
            continue
        for match in re.finditer(r"(?:~|/|\.\.?/|[A-Za-z0-9_.-]+/)[^\s`,'\")]+\.md", line):
            path = match.group(0).strip()
            if path.startswith("context/") or "/context/" in path:
                continue
            if "/skills/" in path or "/rules/" in path or path.startswith(("core/rules/", "core/agents/skills/")):
                paths.append(path)
    return sorted(set(paths))


def extract_loaded_skill_paths_from_json(value: object) -> list[str]:
    paths: list[str] = []
    if isinstance(value, str):
        if value.endswith(".md"):
            paths.append(value)
        return paths
    if isinstance(value, list):
        for item in value:
            paths.extend(extract_loaded_skill_paths_from_json(item))
        return paths
    if not isinstance(value, dict):
        return paths

    for key in ("loaded_skills", "skills"):
        paths.extend(extract_loaded_skill_paths_from_json(value.get(key)))
    for key in ("skill_path", "path"):
        paths.extend(extract_loaded_skill_paths_from_json(value.get(key)))
    return paths


def expanded_skill_path(value: str) -> str:
    return str(Path(value.strip().strip("`")).expanduser())


def is_agent_crew_owned_skill_path(value: str) -> bool:
    expanded = expanded_skill_path(value)
    normalized = expanded.replace("\\", "/")
    return (
        "/.agent-crew/system/skills/" in normalized
        or "/.agent-crew/user/skills/" in normalized
        or "/.agent-crew/skills/" in normalized
        or "/.agent-crew/system/agents/skills/" in normalized
        or "/.agent-crew/agents/skills/" in normalized
        or "/core/agents/skills/" in normalized
        or normalized.startswith("core/agents/skills/")
        or normalized.startswith("core/rules/")
        or "/.claude/agent-crew/skills/" in normalized
        or "/.claude/agent-crew/agents/skills/" in normalized
        or "/.codex/skills/agent-crew/" in normalized
        or "/.codex/skills/crew-" in normalized
        or "/.codex/agent-crew/skills/" in normalized
        or "/adapters/claude/skill/" in normalized
        or "/adapters/codex/skill/crew-" in normalized
        or "/adapters/codex/skill/agent-crew/" in normalized
    )


def external_skill_approval_text(task_dir: Path) -> str:
    texts: list[str] = []
    for path in (
        task_dir / "context" / "external-skill-approval.md",
        task_dir / "context" / "external-skill-approval.json",
    ):
        if path.is_file():
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(texts)


def approved_external_skill_paths(task_dir: Path) -> set[str]:
    text = external_skill_approval_text(task_dir)
    if not text:
        return set()

    approved: set[str] = set()
    for path in extract_loaded_skill_paths(text):
        approved.add(expanded_skill_path(path))
    for match in re.finditer(r"(?:~|/|\.\.?/|[A-Za-z0-9_.-]+/)[^\s`,'\")]+\.md", text):
        approved.add(expanded_skill_path(match.group(0).strip()))
    try:
        payload = json.loads(text)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        for key in ("approved_skills", "approved_skill_paths", "skills"):
            for path in extract_loaded_skill_paths_from_json(payload.get(key)):
                approved.add(expanded_skill_path(path))
    return approved


def external_skill_load_status(task_dir: Path, loaded_skill_paths: list[str]) -> dict:
    external = sorted({
        path for path in loaded_skill_paths
        if path and not is_agent_crew_owned_skill_path(path)
    })
    approved = approved_external_skill_paths(task_dir)
    unapproved = [
        path for path in external
        if expanded_skill_path(path) not in approved
    ]
    return {
        "external_skill_paths": external,
        "unapproved_external_skill_paths": sorted(unapproved),
        "approval_paths": [
            evidence_name(task_dir, path)
            for path in (
                task_dir / "context" / "external-skill-approval.md",
                task_dir / "context" / "external-skill-approval.json",
            )
            if path.is_file()
        ],
    }


def required_skill_names(task_dir: Path, register: dict, specialist_paths: list[str]) -> list[str]:
    snippets = [str(register.get("task") or "")]
    selected_skill_names: list[str] = []
    for path in resolve_specialist_paths(task_dir, specialist_paths):
        inspected: list[str] = []
        evidence = inspect_evidence_file(task_dir, path, inspected)
        if evidence is None:
            continue

        _rel_name, text = evidence
        snippets.append(text)
        parsed = specialist_fields_from_text(text)
        selected = parsed.get("selected_skill", []) if parsed else []
        if isinstance(selected, list):
            selected_skill_names.extend(selected)

    required: list[str] = []
    if any(TDD_SKILL_SELECTION_RE.search(text) for text in snippets):
        required.append("tdd.md")
    for selected in selected_skill_names:
        skill = normalize_skill_name(selected)
        if skill:
            required.append(skill)
    return sorted(set(required))


def skill_load_status(
    task_dir: Path,
    register: dict,
    skill_load_paths: list[str],
    specialist_paths: list[str],
) -> dict:
    matched_paths: list[str] = []
    inspected_paths: list[str] = []
    loaded_skill_paths: list[str] = []
    loaded_text = ""
    for path in resolve_skill_load_paths(task_dir, skill_load_paths):
        inspected = inspect_evidence_file(task_dir, path, inspected_paths)
        if inspected is None:
            continue

        rel_name, text = inspected
        loaded_text += "\n" + text
        extracted_paths = extract_loaded_skill_paths(text)
        if SKILL_LOAD_RE.search(text) or extracted_paths:
            matched_paths.append(rel_name)
            loaded_skill_paths.extend(extracted_paths)

    required_skills = required_skill_names(task_dir, register, specialist_paths)
    missing_required_skills: list[str] = []
    loaded_skill_names = {skill_name_from_path(path) for path in loaded_skill_paths}
    for skill in required_skills:
        if skill == "tdd.md" and not TDD_SKILL_PATH_RE.search(loaded_text):
            missing_required_skills.append(skill)
        elif skill != "tdd.md" and skill not in loaded_skill_names:
            missing_required_skills.append(skill)
    external_status = external_skill_load_status(task_dir, loaded_skill_paths)

    return {
        "required": True,
        "passed": (
            bool(matched_paths)
            and not missing_required_skills
            and not external_status["unapproved_external_skill_paths"]
        ),
        "advisory": False,
        "reason": "",
        "matched_paths": sorted(set(matched_paths)),
        "loaded_skill_paths": sorted(set(loaded_skill_paths)),
        "loaded_skill_names": sorted(loaded_skill_names),
        "required_skills": required_skills,
        "missing_required_skills": sorted(set(missing_required_skills)),
        "external_skill_paths": external_status["external_skill_paths"],
        "unapproved_external_skill_paths": external_status["unapproved_external_skill_paths"],
        "external_skill_approval_paths": external_status["approval_paths"],
        "inspected_paths": sorted(set(inspected_paths)),
        "bypassed": False,
        "bypass_reason": "",
    }


def resolve_skill_use_paths(task_dir: Path, paths: list[str]) -> list[Path]:
    candidates = [
        task_dir / "context" / "skill-use.json",
        task_dir / "context" / "skill-use.md",
    ]
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = task_dir / value
        candidates.append(path)
    return candidates


def evidence_field_present(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(evidence_field_present(item) for item in value)
    if isinstance(value, dict):
        return any(evidence_field_present(item) for item in value.values())
    return value is not None


def skill_use_entries_from_json(text: str) -> list[dict]:
    try:
        payload = json.loads(text)
    except Exception:
        return []

    entries = payload.get("skills", payload) if isinstance(payload, dict) else payload
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return []

    return [entry for entry in entries if isinstance(entry, dict)]


def skill_use_entries_from_markdown(text: str) -> list[dict]:
    if not SKILL_USE_RE.search(text):
        return []

    entries: list[dict] = []
    current: dict[str, object] = {}
    for line in text.splitlines():
        match = re.match(r"\s*[-*]?\s*(skill_path|applied_rules|evidence_refs|output_files|verification)\s*:\s*(.+)", line)
        if not match:
            continue

        field, value = match.group(1), match.group(2).strip()
        if field == "skill_path":
            if current:
                entries.append(current)
            current = {"skill_path": value}
        elif current:
            current[field] = value
    if current:
        entries.append(current)
    return entries


def skill_use_status(task_dir: Path, paths: list[str], required_skills: list[str]) -> dict:
    matched_paths: list[str] = []
    inspected_paths: list[str] = []
    complete_skills: set[str] = set()
    incomplete: dict[str, list[str]] = {}
    for path in resolve_skill_use_paths(task_dir, paths):
        inspected = inspect_evidence_file(task_dir, path, inspected_paths)
        if inspected is None:
            continue

        rel_name, text = inspected
        entries = (
            skill_use_entries_from_json(text)
            if path.suffix.lower() == ".json"
            else skill_use_entries_from_markdown(text)
        )
        if entries:
            matched_paths.append(rel_name)

        for entry in entries:
            skill_name = skill_name_from_path(str(entry.get("skill_path") or ""))
            if skill_name not in required_skills:
                continue

            missing_fields = [
                field
                for field in SKILL_USE_REQUIRED_FIELDS
                if not evidence_field_present(entry.get(field))
            ]
            if missing_fields:
                incomplete[skill_name] = sorted(set(incomplete.get(skill_name, []) + missing_fields))
                continue

            complete_skills.add(skill_name)

    missing_skills = sorted(set(required_skills) - complete_skills - set(incomplete))
    return {
        "required": True,
        "passed": bool(required_skills) and not missing_skills and not incomplete,
        "advisory": False,
        "reason": "",
        "matched_paths": sorted(set(matched_paths)),
        "required_skills": sorted(set(required_skills)),
        "complete_skills": sorted(complete_skills),
        "missing_skills": missing_skills,
        "incomplete_skills": incomplete,
        "inspected_paths": sorted(set(inspected_paths)),
        "bypassed": False,
        "bypass_reason": "",
    }


def resolve_skill_plan_paths(task_dir: Path, paths: list[str]) -> list[Path]:
    candidates = [
        task_dir / "context" / "skill-plan.json",
        task_dir / "context" / "skill-plan.md",
    ]
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = task_dir / value
        candidates.append(path)
    return candidates


def entries_from_json_collection(text: str, key: str) -> list[dict]:
    try:
        payload = json.loads(text)
    except Exception:
        return []

    entries = payload.get(key, payload) if isinstance(payload, dict) else payload
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return []

    return [entry for entry in entries if isinstance(entry, dict)]


def rule_id_from_entry(entry: dict) -> str:
    return str(entry.get("rule_id") or entry.get("invariant") or "").strip()


def record_incomplete_fields(incomplete: dict[str, list[str]], skill_name: str, fields: list[str]) -> None:
    incomplete[skill_name] = sorted(set(incomplete.get(skill_name, []) + fields))


def merge_incomplete_skills(*sources: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for source in sources:
        for skill_name, fields in source.items():
            record_incomplete_fields(merged, skill_name, list(fields))
    return merged


def skill_plan_entries_from_markdown(text: str) -> list[dict]:
    if not SKILL_PLAN_RE.search(text):
        return []

    entries: list[dict] = []
    current_skill: dict[str, object] = {}
    current_rule: dict[str, object] = {}
    for line in text.splitlines():
        match = re.match(
            r"\s*[-*]?\s*(skill_path|rule_id|invariant|task_interpretation|planned_application)\s*:\s*(.+)",
            line,
        )
        if not match:
            continue

        field, value = match.group(1), match.group(2).strip()
        if field == "skill_path":
            if current_rule and current_skill:
                current_skill.setdefault("rules", []).append(current_rule)
            if current_skill:
                entries.append(current_skill)
            current_skill = {"skill_path": value, "rules": []}
            current_rule = {}
        elif field in {"rule_id", "invariant"}:
            if current_rule and current_skill:
                current_skill.setdefault("rules", []).append(current_rule)
            current_rule = {field: value}
        elif current_rule:
            current_rule[field] = value
    if current_rule and current_skill:
        current_skill.setdefault("rules", []).append(current_rule)
    if current_skill:
        entries.append(current_skill)
    return entries


def skill_plan_status(task_dir: Path, paths: list[str], required_skills: list[str]) -> dict:
    matched_paths: list[str] = []
    inspected_paths: list[str] = []
    planned_rules: dict[str, list[str]] = {}
    incomplete: dict[str, list[str]] = {}
    for path in resolve_skill_plan_paths(task_dir, paths):
        inspected = inspect_evidence_file(task_dir, path, inspected_paths)
        if inspected is None:
            continue

        rel_name, text = inspected
        entries = (
            entries_from_json_collection(text, "skills")
            if path.suffix.lower() == ".json"
            else skill_plan_entries_from_markdown(text)
        )
        if entries:
            matched_paths.append(rel_name)

        for entry in entries:
            skill_name = skill_name_from_path(str(entry.get("skill_path") or ""))
            if skill_name not in required_skills:
                continue

            rules = entry.get("rules")
            if not isinstance(rules, list) or not rules:
                record_incomplete_fields(incomplete, skill_name, ["rules"])
                continue

            for rule in rules:
                if not isinstance(rule, dict):
                    record_incomplete_fields(incomplete, skill_name, ["rules"])
                    continue

                missing_fields = []
                if not rule_id_from_entry(rule):
                    missing_fields.append("rule_id")
                missing_fields.extend(
                    field
                    for field in SKILL_PLAN_RULE_FIELDS
                    if not evidence_field_present(rule.get(field))
                )
                if missing_fields:
                    record_incomplete_fields(incomplete, skill_name, missing_fields)
                    continue

                planned_rules.setdefault(skill_name, []).append(rule_id_from_entry(rule))

    missing_skills = sorted(set(required_skills) - set(planned_rules) - set(incomplete))
    return {
        "matched_paths": sorted(set(matched_paths)),
        "planned_rules": {skill: sorted(set(rules)) for skill, rules in planned_rules.items()},
        "missing_skills": missing_skills,
        "incomplete_skills": incomplete,
        "inspected_paths": sorted(set(inspected_paths)),
    }


def skill_understanding_evidence_status(task_dir: Path, paths: list[str], planned_rules: dict[str, list[str]]) -> dict:
    matched_paths: list[str] = []
    inspected_paths: list[str] = []
    complete_skills: set[str] = set()
    complete_rules: dict[str, list[str]] = {}
    incomplete: dict[str, list[str]] = {}
    for path in resolve_skill_use_paths(task_dir, paths):
        inspected = inspect_evidence_file(task_dir, path, inspected_paths)
        if inspected is None:
            continue

        rel_name, text = inspected
        entries = (
            skill_use_entries_from_json(text)
            if path.suffix.lower() == ".json"
            else skill_use_entries_from_markdown(text)
        )
        if entries:
            matched_paths.append(rel_name)

        for entry in entries:
            skill_name = skill_name_from_path(str(entry.get("skill_path") or ""))
            expected_rules = set(planned_rules.get(skill_name, []))
            if not expected_rules:
                continue

            rule_evidence = entry.get("rule_evidence")
            if not isinstance(rule_evidence, list) or not rule_evidence:
                record_incomplete_fields(incomplete, skill_name, ["rule_evidence"])
                continue

            for rule in rule_evidence:
                if not isinstance(rule, dict):
                    record_incomplete_fields(incomplete, skill_name, ["rule_evidence"])
                    continue

                rule_id = rule_id_from_entry(rule)
                if not rule_id:
                    record_incomplete_fields(incomplete, skill_name, ["rule_id"])
                    continue
                if rule_id not in expected_rules:
                    continue

                missing_fields = [
                    field
                    for field in SKILL_UNDERSTANDING_RULE_FIELDS
                    if not evidence_field_present(rule.get(field))
                ]
                if str(rule.get("reviewer_status") or "").strip().lower() != "approved":
                    missing_fields.append("reviewer_status=approved")
                if missing_fields:
                    record_incomplete_fields(incomplete, skill_name, missing_fields)
                    continue

                complete_rules.setdefault(skill_name, []).append(rule_id)

    for skill_name, expected_rules in planned_rules.items():
        if set(complete_rules.get(skill_name, [])) >= set(expected_rules):
            complete_skills.add(skill_name)

    missing_skills = sorted(set(planned_rules) - complete_skills - set(incomplete))
    return {
        "matched_paths": sorted(set(matched_paths)),
        "complete_skills": sorted(complete_skills),
        "complete_rules": {skill: sorted(set(rules)) for skill, rules in complete_rules.items()},
        "missing_skills": missing_skills,
        "incomplete_skills": incomplete,
        "inspected_paths": sorted(set(inspected_paths)),
    }


def enforce_specialist_dispatch_gate(args: argparse.Namespace, task_dir: Path, register: dict) -> dict:
    task = register.get("task", "")
    host_bridge_status = str(register.get("host_bridge_status") or "")
    current_session_fallback = host_bridge_status == "current_session_required"
    required = args.status == "completed" and looks_mutating_task(task) and current_session_fallback
    if not required:
        return {"required": False, "passed": True, "bypassed": False}

    status = specialist_dispatch_status(task_dir, list(args.evidence) + list(args.specialist_evidence))
    if status["passed"]:
        return status

    if args.specialist_bypass_reason:
        status["bypassed"] = True
        status["bypass_reason"] = args.specialist_bypass_reason
        return status

    status["advisory"] = True
    status["reason"] = (
        "specialist dispatch coverage is incomplete; repair records this gap "
        "without requiring a separate proof artifact"
    )
    return status


def enforce_skill_load_gate(args: argparse.Namespace, task_dir: Path, register: dict) -> dict:
    task = register.get("task", "")
    host_bridge_status = str(register.get("host_bridge_status") or "")
    current_session_fallback = host_bridge_status == "current_session_required"
    required = args.status == "completed" and looks_mutating_task(task) and current_session_fallback
    if not required:
        return {"required": False, "passed": True, "bypassed": False}

    status = skill_load_status(
        task_dir,
        register,
        list(args.skill_load_evidence),
        list(args.specialist_evidence),
    )
    if status["passed"]:
        return status

    if args.skill_load_bypass_reason:
        status["bypassed"] = True
        status["bypass_reason"] = args.skill_load_bypass_reason
        return status

    if status["matched_paths"] and status.get("unapproved_external_skill_paths"):
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: unapproved_external_skill_load\n"
            "DETAIL: current-session fallback may not auto-load non-agent-crew "
            "host/plugin skills without explicit user approval. "
            "UNAPPROVED: "
            + ", ".join(status["unapproved_external_skill_paths"])
            + ".\n"
            "NEXT: use only agent-crew system/user skills, or record explicit approval "
            "in context/external-skill-approval.md or context/external-skill-approval.json."
        )

    status["advisory"] = True
    status["reason"] = (
        "skill-load coverage is incomplete; repair records this gap without "
        "requiring a separate proof artifact"
    )
    return status


def enforce_skill_use_gate(
    args: argparse.Namespace,
    task_dir: Path,
    register: dict,
    skill_load_gate: dict,
) -> dict:
    task = register.get("task", "")
    host_bridge_status = str(register.get("host_bridge_status") or "")
    current_session_fallback = host_bridge_status == "current_session_required"
    loaded_skill_names = skill_load_gate.get("loaded_skill_names", [])
    required_skills = sorted({name for name in loaded_skill_names if name and name != "tdd.md"})
    required = bool(
        args.status == "completed"
        and looks_mutating_task(task)
        and current_session_fallback
        and required_skills
    )
    if not required:
        return {
            "required": False,
            "passed": True,
            "advisory": False,
            "bypassed": False,
            "required_skills": required_skills,
        }

    status = skill_use_status(task_dir, list(args.skill_use_evidence), required_skills)
    if status["passed"]:
        return status

    if args.skill_use_bypass_reason:
        status["bypassed"] = True
        status["advisory"] = False
        status["bypass_reason"] = args.skill_use_bypass_reason
        return status

    status["advisory"] = True
    status["reason"] = (
        "skill-use proof artifacts are optional; real task outcomes, tests, diffs, "
        "reviews, and tool events own completion evidence"
    )
    return status


def enforce_skill_understanding_gate(
    args: argparse.Namespace,
    task_dir: Path,
    register: dict,
    skill_use_gate: dict,
) -> dict:
    task = register.get("task", "")
    host_bridge_status = str(register.get("host_bridge_status") or "")
    current_session_fallback = host_bridge_status == "current_session_required"
    required_skills = sorted(skill_use_gate.get("complete_skills", []))
    required = bool(
        args.status == "completed"
        and looks_mutating_task(task)
        and current_session_fallback
        and skill_use_gate.get("passed")
        and required_skills
    )
    if not required:
        return {
            "required": False,
            "passed": True,
            "advisory": False,
            "bypassed": False,
            "required_skills": required_skills,
        }

    plan = skill_plan_status(task_dir, list(args.skill_understanding_evidence), required_skills)
    understanding = skill_understanding_evidence_status(
        task_dir,
        list(args.skill_use_evidence),
        plan["planned_rules"],
    )
    status = {
        "required": True,
        "passed": (
            bool(required_skills)
            and not plan["missing_skills"]
            and not plan["incomplete_skills"]
            and not understanding["missing_skills"]
            and not understanding["incomplete_skills"]
            and set(understanding["complete_skills"]) >= set(required_skills)
        ),
        "advisory": False,
        "reason": "",
        "required_skills": required_skills,
        "matched_paths": sorted(set(plan["matched_paths"] + understanding["matched_paths"])),
        "complete_skills": understanding["complete_skills"],
        "planned_rules": plan["planned_rules"],
        "complete_rules": understanding["complete_rules"],
        "missing_skills": sorted(set(plan["missing_skills"] + understanding["missing_skills"])),
        "incomplete_skills": merge_incomplete_skills(
            plan["incomplete_skills"],
            understanding["incomplete_skills"],
        ),
        "inspected_paths": sorted(set(plan["inspected_paths"] + understanding["inspected_paths"])),
        "bypassed": False,
        "bypass_reason": "",
    }
    if status["passed"]:
        return status

    if args.skill_understanding_bypass_reason:
        status["bypassed"] = True
        status["advisory"] = False
        status["bypass_reason"] = args.skill_understanding_bypass_reason
        return status

    status["advisory"] = True
    status["reason"] = (
        "skill-understanding proof artifacts are optional; applied behavior is "
        "judged from task outcomes, tests, diffs, reviews, and tool events"
    )
    return status


def enforce_quality_gate(args: argparse.Namespace, task_dir: Path, register: dict) -> dict:
    task = register.get("task", "")
    required = args.status == "completed" and looks_quality_gated_task(task)
    if not required:
        return {"required": False, "passed": True, "bypassed": False}

    evidence_paths = list(args.evidence) + list(args.quality_evidence)
    status = quality_evidence_status(task_dir, evidence_paths)
    pipeline_status = check_quality_loop(task_dir, target_status=args.status)
    pipeline_soft_failures = set(pipeline_status.get("soft_failures", []))
    pipeline_hard_failures = set(pipeline_status.get("hard_failures", []))
    pipeline_failures = set(pipeline_status.get("failures", []))
    trace = pipeline_status.get("trace_evidence") or {}
    trace_red = trace.get("red", {})
    trace_green = trace.get("green", {})
    trace_refactor = trace.get("refactor", {})
    pipeline_tdd_passed = bool(pipeline_status.get("passed") and pipeline_status.get("tdd_event_count"))
    pipeline_review_passed = bool(pipeline_status.get("passed") and pipeline_status.get("reviewer_approval_count"))

    # A git-verified contradiction (a claimed test path the diff does not
    # contain) always blocks, regardless of any document evidence.
    contradiction = "test_file_claim_contradicts_git" in pipeline_failures
    reviewer_independence_hard = "reviewer_approval_without_independent_span" in pipeline_hard_failures

    # Red phase — trace-first (a recorded failing test run), doc fallback only
    # when the trace source (tool-events.jsonl) is unavailable.
    red_from_trace = trace_red.get("evidence_source") == "trace"
    red_phase_explicit = bool(status["red_phase_evidence_paths"] or status["tdd_exception_paths"])
    red_phase_advisory = bool(
        not red_from_trace
        and not red_phase_explicit
        and pipeline_status.get("passed")
        and "missing_tdd_red_phase_evidence" in pipeline_soft_failures
        and "missing_tdd_red_phase_evidence" not in pipeline_hard_failures
    )
    if red_from_trace:
        red_phase_passed = bool(trace_red.get("passed"))
    else:
        red_phase_passed = red_phase_explicit or red_phase_advisory

    # Green phase — trace-first (a recorded passing test run), else the legacy
    # pipeline/document tdd signal.
    green_from_trace = trace_green.get("evidence_source") == "trace"
    if green_from_trace:
        green_phase_passed = bool(trace_green.get("passed"))
    else:
        green_phase_passed = bool((status["tdd_evidence_paths"] or pipeline_tdd_passed) and pipeline_status["passed"])

    # Refactor phase — trace-first (a green run at/after the last commit), doc
    # fallback only when the trace source is unavailable.
    refactor_from_trace = trace_refactor.get("evidence_source") == "trace"
    refactor_phase_explicit = bool(status["refactor_phase_evidence_paths"])
    refactor_phase_advisory = bool(
        not refactor_from_trace
        and not refactor_phase_explicit
        and pipeline_status.get("passed")
        and "missing_tdd_refactor_phase_evidence" in pipeline_soft_failures
        and "missing_tdd_refactor_phase_evidence" not in pipeline_hard_failures
    )
    if refactor_from_trace:
        refactor_phase_passed = bool(trace_refactor.get("passed"))
    else:
        refactor_phase_passed = refactor_phase_explicit or refactor_phase_advisory

    tdd_and_review_passed = bool(status["passed"] or (pipeline_tdd_passed and pipeline_review_passed))
    status["pipeline_gate"] = pipeline_status
    status["pipeline_passed"] = pipeline_status["passed"]
    status["trace_evidence"] = trace
    status["tdd_outcome_source"] = "evidence" if status["tdd_evidence_paths"] else ("pipeline" if pipeline_tdd_passed else "")
    status["review_outcome_source"] = (
        "evidence"
        if status["review_evidence_paths"]
        else ("pipeline" if pipeline_review_passed else "")
    )
    status["red_phase_advisory"] = red_phase_advisory
    status["refactor_phase_advisory"] = refactor_phase_advisory
    status["red_phase_source"] = trace_red.get("evidence_source") if red_from_trace else (
        "document" if red_phase_explicit else ("advisory" if red_phase_advisory else "")
    )
    status["refactor_phase_source"] = trace_refactor.get("evidence_source") if refactor_from_trace else (
        "document" if refactor_phase_explicit else ("advisory" if refactor_phase_advisory else "")
    )
    status["red_phase_passed"] = red_phase_passed
    status["green_phase_passed"] = green_phase_passed
    status["refactor_phase_passed"] = refactor_phase_passed
    status["contradiction"] = contradiction
    status["passed"] = bool(
        tdd_and_review_passed
        and pipeline_status["passed"]
        and red_phase_passed
        and green_phase_passed
        and refactor_phase_passed
        and not contradiction
    )
    status["bypassed"] = False
    status["bypass_reason"] = ""
    if status["passed"]:
        return status

    if args.quality_bypass_reason:
        status["bypassed"] = True
        status["bypass_reason"] = args.quality_bypass_reason
        return status

    # Only raise a phase-specific blocker when there is enough TDD/review
    # substance that the specific phase is the actual gap. With no substance at
    # all, fall through to the generic missing_quality_loop_evidence blocker.
    has_evidence_substance = bool(
        tdd_and_review_passed
        or status.get("tdd_evidence_paths")
        or status.get("review_evidence_paths")
        or status.get("red_phase_evidence_paths")
        or status.get("refactor_phase_evidence_paths")
        or pipeline_status.get("tdd_event_count")
        or pipeline_status.get("reviewer_approval_count")
    )

    if contradiction:
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: test_file_claim_contradicts_git\n"
            "DETAIL: git shows no test-file change between the recorded base commit "
            "and HEAD, but progress events or result.md claim a test path. The claimed "
            "test coverage is absent from the actual diff.\n"
            "NEXT: commit the real test file so it appears in the git diff, then re-run "
            "the focused test so the tool-event trace records the run. Do not claim a "
            "test path the diff does not contain."
        )

    if reviewer_independence_hard:
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: reviewer_approval_without_independent_span\n"
            "DETAIL: the reviewer-approved event is not corroborated by an independent "
            "review trace (no reviewer delegation span, no reviewer-attributed cost row, "
            "and no host-bridge tool-event window bracketing the approval).\n"
            "NEXT: invoke an independent reviewer so a reviewer delegation span, a "
            "reviewer-attributed cost row, or a bracketing host-bridge tool event is "
            "recorded before repair."
        )

    if has_evidence_substance and not red_phase_passed:
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: missing_tdd_red_phase_evidence\n"
            "DETAIL: completed repair for a mutating implementation task requires a "
            "failing (red) test run before production-code mutation, or an explicit TDD "
            "exception explaining why a runnable red failure could not be produced.\n"
            "NEXT: re-run the focused failing test so the tool-event trace records the "
            "red run before it is made to pass, or record context/tdd-exception.md with "
            "the reason a runnable red failure could not be produced."
        )

    if has_evidence_substance and red_phase_passed and not refactor_phase_passed:
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: missing_tdd_refactor_phase_evidence\n"
            "DETAIL: completed repair for a mutating implementation task requires a "
            "passing test run after the last implementation commit (the post-refactor "
            "green verification).\n"
            "NEXT: re-run the focused test after the refactor so the tool-event trace "
            "records a passing run at or after the last implementation commit."
        )

    if has_evidence_substance:
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: missing_quality_loop_pipeline\n"
            "DETAIL: completed repair for a mutating implementation task requires "
            "pipeline-level quality-loop evidence (implementer/TDD completion plus an "
            "independently corroborated reviewer approval), not only evidence files.\n"
            "FAILURES: " + ", ".join(pipeline_status.get("failures", [])) + "\n"
            "NEXT: re-run the focused test so the trace records implementer/TDD "
            "completion, and invoke an independent reviewer so the approval is "
            "corroborated. If review was rejected, the trace must show implementer/TDD "
            "retry followed by reviewer re-approval."
        )

    raise SystemExit(
        "STATUS: blocked\n"
        "BLOCKER: missing_quality_loop_evidence\n"
        "DETAIL: completed repair for a mutating implementation task requires trace "
        "evidence of TDD red/green/refactor and an independently corroborated reviewer "
        "approval.\n"
        "NEXT: re-run the focused test so the tool-event trace records the run and "
        "invoke an independent reviewer, or record an explicit --quality-bypass-reason."
    )


def render_result(task: str, task_id: str, status: str, note: str, blocker: str,
                  evidence_paths: list[str], memory_ids: list[str],
                  memory_context_reused: bool, quality_gate: dict | None = None,
                  specialist_gate: dict | None = None,
                  required_capability_gate: dict | None = None,
                  commit_specialist_gate: dict | None = None,
                  skill_load_gate: dict | None = None,
                  skill_use_gate: dict | None = None,
                  skill_understanding_gate: dict | None = None) -> str:
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
        if quality_gate.get("tdd_outcome_source"):
            lines.append(f"TDD_OUTCOME: {quality_gate.get('tdd_outcome_source')}")
        if quality_gate.get("green_phase_passed"):
            lines.append("TDD_GREEN_PHASE: passed")
        if quality_gate.get("red_phase_advisory"):
            lines.append("TDD_RED_PHASE: advisory")
        elif quality_gate.get("red_phase_passed"):
            if quality_gate.get("tdd_exception_paths"):
                lines.append("TDD_RED_PHASE: exception")
            else:
                lines.append("TDD_RED_PHASE: passed")
        for path in quality_gate.get("red_phase_evidence_paths", []):
            lines.append(f"TDD_RED_EVIDENCE: {path}")
        for path in quality_gate.get("tdd_exception_paths", []):
            lines.append(f"TDD_EXCEPTION: {path}")
        if quality_gate.get("refactor_phase_advisory"):
            lines.append("TDD_REFACTOR_PHASE: advisory")
        elif quality_gate.get("refactor_phase_passed"):
            lines.append("TDD_REFACTOR_PHASE: passed")
        for path in quality_gate.get("refactor_phase_evidence_paths", []):
            lines.append(f"TDD_REFACTOR_EVIDENCE: {path}")
        for path in quality_gate.get("review_evidence_paths", []):
            lines.append(f"REVIEW_EVIDENCE: {path}")
        if quality_gate.get("review_outcome_source"):
            lines.append(f"REVIEW_OUTCOME: {quality_gate.get('review_outcome_source')}")
    if specialist_gate and specialist_gate.get("required"):
        if specialist_gate.get("passed"):
            lines.append("SPECIALIST_DISPATCH: passed")
        elif specialist_gate.get("bypassed"):
            lines.append("SPECIALIST_DISPATCH: bypassed")
            lines.append(f"SPECIALIST_BYPASS_REASON: {specialist_gate.get('bypass_reason')}")
        elif specialist_gate.get("advisory"):
            lines.append("SPECIALIST_DISPATCH: advisory")
            if specialist_gate.get("reason"):
                lines.append(f"SPECIALIST_ADVISORY_REASON: {specialist_gate.get('reason')}")
        for path in specialist_gate.get("matched_paths", []):
            lines.append(f"SPECIALIST_EVIDENCE: {path}")
        missing_fields = specialist_gate.get("missing_fields", [])
        if missing_fields:
            lines.append("MISSING_SPECIALIST_DISPATCH: " + ", ".join(missing_fields))
        incomplete_paths = specialist_gate.get("incomplete_paths", {})
        for path, fields in sorted(incomplete_paths.items()):
            lines.append(f"INCOMPLETE_SPECIALIST_DISPATCH: {path}: {', '.join(fields)}")
        for agent in specialist_gate.get("selected_agents", []):
            lines.append(f"SPECIALIST_AGENT: {agent}")
        for agent in specialist_gate.get("selected_user_agents", []):
            lines.append(f"SPECIALIST_USER_AGENT: {agent}")
        for agent in specialist_gate.get("selected_subagents", []):
            lines.append(f"SPECIALIST_SUBAGENT: {agent}")
        for skill in specialist_gate.get("selected_skills", []):
            lines.append(f"SPECIALIST_SKILL: {skill}")
    if required_capability_gate and required_capability_gate.get("required"):
        if required_capability_gate.get("passed"):
            lines.append("REQUIRED_CAPABILITIES: passed")
        elif required_capability_gate.get("bypassed"):
            lines.append("REQUIRED_CAPABILITIES: bypassed")
            lines.append(f"REQUIRED_CAPABILITY_BYPASS_REASON: {required_capability_gate.get('bypass_reason')}")
        elif required_capability_gate.get("advisory"):
            lines.append("REQUIRED_CAPABILITIES: advisory")
            if required_capability_gate.get("reason"):
                lines.append(f"REQUIRED_CAPABILITY_ADVISORY_REASON: {required_capability_gate.get('reason')}")
        for capability in required_capability_gate.get("required_capabilities", []):
            lines.append(f"REQUIRED_CAPABILITY: {capability}")
        missing_capabilities = required_capability_gate.get("missing_capabilities", [])
        if missing_capabilities:
            lines.append("MISSING_REQUIRED_CAPABILITY: " + ", ".join(missing_capabilities))
        missing_completion = required_capability_gate.get("missing_completion_capabilities", [])
        if missing_completion:
            lines.append("MISSING_REQUIRED_CAPABILITY_COMPLETION: " + ", ".join(missing_completion))
        for capability, handlers in required_capability_gate.get("selected_handlers", {}).items():
            for handler in handlers:
                lines.append(f"SELECTED_HANDLER: {capability}={handler}")
        for capability, handlers in required_capability_gate.get("completed_handlers", {}).items():
            for handler in handlers:
                lines.append(f"COMPLETED_HANDLER: {capability}={handler}")
        for path in required_capability_gate.get("completion_evidence_paths", []):
            lines.append(f"CAPABILITY_COMPLETION_EVIDENCE: {path}")
    if commit_specialist_gate and commit_specialist_gate.get("required"):
        if commit_specialist_gate.get("passed"):
            lines.append("COMMIT_SPECIALIST: passed")
        elif commit_specialist_gate.get("bypassed"):
            lines.append("COMMIT_SPECIALIST: bypassed")
            lines.append(f"COMMIT_SPECIALIST_BYPASS_REASON: {commit_specialist_gate.get('bypass_reason')}")
        elif commit_specialist_gate.get("advisory"):
            lines.append("COMMIT_SPECIALIST: advisory")
            if commit_specialist_gate.get("reason"):
                lines.append(f"COMMIT_SPECIALIST_ADVISORY_REASON: {commit_specialist_gate.get('reason')}")
        missing_capabilities = commit_specialist_gate.get("missing_capabilities", [])
        if missing_capabilities:
            lines.append("MISSING_COMMIT_SPECIALIST_CAPABILITY: " + ", ".join(missing_capabilities))
        missing_completion = commit_specialist_gate.get("missing_completion_capabilities", [])
        if missing_completion:
            lines.append("MISSING_COMMIT_SPECIALIST_COMPLETION: " + ", ".join(missing_completion))
        for agent in commit_specialist_gate.get("selected_user_agents", []):
            lines.append(f"COMMIT_SPECIALIST_USER_AGENT: {agent}")
        for path in commit_specialist_gate.get("available_paths", []):
            lines.append(f"COMMIT_SPECIALIST_AVAILABLE: {path}")
        for capability, handlers in commit_specialist_gate.get("completed_handlers", {}).items():
            for handler in handlers:
                lines.append(f"COMMIT_SPECIALIST_COMPLETED_HANDLER: {capability}={handler}")
    if skill_load_gate and skill_load_gate.get("required"):
        if skill_load_gate.get("passed"):
            lines.append("SKILL_LOAD: passed")
        elif skill_load_gate.get("bypassed"):
            lines.append("SKILL_LOAD: bypassed")
            lines.append(f"SKILL_LOAD_BYPASS_REASON: {skill_load_gate.get('bypass_reason')}")
        elif skill_load_gate.get("advisory"):
            lines.append("SKILL_LOAD: advisory")
            if skill_load_gate.get("reason"):
                lines.append(f"SKILL_LOAD_ADVISORY_REASON: {skill_load_gate.get('reason')}")
        for path in skill_load_gate.get("matched_paths", []):
            lines.append(f"SKILL_LOAD_EVIDENCE: {path}")
        for skill in skill_load_gate.get("required_skills", []):
            lines.append(f"REQUIRED_SKILL: {skill}")
        missing = skill_load_gate.get("missing_required_skills", [])
        if missing:
            lines.append("MISSING_REQUIRED_SKILLS: " + ", ".join(missing))
    if skill_use_gate and skill_use_gate.get("required"):
        if skill_use_gate.get("passed"):
            lines.append("SKILL_USE: passed")
        elif skill_use_gate.get("bypassed"):
            lines.append("SKILL_USE: bypassed")
            lines.append(f"SKILL_USE_BYPASS_REASON: {skill_use_gate.get('bypass_reason')}")
        elif skill_use_gate.get("advisory"):
            lines.append("SKILL_USE: advisory")
            if skill_use_gate.get("reason"):
                lines.append(f"SKILL_USE_ADVISORY_REASON: {skill_use_gate.get('reason')}")
        for path in skill_use_gate.get("matched_paths", []):
            lines.append(f"SKILL_USE_EVIDENCE: {path}")
        for skill in skill_use_gate.get("complete_skills", []):
            lines.append(f"USED_SKILL: {skill}")
        missing_skills = skill_use_gate.get("missing_skills", [])
        if missing_skills:
            lines.append("MISSING_SKILL_USE: " + ", ".join(missing_skills))
        incomplete_skills = skill_use_gate.get("incomplete_skills", {})
        for skill, fields in sorted(incomplete_skills.items()):
            lines.append(f"INCOMPLETE_SKILL_USE: {skill}: {', '.join(fields)}")
    if skill_understanding_gate and skill_understanding_gate.get("required"):
        if skill_understanding_gate.get("passed"):
            lines.append("SKILL_UNDERSTANDING: passed")
        elif skill_understanding_gate.get("bypassed"):
            lines.append("SKILL_UNDERSTANDING: bypassed")
            lines.append(
                f"SKILL_UNDERSTANDING_BYPASS_REASON: "
                f"{skill_understanding_gate.get('bypass_reason')}"
            )
        elif skill_understanding_gate.get("advisory"):
            lines.append("SKILL_UNDERSTANDING: advisory")
            if skill_understanding_gate.get("reason"):
                lines.append(
                    f"SKILL_UNDERSTANDING_ADVISORY_REASON: "
                    f"{skill_understanding_gate.get('reason')}"
                )
        for path in skill_understanding_gate.get("matched_paths", []):
            lines.append(f"SKILL_UNDERSTANDING_EVIDENCE: {path}")
        for skill in skill_understanding_gate.get("complete_skills", []):
            lines.append(f"UNDERSTOOD_SKILL: {skill}")
        missing_skills = skill_understanding_gate.get("missing_skills", [])
        if missing_skills:
            lines.append("MISSING_SKILL_UNDERSTANDING: " + ", ".join(missing_skills))
        incomplete_skills = skill_understanding_gate.get("incomplete_skills", {})
        for skill, fields in sorted(incomplete_skills.items()):
            lines.append(f"INCOMPLETE_SKILL_UNDERSTANDING: {skill}: {', '.join(fields)}")
    lines.append("UNCERTAINTY: Manual repair records the current-session outcome; original host bridge execution did not run automatically.")
    if note:
        lines.append(f"NOTE: {note}")
    if memory_ids:
        lines.append("MEMORY_IDS: " + ", ".join(memory_ids))
        lines.append(f"MEMORY_CONTEXT_REUSED: {'yes' if memory_context_reused else 'no'}")
    return "\n".join(lines).rstrip() + "\n"


def append_evolution_closeout_result(task_dir: Path, status: dict) -> None:
    lines = [
        "",
        "## Learning Report",
        "",
        f"EVOLUTION_ANALYZER: {status.get('analyzer', 'skipped')}",
    ]
    if status.get("analyzer") == "completed":
        lines.append("EVOLUTION_REPORT: context/evolution-report.md")

    lines.extend([
        "",
        "## Self-Evolution Proposals",
        "",
        f"EVOLUTION_PROPOSALS: {status.get('proposals', 'skipped')}",
        f"PENDING_PROPOSALS: {int(status.get('pending_proposals') or 0)}",
    ])

    summary_path = task_dir / "context" / "evolution-proposals-summary.txt"
    if summary_path.is_file():
        lines.append("EVOLUTION_PROPOSALS_SUMMARY: context/evolution-proposals-summary.txt")
        lines.append("")
        lines.append(summary_path.read_text(encoding="utf-8").strip())

    errors = status.get("errors") or []
    if errors:
        lines.append("")
        lines.append("EVOLUTION_CLOSEOUT_WARNINGS: " + ", ".join(errors))

    with (task_dir / "result.md").open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")


def repair(args: argparse.Namespace) -> dict:
    state_dir = Path(args.state_dir).expanduser().resolve()
    task_dir = resolve_task_dir(state_dir, args.task_id)
    register_path = task_dir / "register.json"
    pipeline_path = task_dir / "pipeline.json"
    now = utc_now_z()

    register = load_json(register_path)
    pipeline = load_json(pipeline_path)
    original_host_bridge_status = str(register.get("host_bridge_status") or "")
    quality_gate = enforce_quality_gate(args, task_dir, register)
    specialist_gate = enforce_specialist_dispatch_gate(args, task_dir, register)
    required_capability_gate = enforce_required_capability_gate(args, task_dir, register, specialist_gate)
    commit_specialist_gate = enforce_commit_specialist_gate(args, task_dir, register, specialist_gate)
    skill_load_gate = enforce_skill_load_gate(args, task_dir, register)
    skill_use_gate = enforce_skill_use_gate(args, task_dir, register, skill_load_gate)
    skill_understanding_gate = enforce_skill_understanding_gate(args, task_dir, register, skill_use_gate)
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
        "specialist_dispatch_gate": specialist_gate,
        "required_capability_gate": required_capability_gate,
        "commit_specialist_gate": commit_specialist_gate,
        "skill_load_gate": skill_load_gate,
        "skill_use_gate": skill_use_gate,
        "skill_understanding_gate": skill_understanding_gate,
        "previous": previous,
        "repaired_at": now,
    }

    backup_result(task_dir)
    write_json(register_path, register)
    write_json(pipeline_path, pipeline)
    write_json(task_dir / "context" / "manual-fallback-repair.json", repair_record)
    (task_dir / "supervisor-pending.txt").unlink(missing_ok=True)
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
            specialist_gate,
            required_capability_gate,
            commit_specialist_gate,
            skill_load_gate,
            skill_use_gate,
            skill_understanding_gate,
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
    evolution_closeout = run_evolution_closeout(
        args,
        state_dir,
        task_dir,
        original_host_bridge_status=original_host_bridge_status,
    )
    repair_record["evolution_closeout"] = evolution_closeout
    write_json(task_dir / "context" / "manual-fallback-repair.json", repair_record)
    append_evolution_closeout_result(task_dir, evolution_closeout)
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
    parser.add_argument("--specialist-evidence", action="append", default=[])
    parser.add_argument("--specialist-bypass-reason", default="")
    parser.add_argument("--skill-load-evidence", action="append", default=[])
    parser.add_argument("--skill-load-bypass-reason", default="")
    parser.add_argument("--skill-use-evidence", action="append", default=[])
    parser.add_argument("--skill-use-bypass-reason", default="")
    parser.add_argument("--skill-understanding-evidence", action="append", default=[])
    parser.add_argument("--skill-understanding-bypass-reason", default="")
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
