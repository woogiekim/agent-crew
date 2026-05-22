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
)


CODE_IMPLEMENTATION_TASK_RE = re.compile(
    r"\b("
    r"implement|build|fix|refactor|migrate|integrate|code|test|backend|"
    r"frontend|api|cli|runtime|pipeline"
    r")\b|구현|개발|수정|개선|리팩터|테스트|백엔드|프론트|파이프라인",
    re.IGNORECASE,
)


def looks_code_implementation_task(text: str) -> bool:
    return bool(CODE_IMPLEMENTATION_TASK_RE.search(text or ""))


def validate_pipeline_quality_plan(pipeline: dict, task: str | None = None) -> dict:
    task_text = task if task is not None else str(pipeline.get("task", ""))
    stages = pipeline.get("stages") or []
    shape = pipeline_shape(pipeline)
    code_task = looks_code_implementation_task(task_text)
    required = looks_mutating_task(task_text) and (code_task or shape["has_implementation_stage"])

    failures: list[str] = []
    implementation_stage_results: list[dict] = []

    if required:
        if not shape["has_implementation_stage"]:
            failures.append("missing_pipeline_implementation_stage")

        for idx, stage in enumerate(stages):
            if not is_implementation_stage(stage):
                continue

            agents = stage_agents(stage)
            tdd_capable = is_tdd_capable_stage(stage)
            result = {
                "stage_index": idx,
                "agents": agents,
                "tdd_capable": tdd_capable,
            }
            implementation_stage_results.append(result)

            if not tdd_capable:
                failures.append("implementation_stage_without_tdd_parallel")
                if len(agents) > 1:
                    failures.append("multi_agent_implementation_stage_must_split_for_tdd")

        if not shape["has_reviewer_stage"]:
            failures.append("missing_pipeline_reviewer_stage")
        if not shape["has_reviewer_after_implementer"]:
            failures.append("missing_pipeline_reviewer_after_implementer")

    return {
        "passed": not failures,
        "required": required,
        "code_task": code_task,
        "failures": sorted(set(failures)),
        "task": task_text,
        "pipeline_shape": shape,
        "implementation_stages": implementation_stage_results,
    }


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
