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


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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
    durable_workflow_schema = read_text(root / "core/schemas/durable-workflow.schema.json")
    durable_workflow_doc = read_text(root / "docs/durable-workflow-architecture.md")
    durable_workflow_fixture = read_text(root / "core/evaluations/durable-workflow-architecture.json")
    durable_workflow_check = read_text(root / "core/scripts/durable-workflow-architecture-check.py")
    persistent_workflow_test_doc = read_text(root / "docs/persistent-workflow-test-strategy.md")
    persistent_workflow_test_fixture = read_text(root / "core/evaluations/persistent-workflow-test-strategy.json")
    persistent_workflow_test_check = read_text(root / "core/scripts/persistent-workflow-test-check.py")
    persistent_workflow_chaos_fixture = read_text(root / "core/evaluations/persistent-workflow-chaos.json")
    persistent_workflow_chaos_check = read_text(root / "core/scripts/persistent-workflow-chaos-check.py")
    pipeline_rule = read_text(root / "core/rules/state-files/pipeline-json.md")
    quality_loop_rule = read_text(root / "core/rules/quality-loop.md")
    supervisor = read_text(root / "core/agents/supervisor.md")
    supervisor_bootstrap = read_text(root / "core/agents/supervisor-bootstrap.md")
    supervisor_stages = read_text(root / "core/agents/supervisor-stages.md")
    supervisor_retry = read_text(root / "core/agents/supervisor-retry.md")
    planner = read_text(root / "core/agents/planner.md")
    backend = read_text(root / "core/agents/backend.md")
    frontend = read_text(root / "core/agents/frontend.md")
    test_writer = read_text(root / "core/agents/test-writer.md")
    reviewer = read_text(root / "core/agents/reviewer.md")
    memory_wrapper = read_text(root / "core/bin/memory")
    memory_rule = read_text(root / "core/rules/memory-governance.md")
    memory_gc = read_text(root / "core/scripts/memory-gc.py")
    memory_fixture = read_text(root / "core/evaluations/memory-retrieval.json")
    workflow_replay_fixture = read_text(root / "core/evaluations/workflow-replay.json")
    retry_chaos_fixture = read_text(root / "core/evaluations/retry-chaos.json")
    answer_quality = read_text(root / "core/evaluations/answer-quality.json")
    slo_fixture = read_text(root / "core/evaluations/e2e-slo.json")
    update_benchmark = read_text(root / "core/scripts/update-slo-benchmark.py")
    claude_performance_check = read_text(root / "core/scripts/claude-performance-check.py")
    agent_manifest = read_json(root / "core/policies/agent-capabilities.json")
    agent_manifest_text = read_text(root / "core/policies/agent-capabilities.json")
    prompt_injection_rule = read_text(root / "core/rules/prompt-injection-defense.md")
    runtime_governance_rule = read_text(root / "core/rules/runtime-governance.md")
    tool_sandboxing_rule = read_text(root / "core/rules/tool-sandboxing.md")
    progress_buffer_rule = read_text(root / "core/rules/state-files/progress-buffer-jsonl.md")
    register_rule = read_text(root / "core/rules/state-files/register-json.md")
    quality_metrics_schema = read_text(root / "core/schemas/quality-metrics.schema.json")
    quality_loop_lib = read_text(root / "core/scripts/quality_loop_lib.py")
    capability_check = read_text(root / "core/scripts/agent-capability-check.py")
    pipeline_capability_check = read_text(root / "core/scripts/pipeline-capability-check.py")
    workflow_replay_check = read_text(root / "core/scripts/workflow-replay-check.py")
    retry_chaos_check = read_text(root / "core/scripts/retry-chaos-check.py")
    telemetry_taxonomy_check = read_text(root / "core/scripts/telemetry-taxonomy-check.py")
    crew_diagnostics = read_text(root / "core/scripts/crew-diagnostics.py")
    crew_runtime = read_text(root / "core/scripts/crew-runtime.py")
    agent_capability_schema = read_text(root / "core/schemas/agent-capabilities.schema.json")
    auto_issue_reporter = read_text(root / "core/scripts/auto-issue-reporter.py")
    auto_issue_rule = read_text(root / "core/rules/auto-issue-reporting.md")
    auto_issue_hook = read_text(root / "core/hooks/auto-issue-report.sh")
    auto_issue_test = read_text(root / "tests/shell/test_auto_issue_reporter.bash")
    crew_cli_test = read_text(root / "tests/shell/test_crew_cli.bash")
    agent_entries = agent_manifest.get("agents", {}) if isinstance(agent_manifest.get("agents"), dict) else {}
    model_tiers = {
        entry.get("model_tier")
        for entry in agent_entries.values()
        if isinstance(entry, dict)
    }

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
            "durable_workflow_architecture_contract",
            "high",
            has_all(
                durable_workflow_doc,
                [
                    "Persistent AI Workforce System",
                    "long-running durable AI execution",
                    "State Machine",
                    "Checkpoint And Resume",
                    "Role Contracts",
                    "Human-Supervised Approvals",
                    "Continuity Observability",
                    "Plugin And Runtime Extensions",
                    "Durable Workflow Protocol",
                ],
            )
            and has_all(
                durable_workflow_schema,
                [
                    "workflow_id",
                    "current_state",
                    "checkpoint",
                    "resume",
                    "approval",
                    "observability",
                    "extension_policy",
                    "memory_refs",
                ],
            )
            and has_all(
                durable_workflow_fixture,
                ["107", "108", "109", "110", "111", "112", "113"],
            )
            and "REQUIRED_STATES" in durable_workflow_check,
            "Durable workflow architecture must bind state machine, checkpoints, roles, approvals, observability, extensions, and protocol semantics to a checked contract.",
        ),
        control(
            "reliability",
            "persistent_workflow_test_strategy_contract",
            "high",
            has_all(
                persistent_workflow_test_doc,
                [
                    "Persistent AI Workforce System",
                    "Can this AI continue working tomorrow?",
                    "Can the workflow survive and continue safely?",
                    "Workflow durability",
                    "Resume and recovery",
                    "Human approval integrity",
                    "Workflow determinism",
                    "Workflow observability",
                    "Plugin isolation",
                    "Long-running operational tests",
                ],
            )
            and has_all(
                persistent_workflow_test_fixture,
                [
                    "workflow_durability",
                    "resume_and_recovery",
                    "human_approval_integrity",
                    "workflow_determinism",
                    "workflow_observability",
                    "plugin_isolation",
                    "long_running_operational",
                    "token exhaustion",
                    "memory corruption",
                    "Workflow Continuity Score",
                ],
            )
            and "REQUIRED_CATEGORIES" in persistent_workflow_test_check,
            "Persistent workflow testing must validate durability, resume/recovery, approval integrity, determinism, observability, plugin isolation, and long-running operations.",
        ),
        control(
            "reliability",
            "persistent_workflow_chaos_contract",
            "high",
            has_all(
                persistent_workflow_chaos_fixture,
                [
                    "process_crash_resume_success",
                    "runtime_restart_approval_pause",
                    "token_exhaustion_partial_replay",
                    "plugin_failure_isolated",
                    "partial_persistence_failure_safe_block",
                    "memory_corruption_recovery_blocks",
                    "infrastructure_interruption_rehydrate",
                    "Resume Success Rate",
                    "Workflow Survival Rate",
                    "Recovery Accuracy",
                    "Approval Integrity",
                    "Deterministic Stability",
                    "Workflow Continuity Score",
                ],
            )
            and has_all(
                persistent_workflow_chaos_check,
                [
                    "REQUIRED_CHAOS",
                    "REQUIRED_METRICS",
                    "simulate_case",
                    "metric_value",
                    "Workflow Continuity Score",
                    "dangerous_action",
                ],
            ),
            "Round 2 persistent workflow testing must derive operational chaos metrics from deterministic survival, resume, approval, determinism, observability, plugin, memory, and infrastructure scenarios.",
        ),
        control(
            "architecture",
            "reviewer_read_only_boundary",
            "high",
            "Read-only" in reviewer and "never modifies implementation files" in reviewer,
            "Reviewer role must validate without modifying production state.",
        ),
        control(
            "architecture",
            "agent_capability_manifest",
            "high",
            exists(root, "core/policies/agent-capabilities.json")
            and has_all(agent_capability_schema, ["model_tier", "may_delegate", "may_execute_destructive"])
            and has_all(capability_check, ["planner_orchestrator_boundary", "worker_boundary", "reviewer_read_only_boundary"])
            and {"supervisor", "planner", "backend", "frontend", "devops", "reviewer"}.issubset(agent_entries),
            "Agent role separation and tool permissions must be enforced by a machine-readable manifest.",
        ),
        control(
            "architecture",
            "pipeline_capability_preflight",
            "high",
            exists(root, "core/scripts/pipeline-capability-check.py")
            and has_all(
                supervisor_bootstrap,
                [
                    "pipeline-capability-check.py",
                    "pipeline capability preflight failed",
                    "pipeline_capability_preflight_failed",
                ],
            )
            and has_all(
                pipeline_capability_check,
                [
                    "delegating_agent_in_runtime_stage",
                    "reviewer_stage_must_be_solo",
                    "unknown_agent_without_policy_or_creation_plan",
                ],
            ),
            "Planned pipeline stages must be checked against agent capability policy before runtime execution.",
        ),
        control(
            "architecture",
            "custom_agent_capability_profiles",
            "high",
            has_all(agent_manifest_text, ["default_custom_profile", "custom_profiles", "custom-devops-approved"])
            and has_all(agent_capability_schema, ["default_custom_profile", "custom_profiles"])
            and has_all(pipeline_capability_check, ["capability_profile", "unknown_custom_capability_profile"]),
            "User-owned agents must have safe default and explicit non-default capability profiles enforced by preflight.",
        ),
        control(
            "architecture",
            "runtime_governance_contract",
            "high",
            exists(root, "core/rules/runtime-governance.md")
            and has_all(
                runtime_governance_rule,
                [
                    "pipeline.json",
                    "register.json",
                    "progress.buffer.jsonl",
                    "tool-events.jsonl",
                    "delegation.jsonl",
                    "result.md",
                    "Machine decisions must prefer the structured",
                ],
            ),
            "Runtime governance must identify the authoritative state, trace, delegation, and terminal-output surfaces.",
        ),
        control(
            "performance",
            "slo_fixture_present",
            "high",
            has_all(
                slo_fixture,
                [
                    "status_budget_ms",
                    "telemetry_budget_ms",
                    "memory_search_budget_ms",
                    "update_noop_local_budget_ms",
                    "claude_hook_timeout_budget_seconds",
                ],
            ),
            "Performance budgets must be checked by a fixture, not only by ad hoc observation.",
        ),
        control(
            "performance",
            "claude_performance_budget_probe",
            "high",
            exists(root, "core/scripts/claude-performance-check.py")
            and has_all(
                claude_performance_check,
                ["hook_timeout_seconds", "largest_agent_kb", "agent_crew_kb", "file_count"],
            )
            and has_all(crew_diagnostics, ["claude_performance_probe", "claude performance budgets"]),
            "Claude adapter slowness must be diagnosable by asset-size and hook-timeout budgets.",
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
            "coverage_ownership_contract",
            "high",
            has_all(
                quality_loop_rule,
                [
                    "100% Test Coverage Ownership",
                    "Test-writer",
                    "Implementation agents",
                    "Reviewer",
                    "coverage_below_100",
                    "missing_coverage_evidence",
                ],
            )
            and has_all(
                test_writer,
                [
                    "context/test-coverage.md",
                    "Coverage target: 100% changed-surface coverage",
                    "COVERAGE: 100% changed-surface coverage",
                ],
            )
            and has_all(
                reviewer,
                [
                    "Phase 1.6",
                    "COVERAGE_RESULT",
                    "coverage_exception_unjustified",
                ],
            )
            and has_all(planner, ["100% changed-surface test coverage"])
            and has_all(backend + frontend, ["100% changed executable coverage"]),
            "100% changed-surface coverage must have explicit planner, test-writer, implementer, and reviewer ownership.",
        ),
        control(
            "quality",
            "test_case_checklist_workflow_contract",
            "high",
            has_all(
                test_writer,
                [
                    "requirements analysis -> test checklist derivation -> checklist-only review -> test code generation -> TC-ID mapping verification",
                    "context/test-checklist.md",
                    "context/test-checklist-review.md",
                    "context/test-case-mapping.md",
                    "Do not write test code before checklist review is APPROVED",
                    "TC-ID",
                ],
            )
            and has_all(
                reviewer,
                [
                    "checklist-only review",
                    "Missing MUST",
                    "Low-value Test",
                    "Wrong Priority",
                    "Line coverage is not sufficient",
                    "TEST_CASE_MAPPING_RESULT",
                ],
            )
            and has_all(
                quality_loop_rule,
                [
                    "Test Case Checklist Workflow",
                    "Reviewer APPROVED",
                    "all MUST checklist items are implemented or explicitly explained",
                    "Missing MUST",
                ],
            )
            and "test_test_case_checklist_workflow.py" in "\n".join(
                path.name for path in (root / "tests/python").glob("test_*.py")
            ),
            "Test authoring must derive and review a TC-ID checklist before generating tests, then map every case to implementation coverage.",
        ),
        control(
            "quality",
            "structured_report_gate",
            "medium",
            has_all(answer_quality, ["allowed_blockers", "memory_evidence_trace_path", "require_memory_evidence_trace_when_context_available"]),
            "Reports must include evidence, blocker classification, and memory reuse traceability.",
        ),
        control(
            "quality",
            "operational_quality_metrics",
            "high",
            has_all(
                telemetry_taxonomy_check + read_text(root / "core/scripts/telemetry-aggregate.py"),
                [
                    "operational_quality",
                    "success_rate",
                    "retry_rate",
                    "hallucination_signal_rate",
                    "rollback_frequency",
                    "human_intervention_rate",
                ],
            ),
            "Runtime telemetry must expose required quality metrics as operational rates, not only raw task rows.",
        ),
        control(
            "quality",
            "evaluator_labeled_quality_metrics",
            "high",
            exists(root, "core/schemas/quality-metrics.schema.json")
            and has_all(
                quality_metrics_schema,
                [
                    "hallucination_detected",
                    "rollback_performed",
                    "human_intervention_required",
                    "factuality_review",
                ],
            )
            and has_all(
                read_text(root / "core/scripts/telemetry-aggregate.py"),
                ["read_quality_metrics", "quality_metrics", "explicit_quality_bool"],
            )
            and "quality-metrics.json" in read_text(root / "tests/python/test_telemetry_aggregate.py"),
            "Operational quality metrics must support evaluator-labeled factuality, rollback, and human-intervention signals before text fallbacks.",
        ),
        control(
            "quality",
            "reviewer_quality_metrics_emission_contract",
            "high",
            has_all(
                reviewer,
                [
                    "context/quality-metrics.json",
                    "QUALITY_METRICS:",
                    "hallucination_detected",
                    "factuality_review",
                ],
            )
            and "quality-metrics.schema.json" in read_text(root / "core/scripts/validate-state-schema.py")
            and has_all(
                read_text(root / "core/scripts/reviewer-loop-decision.py"),
                ["QUALITY_METRICS", "quality_metrics_missing", "quality_metrics_file_missing"],
            )
            and "test_invalid_quality_metrics_exits_2" in read_text(root / "tests/python/test_validate_state_schema.py"),
            "Reviewer output, supervisor approval classification, and state validation must enforce evaluator-labeled quality metrics.",
        ),
        control(
            "quality",
            "reviewer_quality_metrics_approval_gate",
            "high",
            has_all(
                read_text(root / "core/scripts/reviewer-loop-decision.py"),
                ["QUALITY_METRICS_RE", "quality_metrics_missing", "quality_metrics_file_missing", "--task-dir"],
            )
            and has_all(
                supervisor_retry,
                ["QUALITY_METRICS:", "quality_metrics_missing", "quality_metrics_file_missing", "--task-dir"],
            )
            and "QUALITY_METRICS: context/quality-metrics.json" in retry_chaos_fixture
            and "test_review_approved_without_quality_metrics_retries_reviewer" in read_text(root / "tests/python/test_reviewer_loop_decision.py"),
            "Reviewer approval must be blocked when evaluator-labeled quality metrics are omitted or point at a missing file.",
        ),
        control(
            "quality",
            "pipeline_quality_metrics_completion_gate",
            "high",
            has_all(
                quality_loop_lib,
                [
                    "QUALITY_METRICS_RE",
                    "event_has_quality_metrics",
                    "missing_reviewer_quality_metrics_artifact",
                    "reviewer_approved_without_quality_metrics_count",
                ],
            )
            and "test_quality_loop_checker_blocks_approval_without_quality_metrics_file" in read_text(root / "tests/python/test_quality_loop_pipeline_check.py")
            and "QUALITY_METRICS: context/quality-metrics.json" in read_text(root / "tests/integration/test_runtime_quality_loop_enforcement.bash"),
            "Completed mutating tasks must not count reviewer approval unless progress evidence points at an existing quality-metrics artifact.",
        ),
        control(
            "quality",
            "pipeline_quality_metrics_schema_gate",
            "high",
            has_all(
                quality_loop_lib,
                [
                    "quality_metrics_schema_errors",
                    "malformed_quality_metrics_json",
                    "invalid_reviewer_quality_metrics_artifact",
                    "unexpected_quality_metrics_fields",
                ],
            )
            and "test_quality_loop_checker_blocks_malformed_quality_metrics_artifact" in read_text(root / "tests/python/test_quality_loop_pipeline_check.py")
            and "test_quality_loop_checker_blocks_schema_invalid_quality_metrics_artifact" in read_text(root / "tests/python/test_quality_loop_pipeline_check.py"),
            "Completed mutating tasks must not count reviewer approval when the referenced quality-metrics artifact is malformed or schema-invalid.",
        ),
        control(
            "reliability",
            "retry_governance",
            "high",
            has_all(supervisor_retry, ["up to **3 retries**", "up to **5 retries**", "cost_budget_exceeded"]),
            "Retries must have explicit budgets and cost breaker behavior.",
        ),
        control(
            "reliability",
            "deterministic_workflow_replay",
            "high",
            exists(root, "core/scripts/workflow-replay-check.py")
            and has_all(workflow_replay_fixture, ["tool_flow", "state_transitions", "expected"])
            and has_all(
                workflow_replay_check,
                [
                    "ALLOWED_TRANSITIONS",
                    "validate-state-schema.py",
                    "pipeline-quality-plan-check.py",
                    "pipeline-capability-check.py",
                ],
            ),
            "Golden workflow replay must pin expected tool flow, failures, and state transitions.",
        ),
        control(
            "reliability",
            "explicit_state_transition_replay_contract",
            "high",
            has_all(runtime_governance_rule, ["finite state machine", "Unknown states are a governance failure"])
            and has_all(register_rule, ["current_phase", "approval_status", "verification_status", "blocked_by"])
            and has_all(workflow_replay_check, ["ALLOWED_TRANSITIONS", "invalid_transition", "non_terminal_final_state"]),
            "Workflow states must be explicit enough for replay to reject unknown, invalid, or non-terminal transitions.",
        ),
        control(
            "reliability",
            "retry_chaos_recovery",
            "high",
            exists(root, "core/scripts/retry-chaos-check.py")
            and has_all(retry_chaos_fixture, ["max_crash_retries", "max_validation_retries", "max_token_truncation_resumes"])
            and has_all(
                retry_chaos_check,
                [
                    "reviewer-loop-decision.py",
                    "token_truncation",
                    "agent_crashed_after_retry_budget",
                    "quality_loop_exhausted",
                ],
            ),
            "Retry chaos tests must simulate crash, token truncation, reviewer loop-back, and host-blocked recovery.",
        ),
        control(
            "reliability",
            "no_bridge_handoff_ready_fallback",
            "high",
            has_all(crew_runtime, ["handoff_ready", "internal_handoff_ready", "no external bridge command is required"])
            and has_all(crew_cli_test, ["crew run writes deterministic state then exits handoff_ready", "tasks_running"])
            and has_all(crew_diagnostics, ["internal handoff fallback available", "host bridge command readiness"]),
            "Missing external host bridge configuration must produce resumable handoff state, not a failed/stalled run.",
        ),
        control(
            "reliability",
            "input_normalization_gate_all_entrypoints",
            "high",
            has_all(crew_runtime, ["detect_source_language", "input_normalization_task", "input_normalization_handoff"])
            and has_all(
                crew_cli_test,
                [
                    "crew run routes Korean task text through input-normalizer gate",
                    "crew run routes non-English multilingual input through input-normalizer gate",
                    "crew run routes ambiguous conversational input through input-normalizer gate",
                    "crew agent keeps intended agent for Korean inline normalization",
                ],
            ),
            "Non-English or ambiguous task input must be normalized before every crew run or direct-agent downstream handoff.",
        ),
        control(
            "reliability",
            "issue_comment_ingestion_before_planning",
            "high",
            has_all(crew, ["issue-ingest ISSUE", "cmd_issue_ingest"])
            and has_all(
                crew_runtime,
                [
                    "command_issue_ingest",
                    "record_issue_ingestion_evidence",
                    "detect_issue_references",
                    "comments_ingested",
                    "comment_derived_requirements",
                ],
            )
            and has_all(
                crew_cli_test,
                [
                    "crew issue-ingest records issue body and comments before planning",
                    "crew run automatically ingests referenced issue comments before planning",
                    "comments_ingested",
                ],
            ),
            "Issue-solving workflows must automatically record issue body/comment ingestion evidence before planning.",
        ),
        control(
            "reliability",
            "context_compression_pageout",
            "high",
            has_all(
                supervisor,
                [
                    "Do not keep file contents inline in context",
                    "Immediately compact when context usage reaches 60%",
                    "Token-Limit Recovery Rule",
                ],
            )
            and has_all(supervisor, ["HANDOFF_PAGEOUT", "HANDOFF_PAGEDOUT"])
            and has_all(supervisor_stages, ["AGENT_CREW_HANDOFF_PAGEOUT_THRESHOLD", "archive/handoff"])
            and has_all(runtime_governance_rule, ["Context Compression", "archived handoff files"]),
            "Supervisors must page out large context and preserve replay coordinates instead of carrying inline file contents.",
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
            "memory_governance",
            "memory_gc_eviction_command",
            "high",
            exists(root, "core/scripts/memory-gc.py")
            and has_all(memory_gc, ["capture -> classify -> summarize -> score -> archive -> evict", "evicted-ids.txt"])
            and has_all(memory_wrapper, ["memory-gc.py", "AGENT_CREW_MEMORY_GC_EVICTED"]),
            "Memory lifecycle must be operationalized by a dry-run-first GC and retrieval eviction command.",
        ),
        control(
            "memory_governance",
            "retrieval_scoring_contract",
            "high",
            has_all(memory_rule, ["relevance", "recency", "trust", "task", "similarity"])
            and has_all(memory_gc, ["trust_score", "score", "duplicate", "low_score"])
            and has_all(memory_fixture, ["accepted_successor_memory_ids", "noise_budget_count", "latency_budget_ms"])
            and has_all(runtime_governance_rule, ["Retrieval Scoring", "recall", "precision", "freshness", "performance"]),
            "Retrieval must score by relevance/recency/trust/task similarity and test recall, precision, freshness, and latency budgets.",
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
            "security",
            "tool_sandboxing_contract",
            "high",
            exists(root, "core/rules/tool-sandboxing.md")
            and has_all(
                tool_sandboxing_rule,
                [
                    "Capability manifest",
                    "Pipeline preflight",
                    "Direct-edit guard",
                    "Dangerous-command guard",
                    "Forbidden-command guard",
                    "Command-Bound Approval",
                    "does not claim to provide an operating-system sandbox",
                ],
            )
            and has_all(agent_manifest_text, ["allowed_capabilities", "denied_capabilities", "destructive_requires_approval"])
            and has_all(guard, ["audit(event)", "approval_command_mismatch", "FORBIDDEN_PATTERNS"]),
            "Tool sandboxing must be explicit about workflow policy layers, command-bound approval, and the host/OS boundary.",
        ),
        control(
            "security",
            "prompt_injection_defense",
            "high",
            has_all(
                prompt_injection_rule,
                [
                    "untrusted data",
                    "must not execute instructions",
                    "Validate every tool request",
                    "Trust Order",
                ],
            ),
            "Retrieved and external context must be isolated from executable instructions.",
        ),
        control(
            "security",
            "prompt_injection_runtime_boundary",
            "high",
            has_all(runtime_governance_rule, ["External content", "retrieved memory", "tool output", "untrusted data"])
            and has_all(prompt_injection_rule, ["Trust Order", "untrusted data", "must not execute instructions"])
            and has_all(auto_issue_reporter, ["redact", "compact_text", "SECRET_PATTERNS"]),
            "Runtime issue text, memory, and external content must remain non-executable and redacted when reported.",
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
            "observability",
            "structured_output_traceability",
            "high",
            has_all(
                progress_buffer_rule,
                ["trace_id", "tool-events.jsonl", "delegation.jsonl", "Consumer Contract", "Schema validator"]
            )
            and has_all(runtime_governance_rule, ["Structured Outputs", "STATUS:", "PLAN:", "REVIEW:", "JSONL"])
            and has_all(supervisor_bootstrap, ["progress.buffer.jsonl", "json.dumps", "trace_id"]),
            "Runtime outputs that drive status, approvals, review, and telemetry must be structured and trace-correlated.",
        ),
        control(
            "observability",
            "telemetry_retry_taxonomy_correlation",
            "high",
            exists(root, "core/scripts/telemetry-taxonomy-check.py")
            and has_all(
                telemetry_taxonomy_check,
                ["retry-chaos.json", "progress.buffer.jsonl", "unknown_labels", "require-label"],
            ),
            "Live retry/blocker telemetry must correlate with the retry-chaos failure taxonomy.",
        ),
        control(
            "observability",
            "automatic_issue_reporting_surface",
            "high",
            exists(root, "core/scripts/auto-issue-reporter.py")
            and exists(root, "core/hooks/auto-issue-report.sh")
            and has_all(crew, ["report auto|publish", "cmd_report()", "auto-issue-reporter.py"])
            and has_all(auto_issue_hook, ["crew", "report", "auto"]),
            "Native automatic issue reporting must be reachable from hooks and the crew CLI.",
        ),
        control(
            "observability",
            "automatic_issue_reporting_governance",
            "high",
            has_all(
                auto_issue_reporter,
                [
                    "write_outbox",
                    "duplicate_record",
                    "redact",
                    "remote_duplicate",
                    "return 0",
                    "supervisor_blocked",
                    "PostToolUse:Bash",
                    "has_infrastructure_failure_signal",
                ],
            )
            and has_all(
                auto_issue_rule,
                [
                    "Native Report Outbox",
                    "Local deduplication",
                    "Remote deduplication",
                    "Secret redaction",
                    "Advisory failure mode",
                ],
            ),
            "Automatic issue reporting must preserve local reports, dedupe, redact secrets, detect infrastructure blockers, and never block workflow execution.",
        ),
        control(
            "observability",
            "automatic_issue_reporting_runtime_issue_contract",
            "high",
            has_all(runtime_governance_rule, ["Automatic Issue Reporting", "Unexpected runtime infrastructure blockers"])
            and has_all(auto_issue_reporter, ["supervisor_blocked", "STRUCTURED_BLOCKED_RE", "INFRASTRUCTURE_FAILURE_RE"])
            and has_all(auto_issue_rule, ["infrastructure blocker", "must not block", "outbox"]),
            "Runtime infrastructure blockers must be reportable without fabricating publication success or blocking execution.",
        ),
        control(
            "observability",
            "automatic_issue_reporting_regression_tests",
            "medium",
            has_all(
                auto_issue_test,
                [
                    "records agent-crew error prompts locally",
                    "redacts secrets in native outbox",
                    "skips duplicate prompt reports locally",
                    "handles Bash tool failures involving crew",
                    "records structured infrastructure blockers from Bash crew output",
                    "ignores normal host bridge blocked handoffs",
                    "ignores resumable internal handoff-ready runs",
                    "recognizes hook and missing-asset supervisor blockers",
                    "auto issue hook wrapper is advisory",
                ],
            ),
            "Automatic issue reporting must have regression coverage for real hook surfaces and non-blocking behavior.",
        ),
        control(
            "observability",
            "automatic_issue_reporting_runtime_smoke",
            "high",
            has_all(
                crew_diagnostics,
                [
                    "auto_issue_reporting_probe",
                    "auto-issue-report.sh",
                    "UserPromptSubmit",
                    "hook smoke created native report and outbox record",
                ],
            ),
            "Runtime diagnostics must exercise the real hook-facing automatic issue reporting path.",
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
            "cost_efficiency",
            "cost_aware_role_tiers",
            "medium",
            {"xhigh", "high", "medium", "cheap"}.issubset(model_tiers)
            and '"model_tier": "xhigh"' in agent_manifest_text
            and '"model_tier": "high"' in agent_manifest_text
            and '"model_tier": "medium"' in agent_manifest_text
            and '"model_tier": "cheap"' in agent_manifest_text,
            "Role routing must avoid assigning the highest-tier model to every agent.",
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
