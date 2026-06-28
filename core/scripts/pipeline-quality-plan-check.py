#!/usr/bin/env python3
"""Validate that a planned implementation pipeline includes the quality loop.

Inputs:
  --pipeline PATH             pipeline.json emitted by analyst/planner.
  --task TEXT                 Optional task text; defaults to pipeline["task"].
  --format text|json          Output format.

Outputs:
  text: PASS/FAIL plus failure labels.
  json: structured validation payload.

Exit codes:
  0 - plan is valid or quality-loop planning is not required
  1 - validation failed
  2 - invalid arguments

PRD placeholder scan
--------------------

In addition to pipeline-shape checks, this script scans the PRD that lives
alongside the pipeline (``<dirname(pipeline.json)>/context/prd.md``) for a
closed list of placeholder tokens. The scan is provider-neutral
(python stdlib only) and runs automatically when ``prd.md`` exists. There
is no CLI flag to enable or disable it.

Forbidden tokens (case-insensitive, whole-word/phrase):

- ``TBD``
- ``TODO``
- ``FIXME``
- ``XXX``
- ``implement later``
- ``fill in details``
- ``add appropriate error handling``

Multi-word phrases match with arbitrary internal whitespace collapsed to a
single space (``implement   later`` matches ``implement later``).

Skip rules:

- Markdown blockquote lines (lines whose first non-whitespace character is
  ``>``) are skipped, so the analyst rule itself can document the
  forbidden tokens without triggering a failure.
- Lines inside fenced code blocks (between paired ``\`\`\``` fences) are
  skipped for the same reason.

Failure labels emitted (one per matched token type, deduplicated):

- ``prd_placeholder_tbd``
- ``prd_placeholder_todo``
- ``prd_placeholder_fixme``
- ``prd_placeholder_xxx``
- ``prd_placeholder_implement_later``
- ``prd_placeholder_fill_in_details``
- ``prd_placeholder_add_appropriate_error_handling``

Result payload additions:

- ``prd_path`` (str) — resolved PRD path (whether or not it exists).
- ``prd_missing`` (bool) — ``True`` when no PRD file was found; the scan
  is skipped and the gate is not failed by the PRD's absence (preserves
  backward compatibility for legacy pipelines and design-only flows).
- ``prd_placeholder_hits`` (list of ``{token, line, snippet}`` dicts) —
  one entry per hit (NOT deduplicated). ``snippet`` is the stripped
  matched line, truncated to 120 characters.

Exit code interaction: any placeholder hit causes exit 1 (joins the
existing failure-driven exit logic). A missing PRD has no effect on the
exit code by itself.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from quality_loop_lib import (
    is_implementation_stage,
    is_tdd_capable_stage,
    load_json,
    looks_mutating_task,
    pipeline_shape,
    stage_agents,
    stage_implementer_agents,
)


CODE_IMPLEMENTATION_TASK_RE = re.compile(
    r"\b("
    r"implement|build|fix|refactor|migrate|integrate|code|test|backend|"
    r"frontend|api|cli|runtime|pipeline"
    r")\b|구현|개발|수정|개선|리팩터|테스트|백엔드|프론트|파이프라인",
    re.IGNORECASE,
)


# Closed list of forbidden PRD placeholder tokens. Each entry is a
# (regex_pattern, slug) tuple. Multi-word phrases use ``\s+`` so arbitrary
# internal whitespace still matches. Word boundaries (``\b``) ensure
# ``TODO`` does not match inside ``TODOIST``.
#
# Keep this list closed (KISS / YAGNI / false-positive conservatism). Do
# not add fuzzy English-prose heuristics — the goal is to catch known
# placeholder tokens, not to police prose.
PRD_PLACEHOLDER_PATTERNS: list[tuple[str, str]] = [
    (r"\bTBD\b", "tbd"),
    (r"\bTODO\b", "todo"),
    (r"\bFIXME\b", "fixme"),
    (r"\bXXX\b", "xxx"),
    (r"\bimplement\s+later\b", "implement_later"),
    (r"\bfill\s+in\s+details\b", "fill_in_details"),
    (r"\badd\s+appropriate\s+error\s+handling\b", "add_appropriate_error_handling"),
]

_COMPILED_PRD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), slug)
    for pattern, slug in PRD_PLACEHOLDER_PATTERNS
]

NEED_ANALYSIS_KEYS = [
    "can_solve_without_code",
    "existing_project_code",
    "framework_functionality",
    "standard_library",
    "configuration",
    "infrastructure",
    "existing_api",
    "delete_instead",
]

CAPABILITY_SEARCH_ORDER = [
    "existing_project_code",
    "existing_utilities",
    "language_features",
    "standard_library",
    "framework_features",
    "installed_libraries",
    "platform_capabilities",
    "infrastructure_configuration",
]

DIFF_BUDGET_CATEGORIES = {"XS", "S", "M", "L", "XL"}
NEED_ANALYSIS_ANSWERS = {"yes", "no"}

_BLOCKQUOTE_RE = re.compile(r"^\s*>")
_FENCE_RE = re.compile(r"^\s*```")
_AC_ID_RE = re.compile(r"\bAC-\d+\b", re.IGNORECASE)
_SNIPPET_MAX = 120


def looks_code_implementation_task(text: str) -> bool:
    return bool(CODE_IMPLEMENTATION_TASK_RE.search(text or ""))


def scan_prd_placeholders(prd_path: Path) -> dict:
    """Scan ``prd_path`` for forbidden placeholder tokens.

    Returns a dict with three keys:

    - ``prd_path`` (str): the resolved path (always present).
    - ``prd_missing`` (bool): ``True`` when the file does not exist.
    - ``hits`` (list[dict]): one ``{token, line, snippet}`` entry per
      match. Lines inside markdown blockquotes (``>``) and fenced code
      blocks (``\`\`\```` toggled) are skipped. Slugs are NOT
      deduplicated here — callers dedupe when building failure labels.
    """

    result: dict = {
        "prd_path": str(prd_path),
        "prd_missing": False,
        "hits": [],
    }

    if not prd_path.is_file():
        result["prd_missing"] = True
        return result

    text = prd_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    in_fence = False
    for lineno, raw_line in enumerate(lines, start=1):
        if _FENCE_RE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _BLOCKQUOTE_RE.match(raw_line):
            continue

        for pattern, slug in _COMPILED_PRD_PATTERNS:
            match = pattern.search(raw_line)
            if not match:
                continue

            snippet = raw_line.strip()
            if len(snippet) > _SNIPPET_MAX:
                snippet = snippet[:_SNIPPET_MAX]

            result["hits"].append(
                {
                    "token": match.group(0),
                    "line": lineno,
                    "snippet": snippet,
                    "slug": slug,
                }
            )

    return result


def extract_prd_acceptance_criteria(prd_path: Path) -> list[str]:
    if not prd_path.is_file():
        return []

    ids: list[str] = []
    in_fence = False
    for raw_line in prd_path.read_text(encoding="utf-8").splitlines():
        if _FENCE_RE.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence or _BLOCKQUOTE_RE.match(raw_line):
            continue
        for match in _AC_ID_RE.finditer(raw_line):
            value = match.group(0).upper()
            if value not in ids:
                ids.append(value)

    return ids


def stage_acceptance_criteria_ids(stages: list) -> list[str]:
    ids: list[str] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        values = stage.get("acceptance_criteria") or []
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue
        for value in values:
            for match in _AC_ID_RE.finditer(str(value)):
                item = match.group(0).upper()
                if item not in ids:
                    ids.append(item)

    return ids


def _nonempty_list(value: object) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)


def validate_minimal_change_decision_context(
    pipeline: dict,
    required: bool,
    shape: dict,
) -> dict:
    """Validate Ponytail-inspired minimal-change planning context.

    This intentionally uses the existing open-ended ``pipeline.json`` surface:
    no new state file, no new schema version, and no dependency beyond the
    Python standard library.
    """

    failures: list[str] = []
    context = pipeline.get("decision_context")
    if not required:
        return {
            "required": False,
            "present": isinstance(context, dict),
            "failures": failures,
        }

    if not isinstance(context, dict):
        failures.append("missing_minimal_change_decision_context")
        return {
            "required": True,
            "present": False,
            "failures": failures,
        }

    need_analysis = context.get("need_analysis")
    missing_need_keys: list[str] = []
    invalid_need_keys: list[str] = []
    yes_answers: list[str] = []
    if not isinstance(need_analysis, dict):
        failures.append("missing_need_analysis")
    else:
        for key in NEED_ANALYSIS_KEYS:
            answer = str(need_analysis.get(key, "")).strip().lower()
            if answer == "":
                missing_need_keys.append(key)
            elif answer not in NEED_ANALYSIS_ANSWERS:
                invalid_need_keys.append(key)
            elif answer == "yes":
                yes_answers.append(key)
        if missing_need_keys:
            failures.append("incomplete_need_analysis")
        if invalid_need_keys:
            failures.append("invalid_need_analysis_answer")

    capability_search = context.get("capability_search")
    if isinstance(capability_search, list):
        search_order = [str(item).strip() for item in capability_search]
    else:
        search_order = []

    if search_order != CAPABILITY_SEARCH_ORDER:
        failures.append("capability_search_order_incomplete")

    diff_budget = context.get("diff_budget")
    diff_category = ""
    if isinstance(diff_budget, dict):
        diff_category = str(diff_budget.get("category", "")).strip().upper()
    if diff_category not in DIFF_BUDGET_CATEGORIES:
        failures.append("invalid_diff_budget")
    if diff_category in {"L", "XL"} and not _nonempty_list(
        context.get("smaller_alternatives_rejected")
    ):
        failures.append("large_diff_budget_missing_rejected_alternatives")

    if not _nonempty_list(context.get("will_do")):
        failures.append("missing_will_do")
    if not _nonempty_list(context.get("will_not_do")):
        failures.append("missing_will_not_do")
    if not str(context.get("selected_solution", "")).strip():
        failures.append("missing_selected_solution")
    if (
        shape.get("has_implementation_stage")
        and not yes_answers
        and not str(context.get("new_code_allowed_reason", "")).strip()
    ):
        failures.append("missing_new_code_allowed_reason")
    if shape.get("has_implementation_stage") and yes_answers:
        failures.append("need_analysis_yes_requires_no_implementation")

    return {
        "required": True,
        "present": True,
        "failures": sorted(set(failures)),
        "yes_answers": yes_answers,
        "missing_need_keys": missing_need_keys,
        "invalid_need_keys": sorted(invalid_need_keys),
        "diff_budget": diff_category,
    }


def validate_pipeline_quality_plan(pipeline: dict, task: str | None = None) -> dict:
    task_text = task if task is not None else str(pipeline.get("task", ""))
    stages = pipeline.get("stages") or []
    shape = pipeline_shape(pipeline)
    code_task = looks_code_implementation_task(task_text)
    required = looks_mutating_task(task_text) and (code_task or shape["has_implementation_stage"])

    minimal_change = validate_minimal_change_decision_context(
        pipeline,
        required,
        shape,
    )
    no_code_route = bool(
        minimal_change.get("yes_answers")
        and not shape["has_implementation_stage"]
        and not minimal_change["failures"]
    )

    failures: list[str] = []
    implementation_stage_results: list[dict] = []

    if required and not no_code_route:
        if not shape["has_implementation_stage"]:
            failures.append("missing_pipeline_implementation_stage")

        for idx, stage in enumerate(stages):
            if not is_implementation_stage(stage):
                continue

            agents = stage_agents(stage)
            implementers = stage_implementer_agents(stage)
            tdd_capable = is_tdd_capable_stage(stage)
            result = {
                "stage_index": idx,
                "agents": agents,
                "implementers": implementers,
                "tdd_capable": tdd_capable,
            }
            implementation_stage_results.append(result)

            if len(implementers) != 1:
                failures.append("multi_agent_implementation_stage_must_split_for_tdd")

            if not tdd_capable:
                failures.append("implementation_stage_without_tdd_parallel")

        if not shape["has_reviewer_stage"]:
            failures.append("missing_pipeline_reviewer_stage")
        if not shape["has_reviewer_after_implementer"]:
            failures.append("missing_pipeline_reviewer_after_implementer")
        if not shape["has_quality_gate_after_each_implementer"]:
            failures.append("missing_pipeline_reviewer_after_each_implementer")
        if not shape["has_reviewer_after_each_qa_verify"]:
            failures.append("missing_pipeline_reviewer_after_qa_verify")

    failures.extend(minimal_change["failures"])

    return {
        "passed": not failures,
        "required": required,
        "code_task": code_task,
        "failures": sorted(set(failures)),
        "task": task_text,
        "pipeline_shape": shape,
        "implementation_stages": implementation_stage_results,
        "minimal_change_decision": minimal_change,
    }


def _apply_prd_scan(result: dict, pipeline_path: Path) -> dict:
    """Merge placeholder-scan output into ``result`` and update failures.

    The scan runs automatically when ``<pipeline_dir>/context/prd.md``
    exists. A missing PRD does not fail the gate (only sets
    ``prd_missing: True``). Any hit adds one ``prd_placeholder_<slug>``
    label per distinct slug to ``failures`` and flips ``passed`` to
    ``False``.
    """

    prd_path = pipeline_path.parent / "context" / "prd.md"
    scan = scan_prd_placeholders(prd_path)

    hits = scan["hits"]
    placeholder_hits = [
        {"token": hit["token"], "line": hit["line"], "snippet": hit["snippet"]}
        for hit in hits
    ]

    result["prd_path"] = scan["prd_path"]
    result["prd_missing"] = scan["prd_missing"]
    result["prd_placeholder_hits"] = placeholder_hits
    prd_acceptance = extract_prd_acceptance_criteria(prd_path)
    stage_acceptance = stage_acceptance_criteria_ids(
        load_json(pipeline_path).get("stages") or []
    )
    acceptance_mapping_required = bool(result.get("required") and stage_acceptance)
    unmapped = [
        item for item in prd_acceptance
        if acceptance_mapping_required and item not in stage_acceptance
    ]
    result["prd_acceptance_criteria"] = prd_acceptance
    result["pipeline_acceptance_criteria"] = stage_acceptance
    result["prd_acceptance_mapping_required"] = acceptance_mapping_required
    result["prd_unmapped_acceptance_criteria"] = unmapped

    if hits:
        slugs = {hit["slug"] for hit in hits}
        new_labels = {f"prd_placeholder_{slug}" for slug in slugs}
        existing = set(result.get("failures") or [])
        result["failures"] = sorted(existing | new_labels)
        result["passed"] = False
    if unmapped:
        existing = set(result.get("failures") or [])
        existing.add("prd_acceptance_criteria_unmapped")
        result["failures"] = sorted(existing)
        result["passed"] = False

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--task")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    pipeline_path = Path(args.pipeline)
    if not pipeline_path.is_file():
        print(f"pipeline-quality-plan-check: pipeline not found: {pipeline_path}", file=sys.stderr)
        return 2

    pipeline = load_json(pipeline_path)
    result = validate_pipeline_quality_plan(pipeline, task=args.task)
    _apply_prd_scan(result, pipeline_path)

    if args.format == "json":
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print(("PASS" if result["passed"] else "FAIL") + ": pipeline quality plan")
        for failure in result["failures"]:
            print(f"- {failure}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
