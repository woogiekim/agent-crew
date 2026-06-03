#!/usr/bin/env python3
"""Deterministic requirements sufficiency gate for crew:run.

This helper keeps the scoring logic out of large command/agent prompt bodies.
It is intentionally conservative: a task is sufficient only when it carries
scope, target, and constraint signals, and question-like prompts still ask.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path


QUESTION_MARKERS = (
    "?",
    "how should",
    "what about",
    "which ",
    "should i",
    "shall i",
    "do you think",
)

BACKEND_KW = (
    "backend",
    "api",
    "server",
    "endpoint",
    "database",
    "domain model",
    "schema",
)
UI_KW = (
    "frontend",
    "ui ",
    "component",
    " page ",
    "css",
    "styling",
    "layout",
)
TOOLING_KW = (
    "docs",
    "documentation",
    "readme",
    "markdown",
    "config",
    "script",
    "refactor",
    "spec",
    "tooling",
    "pipeline",
    "workflow",
    "agent",
    "hook",
    "prompt",
    "instruction",
    "status",
    "telemetry",
    "benchmark",
    "coverage",
    "python",
    "bash",
    "shell script",
)
WORKFLOW_TARGET_KW = (
    "current branch",
    "current behavior",
    "latest fixes",
    "previous validation report",
    "validation report",
    "commercialization blocker",
    "commercial blockers",
    "commercialization-focused end-to-end validation",
    "commercialization-focused e2e validation",
    "end-to-end validation",
    "e2e validation",
    "crew setup",
    "crew run",
    "crew status",
    "crew update",
    "crew agent",
    "fake-host e2e",
    "fake host e2e",
    "host handoff",
    "stale or incomplete pipeline",
    "incomplete pipeline",
    "run flow",
    "status flow",
    "agent flow",
    "update flow",
    "run/update/status/agent",
    "prompt surface",
    "instruction surface",
    "telemetry/status",
    "status reporting",
    "status and telemetry guidance",
    "benchmark/test coverage",
    "test coverage",
    "prompt-runtime overhead",
)
PERF_KW = (
    "performance",
    "latency",
    "slow",
    "slowness",
    "fast",
    "faster",
    "speed",
    "throughput",
    "overhead",
    "prompt surface",
    "token",
    "tokens",
)
QUALITY_KW = (
    "quality",
    "answer quality",
    "failure guidance",
    "status guidance",
    "actionable",
    "user-visible",
)
INTENSITY_CHOICES = ("light", "balanced", "deep", "strict")
DEFAULT_INTENSITY = "balanced"
DEFAULT_AMBIGUITY_THRESHOLD = 0.20


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _workflow_target_count(text: str) -> int:
    return sum(1 for needle in WORKFLOW_TARGET_KW if needle in text)


def sufficiency_signals(task: str) -> dict:
    """Return the signal map used for deterministic classification."""
    t = task.lower()
    has_question = _contains_any(t, QUESTION_MARKERS)

    backend_hit = _contains_any(t, BACKEND_KW)
    ui_hit = _contains_any(t, UI_KW)
    tooling_hit = _contains_any(t, TOOLING_KW)
    has_script_file = bool(
        re.search(r"\.(py|sh|js|ts|jsx|tsx)\b", task, re.IGNORECASE)
    )
    extension_scope = has_script_file
    scope_hit = backend_hit or ui_hit or tooling_hit or extension_scope

    has_file_path = re.search(
        r"[a-zA-Z0-9_./-]+\.(md|py|ts|tsx|js|jsx|sh|json|yml|yaml)",
        task,
    ) is not None
    has_branch_ref = re.search(
        r"\b(feat|fix|docs|chore|refactor|test)/[a-z0-9-]+",
        task,
    ) is not None
    has_quoted_name = '"' in task or "`" in task
    has_concrete_pointer = re.search(
        r"\bthe [a-z]+ (agent|hook|command|step|phase|rule|gate|file|module)",
        t,
    ) is not None
    workflow_targets = _workflow_target_count(t)
    target_hit = (
        has_file_path
        or has_branch_ref
        or has_quoted_name
        or has_concrete_pointer
        or workflow_targets >= 2
    )

    has_numeric_perf = (
        re.search(r"\d+\s*(ms|s\b|mb|gb|req/s|qps|rps)", t) is not None
    )
    has_perf = has_numeric_perf or _contains_any(t, PERF_KW)
    has_quality = _contains_any(t, QUALITY_KW)
    has_mvp = _contains_any(t, ("mvp", "minimal", "v1 ", "scope-limit", "scope limit"))
    has_dep = _contains_any(
        t,
        (
            "no new deps",
            "no new dependencies",
            "existing stack",
            "existing tech stack",
            "use only",
        ),
    )
    has_no_remote = (
        ("do not push" in t)
        or ("do not merge" in t)
        or ("without approval" in t and ("push" in t or "merge" in t))
    )
    has_func_spec = bool(
        re.search(r"\b(function|functions|method|methods|parameter|param)\b", t)
    ) or bool(re.search(r"[a-zA-Z_]\w*\([^)]*\)", task))
    constraint_hit = (
        has_perf
        or has_quality
        or has_mvp
        or has_dep
        or has_no_remote
        or (has_script_file and has_func_spec)
    )

    return {
        "has_question": has_question,
        "backend_hit": backend_hit,
        "ui_hit": ui_hit,
        "tooling_hit": tooling_hit or extension_scope,
        "scope_hit": scope_hit,
        "target_hit": target_hit,
        "constraint_hit": constraint_hit,
        "has_perf": has_perf,
        "has_quality": has_quality,
        "has_mvp": has_mvp,
        "has_dep": has_dep,
        "has_no_remote": has_no_remote,
        "has_script_func_spec": has_script_file and has_func_spec,
        "workflow_targets": workflow_targets,
    }


def sufficiency_check(task: str) -> str:
    """Return SUFFICIENT when TASK can safely synthesize requirements."""
    signals = sufficiency_signals(task)
    if signals["has_question"]:
        return "AMBIGUOUS"
    if signals["scope_hit"] and signals["target_hit"] and signals["constraint_hit"]:
        return "SUFFICIENT"
    return "AMBIGUOUS"


def _default_intensity() -> str:
    return os.environ.get("AGENT_CREW_INTERACTION_INTENSITY", DEFAULT_INTENSITY)


def _default_threshold() -> float:
    raw = os.environ.get("AGENT_CREW_AMBIGUITY_THRESHOLD")
    if raw is None:
        return DEFAULT_AMBIGUITY_THRESHOLD
    return float(raw)


def normalize_intensity(value: str) -> str:
    intensity = value.strip().lower()
    if intensity not in INTENSITY_CHOICES:
        choices = ", ".join(INTENSITY_CHOICES)
        raise ValueError(f"intensity must be one of: {choices}")
    return intensity


def normalize_threshold(value: float) -> float:
    threshold = float(value)
    if threshold < 0 or threshold > 1:
        raise ValueError("ambiguity threshold must be between 0 and 1")
    return threshold


def ambiguity_dimensions(signals: dict) -> list[dict]:
    """Return deterministic ambiguity dimensions for policy decisions."""
    has_acceptance_signal = (
        signals["has_perf"]
        or signals["has_quality"]
        or signals["has_mvp"]
        or signals["has_script_func_spec"]
    )
    dimensions = [
        ("intent", not signals["has_question"]),
        ("scope", signals["scope_hit"]),
        ("target", signals["target_hit"]),
        ("constraints", signals["constraint_hit"]),
        ("success_criteria", has_acceptance_signal),
    ]
    return [
        {"name": name, "present": bool(present)}
        for name, present in dimensions
    ]


def ambiguity_score(dimensions: list[dict]) -> float:
    missing = sum(1 for dimension in dimensions if not dimension["present"])
    return round(missing / len(dimensions), 2)


def policy_next_action(
    *,
    status: str,
    ambiguity: float,
    threshold: float,
    intensity: str,
    signals: dict,
) -> str:
    """Return the next workflow action for the interaction policy."""
    if signals["has_question"] and intensity == "light":
        return "direct_answer"

    if status == "SUFFICIENT" and ambiguity <= threshold:
        return "synthesize"

    if intensity == "light":
        return "single_round"
    if intensity == "balanced":
        return "single_round"
    if intensity == "deep" and ambiguity > threshold:
        return "deep_interview"
    if intensity == "strict" and ambiguity > threshold:
        return "deep_interview"
    return "single_round"


def policy_report(
    task: str,
    *,
    intensity: str | None = None,
    threshold: float | None = None,
) -> dict:
    """Return the full sufficiency and ambiguity policy report."""
    resolved_intensity = normalize_intensity(intensity or _default_intensity())
    resolved_threshold = normalize_threshold(
        _default_threshold() if threshold is None else threshold
    )
    signals = sufficiency_signals(task)
    status = sufficiency_check(task)
    dimensions = ambiguity_dimensions(signals)
    ambiguity = ambiguity_score(dimensions)
    missing = [
        dimension["name"]
        for dimension in dimensions
        if not dimension["present"]
    ]
    implementation_allowed = status == "SUFFICIENT" and ambiguity <= resolved_threshold
    next_action = policy_next_action(
        status=status,
        ambiguity=ambiguity,
        threshold=resolved_threshold,
        intensity=resolved_intensity,
        signals=signals,
    )

    return {
        "status": status,
        "intensity": resolved_intensity,
        "ambiguity": ambiguity,
        "ambiguity_threshold": resolved_threshold,
        "implementation_allowed": implementation_allowed,
        "next_action": next_action,
        "dimensions": dimensions,
        "missing_dimensions": missing,
        "signals": signals,
    }


def codex_skill_context(task: str) -> str:
    """Return a compact marker for explicit Codex skill mentions in TASK."""
    skill_names = set(re.findall(r"(?<!\w)\$([A-Za-z][\w:-]*)", task))
    skill_names.update(re.findall(r"Skill\([\"']([^\"']+)[\"']\)", task))
    if not skill_names:
        return "(none)"
    return ", ".join(sorted(skill_names))


def synthesize_requirements(
    task: str,
    *,
    intensity: str | None = None,
    threshold: float | None = None,
) -> str:
    """Return a requirements block compatible with the requirements agent."""
    signals = sufficiency_signals(task)
    policy = policy_report(task, intensity=intensity, threshold=threshold)

    if signals["backend_hit"] and signals["ui_hit"]:
        scope = "Full-stack"
    elif signals["backend_hit"]:
        scope = "Backend API"
    elif signals["ui_hit"]:
        scope = "UI only"
    else:
        scope = "Tooling / docs / config"

    lowered = task.lower()
    if signals["tooling_hit"]:
        target = "Developer tooling or API"
    elif any(k in lowered for k in ("admin", "dashboard", "internal")):
        target = "Internal team / admin tooling"
    elif '"' in task or "`" in task or signals["ui_hit"]:
        target = "End-user product feature"
    else:
        target = "Other / not yet defined"

    constraints = []
    if signals["has_perf"]:
        constraints.append("Performance / scalability")
    if signals["has_quality"]:
        constraints.append("Answer quality / failure guidance")
    if signals["has_mvp"]:
        constraints.append("MVP scope")
    if signals["has_dep"]:
        constraints.append("Use existing tech stack only")
    if signals["has_no_remote"]:
        constraints.append("No remote publish without approval")
    if signals["has_script_func_spec"]:
        constraints.append("Explicit function/interface spec")
    if not constraints:
        constraints.append("No special constraints")

    return (
        "REQUIREMENTS: |\n"
        f"  scope: {scope}\n"
        f"  target: {target}\n"
        f"  constraints: {', '.join(constraints)}\n"
        f"  skill_context: {codex_skill_context(task)}\n"
        "  followup: (none)\n"
        "  sufficiency: HIGH\n"
        f"  ambiguity: {policy['ambiguity']:.2f}\n"
        f"  ambiguity_threshold: {policy['ambiguity_threshold']:.2f}\n"
        f"  interaction_intensity: {policy['intensity']}\n"
        f"  implementation_allowed: {str(policy['implementation_allowed']).lower()}\n"
        "  inline_synthesis: true\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="agent-crew requirements sufficiency helper"
    )
    parser.add_argument("task")
    parser.add_argument("--status", action="store_true", help="print SUFFICIENT/AMBIGUOUS")
    parser.add_argument("--requirements", action="store_true", help="print synthesized requirements")
    parser.add_argument("--json", action="store_true", help="print status and signals as JSON")
    parser.add_argument("--policy", action="store_true", help="print the interaction policy next action")
    parser.add_argument(
        "--intensity",
        default=_default_intensity(),
        help="interaction intensity: light, balanced, deep, or strict",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="ambiguity threshold from 0 to 1; defaults to AGENT_CREW_AMBIGUITY_THRESHOLD or 0.20",
    )
    parser.add_argument("--write", help="write synthesized requirements to this path")
    args = parser.parse_args()

    try:
        intensity = normalize_intensity(args.intensity)
        threshold = normalize_threshold(
            _default_threshold() if args.threshold is None else args.threshold
        )
    except ValueError as exc:
        parser.error(str(exc))

    status = sufficiency_check(args.task)
    report = policy_report(args.task, intensity=intensity, threshold=threshold)
    requirements = synthesize_requirements(
        args.task,
        intensity=intensity,
        threshold=threshold,
    )

    if args.write:
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(requirements, encoding="utf-8")

    if args.json:
        print(json.dumps({
            "status": status,
            "intensity": report["intensity"],
            "ambiguity": report["ambiguity"],
            "ambiguity_threshold": report["ambiguity_threshold"],
            "implementation_allowed": report["implementation_allowed"],
            "next_action": report["next_action"],
            "dimensions": report["dimensions"],
            "missing_dimensions": report["missing_dimensions"],
            "signals": report["signals"],
            "requirements": requirements,
        }, ensure_ascii=False, indent=2))
    elif args.policy:
        print(report["next_action"])
    elif args.requirements:
        print(requirements, end="")
    elif args.write and not args.status:
        pass
    else:
        print(status)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
