#!/usr/bin/env python3
"""Classify reviewer output for supervisor quality-loop routing.

Inputs:
  --response FILE     Reviewer output file. When omitted, read stdin.
  --format text|json  Output format.

Outputs:
  json: {"action": "approve|retry|none", "reason": "...", "directive": "..."}
  text: ACTION/REASON/DIRECTIVE lines.

Exit codes:
  0 - reviewer approved or no loop action needed
  1 - reviewer requested implementer retry
  2 - invalid arguments or unreadable response file
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from completion_artifact_lib import validate as validate_completion_artifact
except ModuleNotFoundError:
    from core.scripts.completion_artifact_lib import (
        validate as validate_completion_artifact,
    )


STATUS_REJECTED_RE = re.compile(r"^STATUS\s*:\s*REJECTED\b", re.I | re.M)
REVIEW_NEEDS_CHANGES_RE = re.compile(r"^REVIEW\s*:\s*NEEDS_CHANGES\b", re.I | re.M)
REVIEW_APPROVED_RE = re.compile(r"^REVIEW\s*:\s*APPROVED\b", re.I | re.M)
REASON_RE = re.compile(r"^REASON\s*:\s*([a-zA-Z0-9_.:-]+)", re.I | re.M)
ISSUES_RE = re.compile(r"^ISSUES\s*:\s*(\d+)", re.I | re.M)
REPORT_RE = re.compile(r"^REPORT\s*:\s*(.+)$", re.I | re.M)
QUALITY_METRICS_RE = re.compile(r"^QUALITY_METRICS\s*:\s*(.+)$", re.I | re.M)
REVIEW_MODE_RE = re.compile(r"^REVIEW_MODE\s*:\s*([a-zA-Z0-9_.:-]+)", re.I | re.M)
NEW_MUST_CLASSIFICATION_RE = re.compile(r"^NEW_MUST_CLASSIFICATION\s*:\s*([a-zA-Z0-9_.:-]+)", re.I | re.M)
NEW_MUST_EVIDENCE_RE = re.compile(r"^NEW_MUST_EVIDENCE\s*:\s*(.+)$", re.I | re.M)
BLOCKING_FINDING_RE = re.compile(
    r"(?:\[(?:CRITICAL|IMPORTANT|MUST|P0|P1)\]|\b(?:CRITICAL|IMPORTANT|MUST|P0|P1)\s*:)",
    re.I,
)
FIRST_PARTY_EVIDENCE_RE = re.compile(
    r"(?<![\w/.-])((?:[A-Za-z0-9_./-]+\.(?:py|kt|java|js|ts|tsx|jsx|md|json|yml|yaml|toml|sh|gradle))(?:[:#]\d+)?|"
    r"(?:context|tests|src|core)/[A-Za-z0-9_./-]+)",
    re.I,
)
TOOL_OUTPUT_EVIDENCE_RE = re.compile(r"\btool[-_ ]?output\s*:", re.I)
FIELD_HEADER_RE = re.compile(r"^[A-Z][A-Z0-9_ -]{2,}:\s*")

VERIFY_PRIOR_MUST_ONLY = "verify-prior-must-only"
FULL_RESCAN = "full-rescan"
VALID_REVIEW_MODES = {VERIFY_PRIOR_MUST_ONLY, FULL_RESCAN}
ALLOWED_NEW_MUST_CLASSIFICATIONS = {
    "regression",
    "missed_existing",
    "severity_escalation",
    "unclear_requirement",
}
REVIEWER_RETRY_BUDGET_LIMIT = 2
IMPLEMENTER_RETRY_BUDGET_LIMIT = 3


RE_REVIEW_MODE_DIRECTIVE = (
    " On the next reviewer pass, set REVIEW_MODE: verify-prior-must-only "
    "unless the operator or supervisor explicitly requests REVIEW_MODE: full-rescan. "
    "Verify the prior Must findings first. If a new Must is raised during "
    "re-review, require NEW_MUST_CLASSIFICATION: regression | missed_existing | "
    "severity_escalation | unclear_requirement plus concrete first-party evidence; "
    "weakly evidenced new findings must remain non-blocking Should/MINOR items."
)


DIRECTIVES = {
    "tests_failed": (
        "Tests failed in the previous review. Fix the failing tests reported "
        "in ${TASK_DIR}/context/review-tests.md. Do not skip or comment out "
        "the failing assertions."
    ),
    "tests_absent_for_code_change": (
        "Reviewer detected a code change with no discoverable test runner. "
        "Add a test runner config and tests covering the changed behavior, "
        "or have the planner justify requires_test_execution=false for a "
        "non-code stage."
    ),
    "cross_process_path_mismatch": (
        "Reviewer detected a path-literal mismatch across the shell/Python "
        "boundary. Make both sides resolve to the same path."
    ),
    "review_needs_changes": (
        "Reviewer requested changes in ${TASK_DIR}/context/review.md. Return "
        "to the immediately preceding implementation/TDD stage, remediate every "
        "listed issue, run the relevant tests, and then re-run reviewer."
        + RE_REVIEW_MODE_DIRECTIVE
    ),
    "spec_incomplete": (
        "Reviewer found missing PRD acceptance criteria in ${TASK_DIR}/context/review.md. "
        "Return to the immediately preceding implementation/TDD stage and implement "
        "the missing PRD acceptance criteria before addressing code-quality polish."
        + RE_REVIEW_MODE_DIRECTIVE
    ),
    "code_quality": (
        "Reviewer found code-quality issues in ${TASK_DIR}/context/review.md. Return "
        "to the immediately preceding implementation/TDD stage, remediate the "
        "code-quality findings, run the relevant tests, and then re-run reviewer."
        + RE_REVIEW_MODE_DIRECTIVE
    ),
    "quality_metrics_missing": (
        "Reviewer approved without the required QUALITY_METRICS line. Re-run "
        "the reviewer stage and require it to write "
        "${TASK_DIR}/context/quality-metrics.json before approval."
    ),
    "quality_metrics_file_missing": (
        "Reviewer returned a QUALITY_METRICS path, but the referenced file was "
        "not found. Re-run the reviewer stage and require it to write the "
        "quality metrics artifact before approval."
    ),
    "review_contract_invalid": (
        "Reviewer raised a new Must during REVIEW_MODE: verify-prior-must-only "
        "without the required NEW_MUST_CLASSIFICATION and first-party evidence. "
        "Re-run the reviewer only; do not return to implementer or count this "
        "against the implementer retry budget. A valid new Must must include "
        "NEW_MUST_CLASSIFICATION: regression | missed_existing | "
        "severity_escalation | unclear_requirement and NEW_MUST_EVIDENCE with "
        "concrete repository/test/context references."
    ),
    "completion_artifact_missing": (
        "Reviewer completion did not reference an existing task-local REPORT. "
        "Re-run the reviewer only and require REPORT to point to the durable "
        "review artifact."
    ),
    "completion_artifact_ambiguous": (
        "Reviewer completion returned multiple REPORT fields. Re-run the "
        "reviewer only and require one unambiguous task-local REPORT path."
    ),
    "completion_artifact_outside_task": (
        "Reviewer completion referenced a REPORT outside TASK_DIR. Re-run the "
        "reviewer only and write the report under the current task."
    ),
    "completion_artifact_not_file": (
        "Reviewer REPORT does not reference a regular file. Re-run the "
        "reviewer only and write the durable review artifact first."
    ),
    "completion_artifact_unreadable": (
        "Reviewer REPORT is not readable UTF-8 text. Re-run the reviewer only "
        "and write a readable durable review artifact."
    ),
    "completion_artifact_empty": (
        "Reviewer REPORT contains no semantic content. Re-run the reviewer "
        "only and write the durable review findings before completion."
    ),
}


def with_budget(payload: dict, retry_target: str) -> dict:
    if retry_target == "reviewer":
        payload.update({
            "retry_budget": "reviewer",
            "retry_budget_limit": REVIEWER_RETRY_BUDGET_LIMIT,
            "implementation_retry_budget_consumed": False,
        })
    elif retry_target == "implementer":
        payload.update({
            "retry_budget": "validation",
            "retry_budget_limit": IMPLEMENTER_RETRY_BUDGET_LIMIT,
            "implementation_retry_budget_consumed": True,
        })
    return payload


def read_response(path: str | None) -> tuple[str, str | None]:
    if not path:
        return sys.stdin.read(), None
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace"), None
    except Exception as exc:
        return "", f"reviewer-loop-decision: cannot read response: {exc}"


def report_path(text: str) -> str:
    match = REPORT_RE.search(text)
    return match.group(1).strip() if match else "${TASK_DIR}/context/review.md"


def quality_metrics_path(text: str) -> str:
    match = QUALITY_METRICS_RE.search(text)
    return match.group(1).strip() if match else ""


def review_mode(text: str, explicit_mode: str | None = None) -> str:
    if explicit_mode:
        value = explicit_mode.strip().lower()
        return value if value in VALID_REVIEW_MODES else VERIFY_PRIOR_MUST_ONLY
    match = REVIEW_MODE_RE.search(text)
    if match:
        value = match.group(1).strip().lower()
        return value if value in VALID_REVIEW_MODES else VERIFY_PRIOR_MUST_ONLY
    return FULL_RESCAN


def resolve_quality_metrics_path(path_text: str, task_dir: str | None) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    if task_dir:
        if path_text.startswith("context/"):
            return Path(task_dir) / path_text
        return Path(task_dir) / path.name
    return None


def is_new_findings_section(line: str) -> bool:
    lowered = line.strip().lower().rstrip(":")
    return (
        "new findings in this review" in lowered
        or "new must" in lowered
        or "new blocking" in lowered
        or "new critical" in lowered
        or "new important" in lowered
    )


def is_prior_findings_section(line: str) -> bool:
    lowered = line.strip().lower().rstrip(":")
    return (
        "existing unresolved findings" in lowered
        or "prior must" in lowered
        or "previous must" in lowered
        or "prior findings" in lowered
        or "previous findings" in lowered
        or "unresolved prior" in lowered
        or "remediation verification" in lowered
    )


def is_section_boundary(line: str) -> bool:
    return line.startswith("#") or bool(FIELD_HEADER_RE.match(line))


def is_benign_must_summary(line: str) -> bool:
    normalized = line.lstrip("-* ").strip().lower()
    if "must / should / suggestion" in normalized:
        return True
    if not normalized.startswith("missing must:"):
        return False
    value = normalized.split(":", 1)[1].strip()
    return value in {"none", "no", "n/a", "na", "0", "[]", "-"}


def extract_new_must_lines(text: str) -> list[str]:
    lines: list[str] = []
    section = "generic"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if is_benign_must_summary(line):
            continue

        if line.upper().startswith("NEW_MUST:"):
            lines.append(line)
            continue

        if is_new_findings_section(line):
            section = "new"
            continue
        if is_prior_findings_section(line):
            section = "prior"
            continue

        if is_section_boundary(line):
            section = "generic"
            continue

        if section != "prior" and BLOCKING_FINDING_RE.search(line):
            lines.append(line)

    return lines


def new_must_classification(text: str) -> str:
    match = NEW_MUST_CLASSIFICATION_RE.search(text)
    return match.group(1).strip().lower() if match else ""


def strip_line_suffix(path_text: str) -> str:
    return re.sub(r"([:#])\d+$", "", path_text.strip().strip("`'\".,);]"))


def evidence_path_exists(path_text: str, task_dir: str | None) -> bool:
    clean = strip_line_suffix(path_text)
    if not clean:
        return False

    path = Path(clean)
    if path.is_absolute():
        return path.exists()

    candidate_roots: list[Path] = []
    if task_dir:
        task_root = Path(task_dir)
        if clean.startswith("context/"):
            candidate_roots.append(task_root)
        candidate_roots.append(task_root)
    candidate_roots.append(Path.cwd())

    return any((root / clean).exists() for root in candidate_roots)


def has_first_party_new_must_evidence(text: str, new_must_lines: list[str], task_dir: str | None = None) -> bool:
    evidence_match = NEW_MUST_EVIDENCE_RE.search(text)
    evidence_text = evidence_match.group(1) if evidence_match else ""
    candidate_text = "\n".join([evidence_text, *new_must_lines])
    if TOOL_OUTPUT_EVIDENCE_RE.search(candidate_text):
        return True

    return any(
        evidence_path_exists(match.group(1), task_dir)
        for match in FIRST_PARTY_EVIDENCE_RE.finditer(candidate_text)
    )


def review_contract_status(text: str, active_review_mode: str, task_dir: str | None = None) -> dict:
    classification = new_must_classification(text)
    new_must_lines = extract_new_must_lines(text)
    violations: list[str] = []
    if active_review_mode == VERIFY_PRIOR_MUST_ONLY and new_must_lines:
        if not classification:
            violations.append("new_must_classification_missing")
        elif classification not in ALLOWED_NEW_MUST_CLASSIFICATIONS:
            violations.append("new_must_classification_invalid")
        if not has_first_party_new_must_evidence(text, new_must_lines, task_dir):
            violations.append("new_must_first_party_evidence_missing")

    return {
        "valid": not violations,
        "mode": active_review_mode,
        "new_must_lines": new_must_lines,
        "new_must_classification": classification,
        "violations": violations,
    }


def classify(text: str, task_dir: str | None = None, explicit_review_mode: str | None = None) -> dict:
    active_review_mode = review_mode(text, explicit_review_mode)
    has_review_verdict = bool(
        STATUS_REJECTED_RE.search(text)
        or REVIEW_NEEDS_CHANGES_RE.search(text)
        or REVIEW_APPROVED_RE.search(text)
    )
    if task_dir and has_review_verdict:
        artifact = validate_completion_artifact("reviewer", Path(task_dir), text)
        if artifact["action"] == "retry_validation":
            reason = artifact["reason"]
            return with_budget({
                "action": "retry",
                "trigger": "semantic_completion_artifact",
                "reason": reason,
                "directive": DIRECTIVES[reason],
                "retry_target": "reviewer",
                "review_mode": active_review_mode,
                "artifact_field": artifact["field"],
                "artifact_path": artifact["path"],
            }, "reviewer")

    if STATUS_REJECTED_RE.search(text):
        reason_match = REASON_RE.search(text)
        reason = reason_match.group(1) if reason_match else "reviewer_rejected"
        return with_budget({
            "action": "retry",
            "trigger": "STATUS: REJECTED",
            "reason": reason,
            "directive": DIRECTIVES.get(reason, DIRECTIVES["review_needs_changes"]),
            "retry_target": "implementer",
            "review_mode": active_review_mode,
        }, "implementer")

    if REVIEW_NEEDS_CHANGES_RE.search(text):
        contract = review_contract_status(text, active_review_mode, task_dir)
        reason_match = REASON_RE.search(text)
        reason = reason_match.group(1) if reason_match else "review_needs_changes"
        issues_match = ISSUES_RE.search(text)
        issues = int(issues_match.group(1)) if issues_match else None
        report = report_path(text)
        if not contract["valid"]:
            return with_budget({
                "action": "retry",
                "trigger": "REVIEW: NEEDS_CHANGES",
                "reason": "review_contract_invalid",
                "directive": DIRECTIVES["review_contract_invalid"],
                "issues": issues,
                "report": report,
                "retry_target": "reviewer",
                "review_mode": active_review_mode,
                "review_contract_valid": False,
                "review_contract_violations": contract["violations"],
                "new_must_lines": contract["new_must_lines"],
                "new_must_classification": contract["new_must_classification"],
            }, "reviewer")
        directive = DIRECTIVES.get(reason, DIRECTIVES["review_needs_changes"]).replace(
            "${TASK_DIR}/context/review.md",
            report,
        )
        return with_budget({
            "action": "retry",
            "trigger": "REVIEW: NEEDS_CHANGES",
            "reason": reason,
            "directive": directive,
            "issues": issues,
            "report": report,
            "retry_target": "implementer",
            "review_mode": active_review_mode,
            "review_contract_valid": True,
            "review_contract_violations": [],
            "new_must_lines": contract["new_must_lines"],
            "new_must_classification": contract["new_must_classification"],
        }, "implementer")

    if REVIEW_APPROVED_RE.search(text):
        metrics_path = quality_metrics_path(text)
        if not metrics_path:
            return with_budget({
                "action": "retry",
                "trigger": "REVIEW: APPROVED",
                "reason": "quality_metrics_missing",
                "directive": DIRECTIVES["quality_metrics_missing"],
                "retry_target": "reviewer",
                "review_mode": active_review_mode,
            }, "reviewer")
        resolved = resolve_quality_metrics_path(metrics_path, task_dir)
        if resolved is not None and not resolved.is_file():
            return with_budget({
                "action": "retry",
                "trigger": "REVIEW: APPROVED",
                "reason": "quality_metrics_file_missing",
                "directive": DIRECTIVES["quality_metrics_file_missing"],
                "quality_metrics": metrics_path,
                "retry_target": "reviewer",
                "review_mode": active_review_mode,
            }, "reviewer")
        return {
            "action": "approve",
            "trigger": "REVIEW: APPROVED",
            "reason": "review_approved",
            "directive": "",
            "quality_metrics": metrics_path,
            "retry_target": "",
            "review_mode": active_review_mode,
        }

    return {
        "action": "none",
        "trigger": "",
        "reason": "no_review_verdict",
        "directive": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response")
    parser.add_argument("--task-dir")
    parser.add_argument("--review-mode", choices=["full-rescan", VERIFY_PRIOR_MUST_ONLY])
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    text, error = read_response(args.response)
    if error:
        print(error, file=sys.stderr)
        return 2

    result = classify(text, task_dir=args.task_dir, explicit_review_mode=args.review_mode)
    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"ACTION: {result['action']}")
        print(f"REASON: {result['reason']}")
        if result.get("retry_target"):
            print(f"RETRY_TARGET: {result['retry_target']}")
        if result.get("review_mode"):
            print(f"REVIEW_MODE: {result['review_mode']}")
        if result.get("directive"):
            print(f"DIRECTIVE: {result['directive']}")
    return 1 if result["action"] == "retry" else 0


if __name__ == "__main__":
    raise SystemExit(main())
