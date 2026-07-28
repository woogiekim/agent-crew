"""Regression coverage for Review Intent Fidelity."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

RULE_PATH = REPO_ROOT / "core" / "rules" / "review-intent-fidelity.md"
REVIEWER_PATH = REPO_ROOT / "core" / "agents" / "reviewer.md"
SUPERVISOR_PATH = REPO_ROOT / "core" / "agents" / "supervisor.md"
COMPLETION_PATH = REPO_ROOT / "core" / "rules" / "completion-report.md"
QUALITY_LOOP_PATH = REPO_ROOT / "core" / "rules" / "quality-loop.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_review_intent_fidelity_rule_defines_provider_neutral_ledger() -> None:
    text = read(RULE_PATH)

    assert "Provider-neutral" in text or "provider-neutral" in text
    assert "core/rules/evidence-grounded-reasoning.md" in text
    assert "{TASK_DIR}/context/review-ledger.json" in text
    assert "{TASK_DIR}/context/review-ledger.md" in text
    assert "implemented" in text
    assert "deferred" in text
    assert "rejected" in text
    assert "not-applicable" in text
    assert "semantic_verification" in text
    assert "state, value, side effect, or behavior" in text


def test_reviewer_requires_review_original_to_disposition_ledger() -> None:
    text = read(REVIEWER_PATH)
    compact = " ".join(text.split())

    assert "core/rules/review-intent-fidelity.md" in text
    assert "{TASK_DIR}/context/review-ledger.json" in text
    assert "{TASK_DIR}/context/review-ledger.md" in text
    assert "reviewer's intended meaning" in compact
    assert "REVIEW: NEEDS_CHANGES" in text
    assert "proves only call existence" in text


def test_supervisor_and_closeout_wire_review_intent_gate() -> None:
    supervisor = read(SUPERVISOR_PATH)
    completion = read(COMPLETION_PATH)
    quality_loop = read(QUALITY_LOOP_PATH)

    for text in (supervisor, completion, quality_loop):
        assert "core/rules/review-intent-fidelity.md" in text
        assert "review-ledger" in text

    assert "review-original-to-disposition ledger" in supervisor
    assert "may only claim" in completion
    assert "Invalid review-ledger entries" in quality_loop
