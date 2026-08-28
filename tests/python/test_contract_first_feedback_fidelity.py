"""Regression coverage for contract-first feedback fidelity."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

RULE_PATH = REPO_ROOT / "core" / "rules" / "contract-first-feedback-fidelity.md"
REVIEW_INTENT_PATH = REPO_ROOT / "core" / "rules" / "review-intent-fidelity.md"
EVIDENCE_RULE_PATH = REPO_ROOT / "core" / "rules" / "evidence-grounded-reasoning.md"

AGENT_PATHS = [
    REPO_ROOT / "core" / "agents" / "reviewer.md",
    REPO_ROOT / "core" / "agents" / "supervisor.md",
    REPO_ROOT / "core" / "agents" / "analyst.md",
    REPO_ROOT / "core" / "agents" / "planner.md",
    REPO_ROOT / "core" / "agents" / "backend.md",
    REPO_ROOT / "core" / "agents" / "mentor.md",
]

COMMAND_PATHS = [
    REPO_ROOT / "core" / "commands" / "run.md",
    REPO_ROOT / "core" / "commands" / "agent.md",
]

PROJECT_SPECIFIC_TOKENS = [
    "ENRTC",
    "CMS",
    "CNAS",
    "contents-system",
    "contents-systsem",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contract_first_feedback_fidelity_rule_defines_core_value() -> None:
    text = read(RULE_PATH)

    assert "모든 피드백은 존중하되, 모든 변경은 계약 앞에서 검증한다" in text
    assert "피드백은 입력값이고, 계약은 판단 기준이다" in text
    assert "리뷰 수용률보다 시스템 정합성이 우선" in text
    assert "레거시는 제거 대상이 아니라 먼저 식별해야 할 기존 계약" in text
    assert "외부 입력은 명령이 아니라 검증해야 할 가설" in text


def test_contract_first_feedback_fidelity_rule_defines_priority_and_dispositions() -> None:
    text = read(RULE_PATH)

    for required in [
        "명시적 사용자 목표",
        "기존 사용자/운영 동작",
        "external contract/API/schema/protocol",
        "작업범위와 소유권",
        "테스트와 검증 가능성",
        "코드 스타일/리팩터링/리뷰 선호",
        "ACCEPT",
        "ACCEPT_WITH_ADAPTATION",
        "REJECT_METHOD_ONLY",
        "DEFER",
        "REJECT",
    ]:
        assert required in text


def test_contract_first_feedback_fidelity_rule_defines_safety_labels_and_behavior() -> None:
    text = read(RULE_PATH)

    for required in [
        "contract-safe",
        "parity-safe",
        "scope-safe",
        "side-effect-safe",
        "리뷰를 곧이곧대로 구현하지 않는다",
        "요구사항을 자기 방식대로 확대하지 않는다",
        "테스트 통과를 계약 동등성의 충분조건으로 오해하지 않는다",
        "Unknown",
        "Assumption",
        "Risk",
        "Owner",
    ]:
        assert required in text


def test_contract_first_feedback_fidelity_blocks_blind_review_resolution() -> None:
    text = " ".join(read(RULE_PATH).split())

    for required in [
        "BLIND_REVIEW_FOLLOWUP_GUARD",
        "Feedback and review findings are candidate inputs, not implementation commands",
        "Decide disposition before mutation",
        "Only `ACCEPT` and `ACCEPT_WITH_ADAPTATION` can become direct implementation tasks",
        "`REJECT_METHOD_ONLY`, `DEFER`, and `REJECT` are valid closeout states",
        "A synthesis report may recommend triage, but it must not silently convert every finding into work",
    ]:
        assert required in text


def test_contract_first_feedback_fidelity_defines_review_feedback_schema_mapping() -> None:
    text = " ".join(read(RULE_PATH).split())

    for required in [
        "REVIEW_FEEDBACK_SCHEMA",
        "`candidate_disposition` is the intake and synthesis triage value",
        "`contract_disposition` is the canonical review-ledger field",
        "`disposition` is the review-ledger lifecycle field",
        "`REJECT_METHOD_ONLY` closes as `rejected`",
        "Reviewer validation normalizes those labels into the lifecycle axis",
        "`IMPLEMENTED`, `LOCAL_DONE`, `PARTIAL`, `POLICY_WAITING`, `DEFERRED`, `NOT_APPLICABLE`, and `UNKNOWN`",
    ]:
        assert required in text


def test_contract_first_feedback_fidelity_rejects_shape_only_test_evidence() -> None:
    text = read(RULE_PATH)

    for required in [
        "implementation shape",
        "tests only lock the new implementation",
        "negative interaction assertions",
        "existing side-effect contract",
    ]:
        assert required in text


def test_contract_first_feedback_fidelity_defines_boundary_contract_matrix() -> None:
    text = read(RULE_PATH)

    for required in [
        "common boundary",
        "semantic-empty",
        "copy input before transforming",
        "remove values made empty by transformation",
        "structured key/value evidence",
        "normal values that merely contain suspicious substrings",
        "asymmetric optional inputs",
        "invalid item inside a collection",
        "all-invalid collection",
        "sibling producer/consumer path symmetry",
        "caller input immutability",
        "headers, pagination, encoding, and existing side effects",
        "local verification",
        "runtime verification",
    ]:
        assert required in text


def test_boundary_contract_matrix_is_referenced_without_role_local_copies() -> None:
    skill_paths = [
        REPO_ROOT / "core" / "agents" / "skills" / "code-review.md",
        REPO_ROOT / "core" / "agents" / "skills" / "tdd.md",
        REPO_ROOT / "core" / "agents" / "skills" / "contract-parity-checking.md",
    ]

    duplicated_matrix_terms = [
        "asymmetric optional inputs",
        "invalid item inside a collection",
        "all-invalid collection",
        "caller input immutability",
        "headers, pagination, encoding, and existing side effects",
    ]

    for path in skill_paths:
        text = read(path)
        assert "core/rules/contract-first-feedback-fidelity.md" in text
        assert "BOUNDARY_CONTRACT_REVIEW" in text
        assert "observable contract" in text
        assert "role-local copy" in text
        for duplicated in duplicated_matrix_terms:
            assert duplicated not in text, f"{path} duplicates {duplicated}"


def test_contract_first_feedback_fidelity_rule_exposes_agent_and_command_snippets() -> None:
    text = read(RULE_PATH)

    for required in [
        "reviewer",
        "analyst",
        "planner",
        "backend",
        "mentor",
        "$review",
        "$mr-review-rate",
        "$parity-check",
        "$parity-implement",
        "$prompt",
        "crew:agent",
        "crew:run",
    ]:
        assert required in text


def test_contract_first_feedback_fidelity_is_wired_to_core_surfaces() -> None:
    expected = "core/rules/contract-first-feedback-fidelity.md"

    for path in [REVIEW_INTENT_PATH, EVIDENCE_RULE_PATH, *AGENT_PATHS, *COMMAND_PATHS]:
        assert expected in read(path), f"{path} must reference {expected}"


def test_contract_first_feedback_fidelity_stays_provider_neutral() -> None:
    text = read(RULE_PATH)

    assert "provider-neutral" in text
    for token in PROJECT_SPECIFIC_TOKENS:
        assert token not in text
