"""Regression coverage for bounded exhaustive caller graph guidance."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

EVIDENCE_RULE = REPO_ROOT / "core" / "rules" / "evidence-grounded-reasoning.md"
CODE_INTELLIGENCE = REPO_ROOT / "core" / "rules" / "code-intelligence-evidence.md"
SCOPE_BOUNDARY = REPO_ROOT / "core" / "agents" / "skills" / "scope-boundary-control.md"
CONTRACT_PARITY = REPO_ROOT / "core" / "agents" / "skills" / "contract-parity-checking.md"
CONTRACT_FIRST = REPO_ROOT / "core" / "rules" / "contract-first-feedback-fidelity.md"
PARITY_CHECK_COMMAND = REPO_ROOT / "core" / "user" / "commands" / "parity-check.md"
PARITY_IMPLEMENT_COMMAND = REPO_ROOT / "core" / "user" / "commands" / "parity-implement.md"
REVIEW_SYNTHESIS_COMMAND = REPO_ROOT / "core" / "user" / "commands" / "review-synthesis.md"
REVIEW_FOLLOWUP = REPO_ROOT / "core" / "agents" / "skills" / "review-followup-discipline.md"
CODE_REVIEW = REPO_ROOT / "core" / "agents" / "skills" / "code-review.md"
DEAD_CODE = REPO_ROOT / "core" / "agents" / "skills" / "dead-code-elimination.md"
VERIFICATION = REPO_ROOT / "core" / "agents" / "skills" / "verification-before-claim.md"
DEBUGGING = REPO_ROOT / "core" / "agents" / "skills" / "systematic-debugging.md"
COMPLETION_REPORT = REPO_ROOT / "core" / "rules" / "completion-report.md"

PROJECT_SPECIFIC_TOKENS = (
    "ENRTC",
    "CMS",
    "CNAS",
    "Danawa",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def compact(path: Path) -> str:
    return " ".join(read(path).split())


def test_evidence_rule_defines_bounded_exhaustive_caller_graph_claims() -> None:
    text = compact(EVIDENCE_RULE)

    for required in (
        "Exhaustive Caller Graph Discipline",
        "bounded exhaustive strategy",
        "Exhaustive within scope",
        "Partial caller graph",
        "No references found",
        "Unknown",
        "Do not equate a single-file inspection",
    ):
        assert required in text


def test_evidence_rule_defines_hybrid_traversal_strategy() -> None:
    text = compact(EVIDENCE_RULE)

    for required in (
        "bounded bidirectional worklist traversal",
        "BFS inventory",
        "selective DFS deep dive",
        "Start with BFS",
        "Use DFS only for risk-bearing paths",
        "caller and callee directions",
        "producer and consumer paths",
    ):
        assert required in text


def test_bfs_inventory_expands_through_approved_boundary() -> None:
    text = compact(EVIDENCE_RULE)

    assert "first reachable layer" not in text

    for required in (
        "BFS inventory expands breadth-first through the approved boundary",
        "direct callers",
        "in-scope indirect callers",
        "until the approved boundary is reached",
        "partial or `Unknown`",
        "selective DFS deep dive",
        "risk-bearing paths",
    ):
        assert required in text


def test_code_intelligence_requires_graph_inventory_before_shared_code_edits() -> None:
    text = compact(CODE_INTELLIGENCE)

    for required in (
        "caller_graph",
        "entrypoints",
        "direct_callers",
        "indirect_callers",
        "callees",
        "consumers",
        "producers",
        "configuration_or_registration_paths",
        "shared module",
        "public API",
    ):
        assert required in text


def test_code_intelligence_can_record_no_references_found_without_unused_claim() -> None:
    text = compact(CODE_INTELLIGENCE)

    for required in (
        "no_references_found",
        "No references found",
        "stated search or semantic-reference method found no references",
        "does not prove the behavior is unused outside the declared search scope",
    ):
        assert required in text


def test_code_intelligence_documents_hybrid_traversal_without_forcing_one_algorithm() -> None:
    text = compact(CODE_INTELLIGENCE)

    for required in (
        "bounded bidirectional worklist traversal",
        "BFS inventory",
        "selective DFS deep dive",
        "DFS-only",
        "BFS-only",
        "Do not force",
    ):
        assert required in text


def test_scope_boundary_links_cross_boundary_work_to_caller_graph() -> None:
    text = compact(SCOPE_BOUNDARY)

    for required in (
        "Before crossing or changing a boundary",
        "trace the bounded caller graph",
        "entrypoints",
        "scheduled jobs",
        "external consumers",
        "configuration wiring",
        "partial graph",
    ):
        assert required in text


def test_contract_parity_requires_reachable_caller_graph_before_parity_claim() -> None:
    text = compact(CONTRACT_PARITY)

    for required in (
        "Exhaustive caller graph within the approved parity scope",
        "Do not claim parity from matching names",
        "consumer-visible entrypoint",
        "producer state",
        "UNKNOWN",
    ):
        assert required in text


def test_parity_guidance_uses_bfs_then_dfs_for_contract_risks() -> None:
    text = compact(CONTRACT_PARITY)

    for required in (
        "Use BFS inventory",
        "selective DFS deep dive",
        "consumer-visible entrypoint",
        "producer state",
        "contract-risk path",
    ):
        assert required in text


def test_contract_first_snippets_apply_graph_strategy_to_prompt_and_review_rate() -> None:
    text = compact(CONTRACT_FIRST)

    for required in (
        "$prompt",
        "$mr-review-rate",
        "caller graph",
        "BFS inventory",
        "selective DFS",
        "contract-safe",
        "side-effect-safe",
    ):
        assert required in text


def test_parity_user_commands_apply_hybrid_graph_strategy() -> None:
    combined = compact(PARITY_CHECK_COMMAND) + " " + compact(PARITY_IMPLEMENT_COMMAND)

    for required in (
        "BFS inventory",
        "selective DFS deep dive",
        "bounded bidirectional",
        "No references found",
        "TARGET_DISCOVERY",
        "DEPENDENCY_GRAPH",
    ):
        assert required in combined


def test_review_synthesis_preserves_graph_coverage_from_lenses() -> None:
    text = compact(REVIEW_SYNTHESIS_COMMAND)

    for required in (
        "caller graph",
        "graph coverage",
        "No references found",
        "unknown",
        "lens",
    ):
        assert required in text


def test_review_followup_and_code_review_require_graph_status_for_risky_claims() -> None:
    combined = compact(REVIEW_FOLLOWUP) + " " + compact(CODE_REVIEW)

    for required in (
        "caller graph",
        "BFS inventory",
        "selective DFS",
        "contract-safe",
        "side-effect-safe",
        "review item",
    ):
        assert required in combined


def test_dead_code_verification_debugging_and_completion_use_graph_status() -> None:
    combined = (
        compact(DEAD_CODE)
        + " "
        + compact(VERIFICATION)
        + " "
        + compact(DEBUGGING)
        + " "
        + compact(COMPLETION_REPORT)
    )

    for required in (
        "caller graph",
        "No references found",
        "unused",
        "BFS",
        "DFS",
        "completion",
    ):
        assert required in combined


def test_exhaustive_caller_graph_guidance_is_project_agnostic() -> None:
    combined = "\n".join(
        [
            read(EVIDENCE_RULE),
            read(CODE_INTELLIGENCE),
            read(SCOPE_BOUNDARY),
            read(CONTRACT_PARITY),
            read(CONTRACT_FIRST),
            read(PARITY_CHECK_COMMAND),
            read(PARITY_IMPLEMENT_COMMAND),
            read(REVIEW_SYNTHESIS_COMMAND),
            read(REVIEW_FOLLOWUP),
            read(CODE_REVIEW),
            read(DEAD_CODE),
            read(VERIFICATION),
            read(DEBUGGING),
            read(COMPLETION_REPORT),
        ]
    )

    for token in PROJECT_SPECIFIC_TOKENS:
        assert token not in combined
