"""Tests for the Progressive Agent Learning Loop.

These tests prove the rule contract laid out in
`core/rules/progressive-learning.md`:

- The learning-candidate schema exists, is valid JSON Schema 2020-12, and
  enforces its required fields and enums.
- Memory candidates are advisory only — the `trust_boundary` field is fixed.
- Recalled candidates cannot bypass TDD, the reviewer stage, or the
  quality-loop gates (verified by content-pattern checks against the rule
  document and the agent prompts that consume the candidates).
- The context-break spacing convention is used as the concrete worked-example
  fixture.

These are file-based / schema-based assertions; they do not depend on a
running service.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULE_PATH = REPO_ROOT / "core" / "rules" / "progressive-learning.md"
SCHEMA_PATH = REPO_ROOT / "core" / "schemas" / "learning-candidate.schema.json"
ANALYST_PATH = REPO_ROOT / "core" / "agents" / "analyst.md"
PLANNER_PATH = REPO_ROOT / "core" / "agents" / "planner.md"
MEMORY_GOV_PATH = REPO_ROOT / "core" / "rules" / "memory-governance.md"


# ---------------------------------------------------------------------------
# Rule + schema artifacts exist
# ---------------------------------------------------------------------------


def test_rule_file_exists():
    assert RULE_PATH.is_file(), f"missing rule file: {RULE_PATH}"


def test_schema_file_exists():
    assert SCHEMA_PATH.is_file(), f"missing schema file: {SCHEMA_PATH}"


def test_schema_is_valid_json_schema_2020_12():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    # jsonschema validator construction surfaces structural errors immediately
    validator = jsonschema.Draft202012Validator(schema)
    validator.check_schema(schema)


# ---------------------------------------------------------------------------
# Schema contract: required fields, enums, and the trust_boundary literal
# ---------------------------------------------------------------------------


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _valid_candidate() -> dict:
    return {
        "schema_version": 1,
        "candidate_id": "ctx-break-spacing-2026-06",
        "source": "reviewer_finding",
        "memory_layer": "project",
        # Finding [7]: progressive-learning.md no longer cites brittle
        # line numbers; the example fixture mirrors the rule's
        # section-heading anchor form.
        "evidence_refs": [
            "core/agents/backend.md#code-style-context-breaks",
            "core/agents/frontend.md#code-style-context-breaks",
        ],
        "promotion_reason": (
            "Context-break spacing was flagged by reviewer on two independent "
            "runs and the diff was approved both times after the fix."
        ),
        "trust_boundary": "advisory_until_rule_promotion",
    }


def test_schema_accepts_well_formed_candidate():
    jsonschema.validate(instance=_valid_candidate(), schema=_load_schema())


def test_schema_rejects_missing_required_fields():
    schema = _load_schema()

    for missing in (
        "schema_version",
        "candidate_id",
        "source",
        "memory_layer",
        "evidence_refs",
        "promotion_reason",
        "trust_boundary",
    ):
        candidate = _valid_candidate()
        candidate.pop(missing)

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=candidate, schema=schema)


def test_schema_rejects_unknown_source():
    candidate = _valid_candidate()
    candidate["source"] = "rumor"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=candidate, schema=_load_schema())


def test_schema_rejects_unknown_memory_layer():
    candidate = _valid_candidate()
    candidate["memory_layer"] = "global"  # global is reserved for promoted entries

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=candidate, schema=_load_schema())


def test_schema_accepts_three_documented_layers():
    schema = _load_schema()

    for layer in ("session", "project", "global_candidate"):
        candidate = _valid_candidate()
        candidate["memory_layer"] = layer
        jsonschema.validate(instance=candidate, schema=schema)


def test_schema_rejects_empty_evidence_refs():
    candidate = _valid_candidate()
    candidate["evidence_refs"] = []

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=candidate, schema=_load_schema())


def test_trust_boundary_is_machine_enforced_literal():
    """The trust_boundary field cannot be relaxed to a softer string.

    This is the schema-level encoding of the rule that memory candidates are
    advisory only.
    """
    candidate = _valid_candidate()
    candidate["trust_boundary"] = "ground_truth"  # attempted policy elevation

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=candidate, schema=_load_schema())

    # And the documented literal must be accepted.
    candidate["trust_boundary"] = "advisory_until_rule_promotion"
    jsonschema.validate(instance=candidate, schema=_load_schema())


# ---------------------------------------------------------------------------
# Rule contract: the loop, maturity levels, and guardrails are documented
# ---------------------------------------------------------------------------


def _rule_text() -> str:
    return RULE_PATH.read_text(encoding="utf-8")


def test_rule_documents_the_full_loop():
    text = _rule_text()

    # The canonical loop order — appears as a code block in the rule.
    assert "work -> review -> capture -> summarize/promote -> recall -> apply -> verify" in text


def test_rule_documents_three_maturity_levels():
    text = _rule_text()

    for header in ("### session", "### project", "### global"):
        assert header in text, f"missing maturity-level section: {header}"


def test_rule_references_issue_129_aar_foundation():
    text = _rule_text()

    assert "issue #129" in text, "rule must reference issue #129 (AAR foundation)"


def test_rule_states_guardrails_explicitly():
    text = _rule_text()

    # The rule contains a Guardrails section with the load-bearing claims.
    assert "## Guardrails" in text

    required_claims = [
        "Memory is not ground truth",
        "Memory cannot override managed rules",
        "Memory cannot skip TDD",
        "Memory cannot skip the reviewer stage",
        "Memory cannot skip the quality loop",
        "Clean runs produce no noisy learning records",
        "Repeated patterns need evidence before promotion",
    ]
    for claim in required_claims:
        assert claim in text, f"rule must state guardrail verbatim: {claim!r}"


def test_rule_uses_context_break_spacing_as_worked_example():
    text = _rule_text()

    assert "## Worked Example: Context-Break Spacing" in text
    # The example cites at least one of the existing managed-rule locations.
    assert "core/agents/backend.md" in text
    assert "core/agents/frontend.md" in text


def test_rule_documents_memory_usage_tracing_format():
    text = _rule_text()

    assert "## Memory-Usage Tracing" in text
    assert "memory-usage.json" in text
    assert "memory-evidence.json" in text
    for field in (
        "decisions",
        "disposition",
        "applications",
        "retrieved_ids",
        "accepted_ids",
        "ignored_ids",
        "superseded_by",
        "applied_at",
        "outcome",
    ):
        assert field in text, f"memory-evidence trace must document field: {field}"


# ---------------------------------------------------------------------------
# Cross-file: analyst and planner consume candidates as advisory hints only
# ---------------------------------------------------------------------------


def test_analyst_documents_progressive_learning_recall():
    text = ANALYST_PATH.read_text(encoding="utf-8")

    assert "Progressive Learning" in text
    assert "advisory" in text.lower()
    assert "memory-usage.json" in text
    assert "memory-feedback.py" in text
    # Pointer back to the rule must exist so the contract is discoverable.
    assert "core/rules/progressive-learning.md" in text


def test_planner_documents_progressive_learning_recall():
    text = PLANNER_PATH.read_text(encoding="utf-8")

    assert "Progressive Learning" in text
    assert "advisory" in text.lower()
    assert "memory-usage.json" in text
    assert "core/rules/progressive-learning.md" in text


def _extract_progressive_learning_section(text: str) -> str:
    """Return the body of the `Progressive Learning` subsection only."""
    pattern = re.compile(
        r"### Progressive Learning.*?(?=\n##\s|\n### |\Z)",
        re.DOTALL,
    )
    match = pattern.search(text)
    assert match, "Progressive Learning section not found"
    return match.group(0)


def test_analyst_and_planner_forbid_dropping_reviewer_or_tdd():
    """Both consumer prompts must explicitly forbid relaxing the gates."""
    for path in (ANALYST_PATH, PLANNER_PATH):
        text = path.read_text(encoding="utf-8")
        section = _extract_progressive_learning_section(text)

        # Markdown wrapping may split phrases like "quality loop" across a
        # line break; collapse whitespace before searching for bigrams.
        collapsed = re.sub(r"\s+", " ", section)

        # Both files must say candidates cannot drop the reviewer.
        assert "reviewer" in collapsed.lower(), (
            f"{path.name} must mention reviewer in the progressive-learning section"
        )
        # Both must say candidates cannot bypass TDD.
        assert "TDD" in collapsed, (
            f"{path.name} must mention TDD in the progressive-learning section"
        )
        # Both must say candidates cannot shorten the quality loop.
        assert "quality loop" in collapsed.lower(), (
            f"{path.name} must mention quality loop in the progressive-learning section"
        )


# ---------------------------------------------------------------------------
# Cross-file: the loop ties back to memory-governance.md (existing rule)
# ---------------------------------------------------------------------------


def test_rule_cross_references_memory_governance():
    text = _rule_text()

    assert "memory-governance.md" in text


def test_memory_governance_aar_section_still_present():
    """The AAR foundation that this loop builds on must still exist."""
    text = MEMORY_GOV_PATH.read_text(encoding="utf-8")

    assert "## After-Action Review (AAR) Memo" in text
