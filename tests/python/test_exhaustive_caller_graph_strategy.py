"""Regression coverage for bounded exhaustive caller graph guidance."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

EVIDENCE_RULE = REPO_ROOT / "core" / "rules" / "evidence-grounded-reasoning.md"
CODE_INTELLIGENCE = REPO_ROOT / "core" / "rules" / "code-intelligence-evidence.md"
SCOPE_BOUNDARY = REPO_ROOT / "core" / "agents" / "skills" / "scope-boundary-control.md"
CONTRACT_PARITY = REPO_ROOT / "core" / "agents" / "skills" / "contract-parity-checking.md"

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


def test_exhaustive_caller_graph_guidance_is_project_agnostic() -> None:
    combined = "\n".join(
        [
            read(EVIDENCE_RULE),
            read(CODE_INTELLIGENCE),
            read(SCOPE_BOUNDARY),
            read(CONTRACT_PARITY),
        ]
    )

    for token in PROJECT_SPECIFIC_TOKENS:
        assert token not in combined
