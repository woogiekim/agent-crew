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
SKILL_LOAD_RE = re.compile(
    r"\b("
    r"skill[-_ ]?load|loaded\s+(?:skill|before)|skill_loaded|"
    r"read\s+.+skills?/.+\.md|applied\s+rule"
    r")\b|스킬\s*(?:로드|사용|적용)",
    re.IGNORECASE,
)
TDD_SKILL_PATH_RE = re.compile(r"(?:^|[/`\\])tdd\.md\b", re.IGNORECASE)
TDD_SKILL_SELECTION_RE = re.compile(r"\bselected_skill\s*[:=]\s*.*\btdd\b|\btdd_parallel\b|\bTDD\b", re.IGNORECASE)
SKILL_USE_RE = re.compile(r"\b(skill[-_ ]?use|applied_rules|evidence_refs|output_files|verification)\b", re.IGNORECASE)
SKILL_USE_REQUIRED_FIELDS = ("applied_rules", "evidence_refs", "output_files", "verification")


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
    for path in resolve_specialist_paths(task_dir, paths):
        inspected = inspect_evidence_file(task_dir, path, inspected_paths)
        if inspected is None:
            continue

        rel_name, text = inspected
        if SPECIALIST_DISPATCH_RE.search(text):
            matched_paths.append(rel_name)
    return {
        "required": True,
        "passed": bool(matched_paths),
        "matched_paths": sorted(set(matched_paths)),
        "inspected_paths": sorted(set(inspected_paths)),
        "bypassed": False,
        "bypass_reason": "",
    }


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
    return Path(value.strip().strip("`")).name


def extract_loaded_skill_paths(text: str) -> list[str]:
    paths: list[str] = []
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


def required_skill_names(task_dir: Path, register: dict, specialist_paths: list[str]) -> list[str]:
    snippets = [str(register.get("task") or "")]
    for path in resolve_specialist_paths(task_dir, specialist_paths):
        inspected: list[str] = []
        evidence = inspect_evidence_file(task_dir, path, inspected)
        if evidence is None:
            continue

        _rel_name, text = evidence
        snippets.append(text)

    required: list[str] = []
    if any(TDD_SKILL_SELECTION_RE.search(text) for text in snippets):
        required.append("tdd.md")
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
        if SKILL_LOAD_RE.search(text):
            matched_paths.append(rel_name)
            loaded_skill_paths.extend(extract_loaded_skill_paths(text))

    required_skills = required_skill_names(task_dir, register, specialist_paths)
    missing_required_skills: list[str] = []
    for skill in required_skills:
        if skill == "tdd.md" and not TDD_SKILL_PATH_RE.search(loaded_text):
            missing_required_skills.append(skill)

    return {
        "required": True,
        "passed": bool(matched_paths) and not missing_required_skills,
        "matched_paths": sorted(set(matched_paths)),
        "loaded_skill_paths": sorted(set(loaded_skill_paths)),
        "loaded_skill_names": sorted({skill_name_from_path(path) for path in loaded_skill_paths}),
        "required_skills": required_skills,
        "missing_required_skills": sorted(set(missing_required_skills)),
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
        "matched_paths": sorted(set(matched_paths)),
        "required_skills": sorted(set(required_skills)),
        "complete_skills": sorted(complete_skills),
        "missing_skills": missing_skills,
        "incomplete_skills": incomplete,
        "inspected_paths": sorted(set(inspected_paths)),
        "bypassed": False,
        "bypass_reason": "",
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

    raise SystemExit(
        "STATUS: blocked\n"
        "BLOCKER: missing_specialist_dispatch_evidence\n"
        "DETAIL: completed repair for a mutating Codex current-session fallback requires "
        "evidence that the task re-applied specialist agent and agent-skill selection "
        "before manual execution.\n"
        "NEXT: add --specialist-evidence pointing to context/specialist-dispatch.md "
        "or record an explicit --specialist-bypass-reason."
    )


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

    if status["matched_paths"] and status["missing_required_skills"]:
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: missing_required_skill_load_evidence\n"
            "DETAIL: completed repair for a mutating Codex current-session fallback requires "
            "skill-load evidence for the selected mandatory skill(s): "
            + ", ".join(status["missing_required_skills"])
            + ".\n"
            "NEXT: record context/skill-load.md with the loaded skill path(s), "
            "or record an explicit --skill-load-bypass-reason."
        )

    raise SystemExit(
        "STATUS: blocked\n"
        "BLOCKER: missing_skill_load_evidence\n"
        "DETAIL: completed repair for a mutating Codex current-session fallback requires "
        "evidence that applicable agent skills were actually loaded before manual execution.\n"
        "NEXT: record context/skill-load.md or context/skill-load.json with loaded skill paths, "
        "or record an explicit --skill-load-bypass-reason."
    )


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
        return {"required": False, "passed": True, "bypassed": False, "required_skills": required_skills}

    status = skill_use_status(task_dir, list(args.skill_use_evidence), required_skills)
    if status["passed"]:
        return status

    if args.skill_use_bypass_reason:
        status["bypassed"] = True
        status["bypass_reason"] = args.skill_use_bypass_reason
        return status

    if status["incomplete_skills"]:
        details = [
            f"{skill}: {', '.join(fields)}"
            for skill, fields in sorted(status["incomplete_skills"].items())
        ]
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: incomplete_skill_use_evidence\n"
            "DETAIL: skill-use evidence must include concrete applied_rules, evidence_refs, "
            "output_files, and verification for each loaded non-TDD skill.\n"
            "INCOMPLETE: " + "; ".join(details) + "\n"
            "NEXT: complete context/skill-use.json or record an explicit --skill-use-bypass-reason."
        )

    raise SystemExit(
        "STATUS: blocked\n"
        "BLOCKER: missing_skill_use_evidence\n"
        "DETAIL: completed repair for a mutating Codex current-session fallback requires "
        "evidence showing how each loaded non-TDD skill was applied, not only loaded.\n"
        "MISSING_SKILLS: " + ", ".join(status["missing_skills"] or required_skills) + "\n"
        "NEXT: record context/skill-use.json or context/skill-use.md with skill_path, "
        "applied_rules, evidence_refs, output_files, and verification, or record an "
        "explicit --skill-use-bypass-reason."
    )


