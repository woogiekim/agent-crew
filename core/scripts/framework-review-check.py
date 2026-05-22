#!/usr/bin/env python3
"""Static operational readiness review for the agent-crew framework."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def has_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def exists(root: Path, rel: str) -> bool:
    return (root / rel).exists()


def control(category: str, name: str, severity: str, passed: bool, detail: str) -> dict:
    return {
        "category": category,
        "name": name,
        "severity": severity,
        "passed": bool(passed),
        "detail": detail,
    }


def evaluate_repo(root: Path) -> dict:
    root = root.resolve()
    crew = read_text(root / "core/bin/crew")
    guard = read_text(root / "core/hooks/guard-dangerous-commands.sh")
    pipeline_schema = read_text(root / "core/schemas/pipeline.schema.json")
    pipeline_rule = read_text(root / "core/rules/state-files/pipeline-json.md")
    supervisor = read_text(root / "core/agents/supervisor.md")
    supervisor_retry = read_text(root / "core/agents/supervisor-retry.md")
    reviewer = read_text(root / "core/agents/reviewer.md")
    memory_rule = read_text(root / "core/rules/memory-governance.md")
    memory_fixture = read_text(root / "core/evaluations/memory-retrieval.json")
    answer_quality = read_text(root / "core/evaluations/answer-quality.json")
    slo_fixture = read_text(root / "core/evaluations/e2e-slo.json")
    update_benchmark = read_text(root / "core/scripts/update-slo-benchmark.py")

    controls = [
        control(
            "architecture",
            "core_roles_present",
            "high",
            all(
                exists(root, f"core/agents/{agent}.md")
                for agent in ("supervisor", "planner", "backend", "frontend", "devops", "reviewer")
            ),
            "Planner/orchestrator, worker, DevOps, and reviewer roles must be materialized.",
        ),
        control(
            "architecture",
            "explicit_state_machine",
            "high",
            has_all(pipeline_schema, ["stages", "completed_stages", "stage_agent_status"])
            and "pipeline.json" in pipeline_rule,
            "Workflow transitions must be represented by explicit pipeline state.",
        ),
        control(
            "architecture",
            "reviewer_read_only_boundary",
            "high",
            "Read-only" in reviewer and "never modifies implementation files" in reviewer,
            "Reviewer role must validate without modifying production state.",
        ),
        control(
            "performance",
            "slo_fixture_present",
            "high",
            has_all(
                slo_fixture,
                ["status_budget_ms", "telemetry_budget_ms", "memory_search_budget_ms", "update_noop_local_budget_ms"],
            ),
            "Performance budgets must be checked by a fixture, not only by ad hoc observation.",
        ),
        control(
            "performance",
            "noop_update_benchmark_warmup",
            "medium",
            "warmup_elapsed_ms" in update_benchmark and "should_warm_noop" in update_benchmark,
            "No-op update latency must measure a warmed true no-op.",
        ),
        control(
            "quality",
            "quality_loop_gate",
            "high",
            exists(root, "core/scripts/quality-loop-check.py")
            and exists(root, "core/scripts/pipeline-quality-plan-check.py")
            and "require_quality_loop_for_implementation_reports" in answer_quality,
            "Implementation completion must require TDD/reviewer evidence or an explicit bypass.",
        ),
        control(
            "quality",
            "structured_report_gate",
            "medium",
            has_all(answer_quality, ["allowed_blockers", "memory_evidence_trace_path", "require_memory_evidence_trace_when_context_available"]),
            "Reports must include evidence, blocker classification, and memory reuse traceability.",
        ),
        control(
            "reliability",
            "retry_governance",
            "high",
            has_all(supervisor_retry, ["up to **3 retries**", "up to **5 retries**", "cost_budget_exceeded"]),
            "Retries must have explicit budgets and cost breaker behavior.",
        ),
        control(
            "memory_governance",
            "memory_lifecycle_rule",
            "high",
            has_all(memory_rule, ["capture -> classify -> summarize -> score -> archive -> evict", "Trust Separation"]),
            "Memory lifecycle and trust separation must be documented as policy.",
        ),
        control(
            "memory_governance",
            "retrieval_eval_budget",
            "high",
            has_all(memory_fixture, ["expected_memory_ids", "latency_budget_ms", "noise_budget_count"]),
            "Critical memory retrieval must pin expected IDs, latency budget, and noise budget.",
        ),
        control(
            "memory_governance",
            "memory_evidence_trace",
            "medium",
            exists(root, "core/scripts/memory-evidence-trace.py")
            and "memory_evidence_trace_path" in answer_quality,
            "Final reports must be able to prove which memory context was reused.",
        ),
        control(
            "security",
            "forbidden_tool_policy",
            "high",
            has_all(guard, ["FORBIDDEN_PATTERNS", "force-push", "sudo", "credential-access"]),
            "Sudo, force push, and credential access must be denied by policy.",
        ),
        control(
            "security",
            "dangerous_command_approval_gate",
            "high",
            has_all(guard, ["DANGEROUS_PATTERNS", "dangerous-commands.approved", "approval_command_mismatch"]),
            "Merge, push, deploy, and destructive commands must require command-bound approval.",
        ),
        control(
            "security",
            "direct_edit_guard",
            "medium",
            exists(root, "core/hooks/direct-edit-guard.sh") and exists(root, "core/rules/direct-edit-guard.md"),
            "Direct production edits must be routed through the workflow unless explicitly marked active.",
        ),
        control(
            "observability",
            "telemetry_and_trace",
            "high",
            exists(root, "core/scripts/telemetry-aggregate.py")
            and "progress.buffer.jsonl" in supervisor
            and "trace_id" in supervisor,
            "Workflow timing, retry, blocker, token, and trace state must be observable.",
        ),
        control(
            "cost_efficiency",
            "native_cost_command",
            "high",
            "cmd_cost()" in crew and re.search(r"\bcost\)\s+cmd_cost", crew) is not None,
            "Native CLI must expose cost aggregation, not only prompt aliases.",
        ),
        control(
            "cost_efficiency",
            "cost_circuit_breaker",
            "high",
            exists(root, "core/scripts/cost-aggregate.py") and "COST_BLOCKED" in supervisor_retry,
            "Per-task token budgets must be enforceable by the supervisor.",
        ),
        control(
            "developer_experience",
            "doctor_command",
            "medium",
            "cmd_doctor()" in crew and re.search(r"\bdoctor\)\s+cmd_doctor", crew) is not None,
            "A single native command should expose framework readiness diagnostics.",
        ),
        control(
            "long_term_scalability",
            "capability_gated_runtime",
            "high",
            exists(root, "core/schemas/capabilities.schema.json")
            and exists(root, "core/rules/host-capabilities.md")
            and "HAS_COST_TRACKING" in read_text(root / "core/agents/supervisor-bootstrap.md"),
            "Host features must be capability-gated for provider-neutral scaling.",
        ),
    ]

    by_category: dict[str, dict[str, int]] = {}
    for item in controls:
        stats = by_category.setdefault(item["category"], {"passed": 0, "failed": 0})
        stats["passed" if item["passed"] else "failed"] += 1

    failures = [item for item in controls if not item["passed"]]
    return {
        "schema_version": 1,
        "project_root": str(root),
        "passed": not failures,
        "summary": {
            "controls": len(controls),
            "passed": len(controls) - len(failures),
            "failed": len(failures),
            "categories": by_category,
        },
        "controls": controls,
        "failures": failures,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(repo_root))
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    result = evaluate_repo(Path(args.project_root))
    if args.format == "json":
        json.dump(result, __import__("sys").stdout, indent=2)
        print()
    else:
        status = "PASS" if result["passed"] else "FAIL"
        summary = result["summary"]
        print(f"{status}: framework review check")
        print(f"controls={summary['controls']} passed={summary['passed']} failed={summary['failed']}")
        for failure in result["failures"]:
            print(f"- {failure['severity']} {failure['category']}.{failure['name']}: {failure['detail']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
