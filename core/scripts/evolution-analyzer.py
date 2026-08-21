#!/usr/bin/env python3
"""
evolution-analyzer.py - Provider-neutral post-task learning report generator.

Purpose:
  Read one completed task directory and emit a deterministic evolution report
  that records reusable-work signals without creating or registering assets.

Inputs:
  --task-dir DIR          Task directory to analyze.
  --state-dir DIR         Optional state dir. Defaults to env-derived resolver.
  --task-id ID            Alternative to --task-dir; resolves DIR/tasks/ID.
  --format json|markdown  Stdout format when no output file is requested.
  --json-output PATH      Optional JSON artifact path to write.
  --markdown-output PATH  Optional markdown artifact path to write.

Outputs:
  JSON and/or markdown. Writes only the canonical report artifacts under the
  task context directory when output paths are provided.

Exit codes:
  0 - report generated
  3 - invalid args / missing task directory
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def _load_telemetry_module():
    path = SCRIPT_DIR / "telemetry-aggregate.py"
    spec = importlib.util.spec_from_file_location("telemetry_aggregate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load telemetry module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("telemetry_aggregate", module)
    spec.loader.exec_module(module)
    return module


telemetry = _load_telemetry_module()


REVIEW_PRINCIPLE_DETECTORS: tuple[dict[str, Any], ...] = (
    {
        "principle_key": "kotlin_spring_kotest_default",
        "required_terms": ("kotlin", "spring", "junit"),
        "any_terms": ("kotest", "funspec", "mockk"),
        "summary": "Reviewer identified a reusable Kotlin/Spring testing convention.",
        "principle": (
            "Kotlin/Spring tests default to Kotest FunSpec + MockK; "
            "JUnit 5 is allowed only when an existing harness or framework "
            "constraint makes Kotest impractical and the reason is stated first."
        ),
        "target_assets": ["backend-kotlin-spring.md", "tdd.md"],
    },
)
CODE_PATH_RE = re.compile(
    r"`?((?:src/(?:main|test)/|tests/|core/scripts/)"
    r"[A-Za-z0-9_./$-]+\.(?:java|kt|kts|py|js|jsx|ts|tsx|json|md))`?"
)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
OUTPUT_OPEN_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
)


def open_context_directory(task_dir: Path) -> int:
    task_fd = os.open(task_dir, DIRECTORY_OPEN_FLAGS)
    try:
        return os.open("context", DIRECTORY_OPEN_FLAGS, dir_fd=task_fd)
    finally:
        os.close(task_fd)


def unlink_output(context_fd: int, filename: str) -> None:
    try:
        os.unlink(filename, dir_fd=context_fd)
    except FileNotFoundError:
        pass


def write_output_at(context_fd: int, filename: str, text: str) -> None:
    descriptor = os.open(
        filename,
        OUTPUT_OPEN_FLAGS,
        0o600,
        dir_fd=context_fd,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


def resolve_state_dir(override: str | None) -> Path:
    if override:
        return Path(override)
    return telemetry.resolve_state_dir(None)


def resolve_task_dir(args: argparse.Namespace, state_dir: Path) -> Path:
    if args.task_dir:
        return Path(args.task_dir)
    if args.task_id:
        return state_dir / "tasks" / args.task_id
    raise ValueError("either --task-dir or --task-id is required")


def stage_agents(stage: Any) -> list[str]:
    if isinstance(stage, str):
        return [stage]
    if isinstance(stage, list):
        return [item for item in stage if isinstance(item, str)]
    if isinstance(stage, dict):
        agents = stage.get("agents")
        if isinstance(agents, str):
            return [agents]
        if isinstance(agents, list):
            return [item for item in agents if isinstance(item, str)]
    return []


def stage_skills(stage: Any) -> list[str]:
    if not isinstance(stage, dict):
        return []
    skills = stage.get("skills") or stage.get("selected_skills")
    if isinstance(skills, str):
        return [skills]
    if isinstance(skills, list):
        return [item for item in skills if isinstance(item, str)]
    return []


def pipeline_reused_assets(task_dir: Path) -> list[dict[str, str]]:
    pipeline = read_json(task_dir / "pipeline.json")
    stages = pipeline.get("stages")
    if not isinstance(stages, list):
        return []

    assets: dict[tuple[str, str], dict[str, str]] = {}
    for stage in stages:
        for agent in stage_agents(stage):
            assets.setdefault(
                ("agent", agent),
                {
                    "asset_type": "agent",
                    "name": agent,
                    "evidence_ref": "pipeline.json",
                },
            )
        for skill in stage_skills(stage):
            assets.setdefault(
                ("skill", skill),
                {
                    "asset_type": "skill",
                    "name": skill,
                    "evidence_ref": "pipeline.json",
                },
            )
    return [assets[key] for key in sorted(assets)]


def changed_files_from_events(events: list[dict[str, Any]], register: dict[str, Any]) -> list[str]:
    files: set[str] = set()
    for key in ("changed_files", "modified_files", "files"):
        value = register.get(key)
        if isinstance(value, list):
            files.update(str(item) for item in value if str(item).strip())

    for event in events:
        value = event.get("files")
        if isinstance(value, list):
            files.update(str(item) for item in value if str(item).strip())

    return sorted(files)


def changed_files_from_review_artifacts(task_dir: Path) -> list[str]:
    files: set[str] = set()
    for relative in (
        "context/reviewer-report.md",
        "context/review-ledger.md",
        "context/review-ledger.json",
        "context/test-coverage.md",
        "context/test-case-mapping.md",
        "context/tdd_log.md",
    ):
        path = task_dir / relative
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files.update(match.group(1) for match in CODE_PATH_RE.finditer(text))

    return sorted(files)


def changed_files_signal(task_dir: Path, events: list[dict[str, Any]], register: dict[str, Any]) -> list[str]:
    files = set(changed_files_from_events(events, register))
    files.update(changed_files_from_review_artifacts(task_dir))
    return sorted(files)


def skill_content_audit_signal(task_dir: Path) -> dict[str, Any]:
    payload = read_json(task_dir / "context" / "skill-content-audit.json")
    if not payload:
        return {
            "available": False,
            "shallow_finding_count": 0,
            "effective_followup_count": 0,
        }

    shallow = payload.get("shallow_findings")
    followups = payload.get("effective_followups")
    return {
        "available": True,
        "shallow_finding_count": len(shallow) if isinstance(shallow, list) else 0,
        "effective_followup_count": len(followups) if isinstance(followups, list) else 0,
    }


def read_review_sources(task_dir: Path) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for relative in (
        "context/review.md",
        "context/reviewer-response.txt",
        "context/review-result.md",
        "context/reviewer-report.md",
        "context/review-ledger.json",
        "context/review-ledger.md",
        "context/code-review.md",
    ):
        path = task_dir / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if text.strip():
            sources.append((relative, text))
    return sources


def review_principle_signals(task_dir: Path) -> list[dict[str, Any]]:
    matches: dict[str, set[str]] = {
        detector["principle_key"]: set()
        for detector in REVIEW_PRINCIPLE_DETECTORS
    }
    for relative, text in read_review_sources(task_dir):
        normalized = re.sub(r"\s+", " ", text.lower())
        for detector in REVIEW_PRINCIPLE_DETECTORS:
            required_terms = detector.get("required_terms") or ()
            any_terms = detector.get("any_terms") or ()
            if (
                all(str(token).lower() in normalized for token in required_terms)
                and any(str(token).lower() in normalized for token in any_terms)
            ):
                matches[detector["principle_key"]].add(relative)

    signals: list[dict[str, Any]] = []
    for detector in REVIEW_PRINCIPLE_DETECTORS:
        evidence_refs = sorted(matches[detector["principle_key"]])
        if not evidence_refs:
            continue
        signals.append({
            "principle_key": detector["principle_key"],
            "principle": detector["principle"],
            "target_assets": detector["target_assets"],
            "evidence_refs": evidence_refs,
        })
    return signals


def read_mistake_corrections(task_dir: Path) -> list[dict[str, Any]]:
    path = task_dir / "context" / "mistake-events.jsonl"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    corrections: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("event_type") != "mistake_correction":
            continue
        pattern_key = str(payload.get("pattern_key") or "").strip()
        if not pattern_key:
            continue

        evidence_refs = payload.get("evidence_refs") or []
        target_assets = payload.get("target_assets") or []
        corrections.append({
            "surface": str(payload.get("surface") or "unknown"),
            "mistake_type": str(payload.get("mistake_type") or "unknown"),
            "pattern_key": pattern_key,
            "corrected_decision": str(payload.get("corrected_decision") or ""),
            "summary": str(payload.get("summary") or "Corrected mistake was recorded."),
            "evidence_refs": [str(item) for item in evidence_refs if str(item).strip()]
            if isinstance(evidence_refs, list) else [],
            "target_assets": [str(item) for item in target_assets if str(item).strip()]
            if isinstance(target_assets, list) else [],
        })
    return corrections


def review_feedback_signal(task_dir: Path, row: dict[str, Any]) -> dict[str, Any]:
    summary = row.get("review_fix_loop_summary") or {}
    ledger_atom_count = int(summary.get("ledger_items_total") or 0)
    review_cycle_count = int(summary.get("total_cycles") or 0)

    evidence_refs: list[str] = []
    for source in summary.get("sources") or []:
        source_text = str(source or "").strip()
        if source_text.startswith("context/review-ledger") and source_text not in evidence_refs:
            evidence_refs.append(source_text)

    reviewer_report = task_dir / "context" / "reviewer-report.md"
    if reviewer_report.is_file() and "context/reviewer-report.md" not in evidence_refs:
        evidence_refs.append("context/reviewer-report.md")

    return {
        "ledger_atom_count": ledger_atom_count,
        "review_cycle_count": review_cycle_count,
        "evidence_refs": evidence_refs,
    }


def observed_patterns(row: dict[str, Any], loop_backs: int,
                      skill_audit: dict[str, Any],
                      review_principles: list[dict[str, Any]],
                      mistake_corrections: list[dict[str, Any]],
                      review_feedback: dict[str, Any],
                      retry_evidence_refs: list[str],
                      loop_back_evidence_refs: list[str]) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    retries = int(row.get("retries") or 0)
    blockers = list(row.get("blockers") or [])

    if retries > 0:
        patterns.append({
            "kind": "retry",
            "summary": f"{retries} retry event(s) were recorded during the task.",
            "evidence_refs": retry_evidence_refs or ["progress.buffer.jsonl"],
        })
    if loop_backs > 0:
        patterns.append({
            "kind": "review_loop_back",
            "summary": f"{loop_backs} reviewer NEEDS_CHANGES loop-back(s) were recorded.",
            "evidence_refs": loop_back_evidence_refs or ["progress.buffer.jsonl"],
        })
    if blockers:
        patterns.append({
            "kind": "blocker",
            "summary": "Task recorded blocker signal(s): " + ", ".join(sorted(blockers)),
            "evidence_refs": ["register.json", "result.md"],
        })
    if int(skill_audit.get("shallow_finding_count") or 0) > 0:
        patterns.append({
            "kind": "skill_content_depth",
            "summary": "Skill content audit found shallow skill material.",
            "evidence_refs": ["context/skill-content-audit.json"],
        })
    if int(review_feedback.get("ledger_atom_count") or 0) > 0:
        patterns.append({
            "kind": "review_feedback",
            "summary": (
                f"{review_feedback['ledger_atom_count']} review ledger atom(s) "
                f"were recorded across {review_feedback['review_cycle_count']} "
                "review cycle(s)."
            ),
            "ledger_atom_count": review_feedback["ledger_atom_count"],
            "review_cycle_count": review_feedback["review_cycle_count"],
            "evidence_refs": review_feedback["evidence_refs"],
        })
    for principle in review_principles:
        patterns.append({
            "kind": "review_principle",
            "principle_key": principle["principle_key"],
            "summary": review_principle_summary(principle["principle_key"]),
            "principle": principle["principle"],
            "target_assets": principle["target_assets"],
            "evidence_refs": principle["evidence_refs"],
        })
    for correction in mistake_corrections:
        patterns.append({
            "kind": "mistake_correction",
            "surface": correction["surface"],
            "mistake_type": correction["mistake_type"],
            "pattern_key": correction["pattern_key"],
            "summary": correction["summary"],
            "corrected_decision": correction["corrected_decision"],
            "target_assets": correction["target_assets"],
            "evidence_refs": correction["evidence_refs"] or ["context/mistake-events.jsonl"],
        })

    return patterns


def review_principle_summary(principle_key: str) -> str:
    for detector in REVIEW_PRINCIPLE_DETECTORS:
        if detector["principle_key"] == principle_key:
            return str(detector["summary"])

    return "Reviewer identified a reusable implementation convention."


def rejected_candidates(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not patterns:
        return []

    candidates: list[dict[str, Any]] = []
    for pattern in patterns:
        if pattern.get("kind") != "review_principle":
            continue
        candidates.append({
            "asset_type": "skill",
            "name": f"review-principle:{pattern['principle_key']}",
            "reason": "A reviewer finding captured a reusable implementation principle that may belong in existing skills.",
            "rejection_reason": "insufficient_repeated_evidence",
            "required_evidence": "Collect repeated independent review findings before suggesting a patch to existing skills.",
            "principle_key": pattern["principle_key"],
            "principle": pattern["principle"],
            "target_assets": pattern["target_assets"],
        })
    for pattern in patterns:
        if pattern.get("kind") != "mistake_correction":
            continue
        candidates.append({
            "asset_type": "rule",
            "name": f"mistake-correction:{pattern['pattern_key']}",
            "reason": "A corrected mistake produced a reusable system-learning pattern.",
            "rejection_reason": "insufficient_repeated_evidence",
            "required_evidence": "Collect repeated corrected mistakes before proposing a system change.",
            "target_assets": pattern.get("target_assets", []),
        })

    if any(pattern.get("kind") not in {"review_principle", "mistake_correction"} for pattern in patterns):
        candidates.append({
            "asset_type": "skill",
            "name": "existing-skill-patch-suggestion",
            "reason": "A single task produced a reusable-work signal; prefer a small patch to an existing skill over creating a new asset.",
            "rejection_reason": "insufficient_repeated_evidence",
            "required_evidence": "Collect repeated occurrences before suggesting a minimal patch to the closest existing skill.",
        })

    return candidates


def learning_summary(meaningful: bool, patterns: list[dict[str, Any]]) -> str:
    if not meaningful:
        return (
            "No reusable asset candidate produced; the task completed without "
            "retry, blocker, reviewer loop-back, skill-content-depth, or "
            "review-principle signals."
        )

    kinds = ", ".join(pattern["kind"] for pattern in patterns)
    return (
        "Reusable-work signals were observed (" + kinds + "), but automatic "
        "asset generation remains disabled. Prefer lightweight follow-up: patch "
        "the closest existing skill only after the pattern repeats."
    )


def build_report(state_dir: Path, task_dir: Path) -> dict[str, Any]:
    row = telemetry.aggregate_task(state_dir, task_dir)
    events = telemetry.effective_progress_events(task_dir)
    register = telemetry.read_register(task_dir) or {}
    loop_backs = telemetry.count_reviewer_loop_backs(events)
    retry_events = [event for event in events if event.get("event") == "RETRY"]
    loop_back_events = [
        event for event in retry_events
        if telemetry.count_reviewer_loop_backs([event]) > 0
    ]
    retry_evidence_refs = telemetry.event_source_names(retry_events)
    loop_back_evidence_refs = telemetry.event_source_names(loop_back_events)
    skill_audit = skill_content_audit_signal(task_dir)
    review_principles = review_principle_signals(task_dir)
    mistake_corrections = read_mistake_corrections(task_dir)
    review_feedback = review_feedback_signal(task_dir, row)
    patterns = observed_patterns(
        row,
        loop_backs,
        skill_audit,
        review_principles,
        mistake_corrections,
        review_feedback,
        retry_evidence_refs,
        loop_back_evidence_refs,
    )
    meaningful = bool(patterns)

    return {
        "schema_version": 1,
        "task_id": row.get("task_id") or task_dir.name,
        "task": row.get("task") or register.get("task") or "",
        "generation_mode": "report_only",
        "meaningful": meaningful,
        "signals": {
            "retries": int(row.get("retries") or 0),
            "reviewer_loop_backs": loop_backs,
            "blockers": list(row.get("blockers") or []),
            "changed_files": changed_files_signal(task_dir, events, register),
            "skill_content_audit": skill_audit,
            "review_principles": review_principles,
            "mistake_corrections": mistake_corrections,
            "review_feedback": review_feedback,
        },
        "reused_assets": pipeline_reused_assets(task_dir),
        "observed_patterns": patterns,
        "asset_candidates": [],
        "rejected_candidates": rejected_candidates(patterns),
        "learning_summary": learning_summary(meaningful, patterns),
        "guardrails": {
            "asset_writes": "disabled",
            "generator_invoked": False,
            "verification_bypass": False,
        },
    }


def markdown_list(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def to_markdown(report: dict[str, Any]) -> str:
    signals = report["signals"]
    skill_audit = signals["skill_content_audit"]
    review_feedback = signals.get("review_feedback") or {}
    reused = [
        f"{asset['asset_type']}: {asset['name']} ({asset['evidence_ref']})"
        for asset in report["reused_assets"]
    ]
    patterns = [
        f"{pattern['kind']}: {pattern['summary']}"
        for pattern in report["observed_patterns"]
    ]
    rejected = [
        f"{item['asset_type']}: {item['name']} - {item['rejection_reason']}"
        for item in report["rejected_candidates"]
    ]
    review_principles = [
        (
            f"{item['principle_key']}: {item['principle']} "
            f"(targets: {', '.join(item['target_assets'])}; "
            f"evidence: {', '.join(item['evidence_refs'])})"
        )
        for item in signals.get("review_principles", [])
    ]
    mistake_corrections = [
        (
            f"{item['pattern_key']}: {item['summary']} "
            f"(surface: {item['surface']}; type: {item['mistake_type']}; "
            f"targets: {', '.join(item.get('target_assets', [])) or 'none'}; "
            f"evidence: {', '.join(item.get('evidence_refs', [])) or 'context/mistake-events.jsonl'})"
        )
        for item in signals.get("mistake_corrections", [])
    ]

    return "\n".join([
        "# Learning Report",
        "",
        f"Task: {report['task_id']}",
        f"Mode: {report['generation_mode']}",
        f"Meaningful signals: {str(report['meaningful']).lower()}",
        "",
        "## Summary",
        "",
        report["learning_summary"],
        "",
        "## Signals",
        "",
        f"- Retries: {signals['retries']}",
        f"- Reviewer loop-backs: {signals['reviewer_loop_backs']}",
        f"- Blockers: {', '.join(signals['blockers']) if signals['blockers'] else 'none'}",
        f"- Changed files: {', '.join(signals['changed_files']) if signals['changed_files'] else 'none'}",
        (
            "- Skill content audit: "
            f"available={str(skill_audit['available']).lower()}, "
            f"shallow={skill_audit['shallow_finding_count']}, "
            f"effective_followups={skill_audit.get('effective_followup_count', 0)}"
        ),
        f"- Review principles: {len(signals.get('review_principles', []))}",
        f"- Mistake corrections: {len(signals.get('mistake_corrections', []))}",
        (
            "- Review feedback: "
            f"ledger_atoms={review_feedback.get('ledger_atom_count', 0)}, "
            f"cycles={review_feedback.get('review_cycle_count', 0)}"
        ),
        "",
        "## Reused Assets",
        "",
        markdown_list(reused),
        "",
        "## Review Principles",
        "",
        markdown_list(review_principles),
        "",
        "## Mistake Corrections",
        "",
        markdown_list(mistake_corrections),
        "",
        "## Observed Patterns",
        "",
        markdown_list(patterns),
        "",
        "## Asset Candidates",
        "",
        "- None; automatic asset creation is disabled.",
        "",
        "## Rejected Candidates",
        "",
        markdown_list(rejected),
        "",
        "## Guardrails",
        "",
        "- Asset writes: disabled",
        "- Generator invoked: false",
        "- Verification bypass: false",
        "",
    ])


def write_report_outputs(
    report: dict[str, Any],
    args: argparse.Namespace,
    task_dir: Path,
) -> None:
    validate_output_paths(args, task_dir)
    outputs: list[tuple[str, str]] = []
    if args.json_output:
        outputs.append((
            "evolution-report.json",
            json.dumps(report, indent=2, sort_keys=True) + "\n",
        ))
    if args.markdown_output:
        outputs.append(("evolution-report.md", to_markdown(report)))
    if not outputs:
        return

    context_fd = open_context_directory(task_dir)
    try:
        for filename, _ in outputs:
            unlink_output(context_fd, filename)
        try:
            for filename, content in outputs:
                write_output_at(context_fd, filename, content)
        except OSError:
            for filename, _ in outputs:
                unlink_output(context_fd, filename)
            raise
    finally:
        os.close(context_fd)


def output_path_is_canonical(output_path: str, task_dir: Path, filename: str) -> bool:
    root = task_dir.resolve(strict=False)
    expected = root / "context" / filename
    try:
        actual = Path(output_path).resolve(strict=False)
    except (OSError, RuntimeError):
        return False

    return actual == expected


def validate_output_paths(args: argparse.Namespace, task_dir: Path) -> None:
    outputs = (
        (args.json_output, "evolution-report.json"),
        (args.markdown_output, "evolution-report.md"),
    )
    for output_path, filename in outputs:
        if output_path and not output_path_is_canonical(output_path, task_dir, filename):
            raise ValueError(
                "output path must be the canonical task report artifact "
                f"{task_dir.resolve(strict=False) / 'context' / filename}; "
                f"got {output_path}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="agent-crew evolution report analyzer")
    parser.add_argument("--state-dir")
    parser.add_argument("--task-dir")
    parser.add_argument("--task-id")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    try:
        state_dir = resolve_state_dir(args.state_dir)
        task_dir = resolve_task_dir(args, state_dir)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if not task_dir.is_dir():
        print(f"error: task directory not found: {task_dir}", file=sys.stderr)
        return 3

    try:
        validate_output_paths(args, task_dir)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    report = build_report(state_dir, task_dir)
    try:
        write_report_outputs(report, args, task_dir)
    except OSError as exc:
        print(f"error: secure report write failed: {exc}", file=sys.stderr)
        return 3

    if not args.json_output and not args.markdown_output:
        if args.format == "markdown":
            sys.stdout.write(to_markdown(report))
        else:
            json.dump(report, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