def enforce_quality_gate(args: argparse.Namespace, task_dir: Path, register: dict) -> dict:
    task = register.get("task", "")
    required = args.status == "completed" and looks_mutating_task(task)
    if not required:
        return {"required": False, "passed": True, "bypassed": False}

    evidence_paths = list(args.evidence) + list(args.quality_evidence)
    status = quality_evidence_status(task_dir, evidence_paths)
    pipeline_status = check_quality_loop(task_dir, target_status=args.status)
    red_phase_passed = bool(status["red_phase_evidence_paths"] or status["tdd_exception_paths"])
    green_phase_passed = bool(status["tdd_evidence_paths"] and pipeline_status["passed"])
    refactor_phase_passed = bool(status["refactor_phase_evidence_paths"])
    status["pipeline_gate"] = pipeline_status
    status["pipeline_passed"] = pipeline_status["passed"]
    status["red_phase_passed"] = red_phase_passed
    status["green_phase_passed"] = green_phase_passed
    status["refactor_phase_passed"] = refactor_phase_passed
    status["passed"] = bool(
        status["passed"]
        and pipeline_status["passed"]
        and red_phase_passed
        and green_phase_passed
        and refactor_phase_passed
    )
    status["bypassed"] = False
    status["bypass_reason"] = ""
    if status["passed"]:
        return status

    if args.quality_bypass_reason:
        status["bypassed"] = True
        status["bypass_reason"] = args.quality_bypass_reason
        return status

    if (
        status.get("tdd_evidence_paths")
        and status.get("review_evidence_paths")
        and status.get("pipeline_passed")
        and not red_phase_passed
    ):
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: missing_tdd_red_phase_evidence\n"
            "DETAIL: completed repair for a mutating implementation task requires "
            "TDD red-phase evidence before production-code mutation, or an explicit "
            "TDD exception explaining why a runnable red failure could not be produced.\n"
            "NEXT: record context/tdd-red.md with the focused failing test result, "
            "or context/tdd-exception.md with the exception reason before repair."
        )

    if (
        status.get("tdd_evidence_paths")
        and status.get("review_evidence_paths")
        and status.get("pipeline_passed")
        and red_phase_passed
        and not refactor_phase_passed
    ):
        raise SystemExit(
            "STATUS: blocked\n"
            "BLOCKER: missing_tdd_refactor_phase_evidence\n"
            "DETAIL: completed repair for a mutating implementation task requires "
            "TDD refactor-phase evidence after green, including the refactor or no-op "
            "refactor decision and post-refactor verification.\n"
            "NEXT: record context/tdd-refactor.md with the refactor decision and "
            "post-refactor verification before repair."
        )

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
                  memory_context_reused: bool, quality_gate: dict | None = None,
                  specialist_gate: dict | None = None,
                  skill_load_gate: dict | None = None,
                  skill_use_gate: dict | None = None) -> str:
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
        if quality_gate.get("green_phase_passed"):
            lines.append("TDD_GREEN_PHASE: passed")
        if quality_gate.get("red_phase_passed"):
            if quality_gate.get("tdd_exception_paths"):
                lines.append("TDD_RED_PHASE: exception")
            else:
                lines.append("TDD_RED_PHASE: passed")
        for path in quality_gate.get("red_phase_evidence_paths", []):
            lines.append(f"TDD_RED_EVIDENCE: {path}")
        for path in quality_gate.get("tdd_exception_paths", []):
            lines.append(f"TDD_EXCEPTION: {path}")
        if quality_gate.get("refactor_phase_passed"):
            lines.append("TDD_REFACTOR_PHASE: passed")
        for path in quality_gate.get("refactor_phase_evidence_paths", []):
            lines.append(f"TDD_REFACTOR_EVIDENCE: {path}")
        for path in quality_gate.get("review_evidence_paths", []):
            lines.append(f"REVIEW_EVIDENCE: {path}")
    if specialist_gate and specialist_gate.get("required"):
        if specialist_gate.get("passed"):
            lines.append("SPECIALIST_DISPATCH: passed")
        elif specialist_gate.get("bypassed"):
            lines.append("SPECIALIST_DISPATCH: bypassed")
            lines.append(f"SPECIALIST_BYPASS_REASON: {specialist_gate.get('bypass_reason')}")
        for path in specialist_gate.get("matched_paths", []):
            lines.append(f"SPECIALIST_EVIDENCE: {path}")
    if skill_load_gate and skill_load_gate.get("required"):
        if skill_load_gate.get("passed"):
            lines.append("SKILL_LOAD: passed")
        elif skill_load_gate.get("bypassed"):
            lines.append("SKILL_LOAD: bypassed")
            lines.append(f"SKILL_LOAD_BYPASS_REASON: {skill_load_gate.get('bypass_reason')}")
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
        for path in skill_use_gate.get("matched_paths", []):
            lines.append(f"SKILL_USE_EVIDENCE: {path}")
        for skill in skill_use_gate.get("complete_skills", []):
            lines.append(f"USED_SKILL: {skill}")
        missing_skills = skill_use_gate.get("missing_skills", [])
        if missing_skills:
            lines.append("MISSING_SKILL_USE: " + ", ".join(missing_skills))
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
    specialist_gate = enforce_specialist_dispatch_gate(args, task_dir, register)
    skill_load_gate = enforce_skill_load_gate(args, task_dir, register)
    skill_use_gate = enforce_skill_use_gate(args, task_dir, register, skill_load_gate)
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
        "skill_load_gate": skill_load_gate,
        "skill_use_gate": skill_use_gate,
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
            skill_load_gate,
            skill_use_gate,
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
    parser.add_argument("--specialist-evidence", action="append", default=[])
    parser.add_argument("--specialist-bypass-reason", default="")
    parser.add_argument("--skill-load-evidence", action="append", default=[])
    parser.add_argument("--skill-load-bypass-reason", default="")
    parser.add_argument("--skill-use-evidence", action="append", default=[])
    parser.add_argument("--skill-use-bypass-reason", default="")
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
