"""Contract tests for PRD acceptance-criteria ownership guidance."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_prd_authoring_templates_use_stable_ac_ids():
    """success-case(contract) - PRD-producing guidance emits stable AC IDs."""
    # given
    pipeline_planning = _read("core/agents/skills/pipeline-planning.md")
    requirement_gathering = _read("core/agents/skills/requirement-gathering.md")

    # when
    pipeline_has_ac_id = bool(re.search(r"-\s+AC-001:\s+Given\b", pipeline_planning))
    requirements_has_ac_id = bool(re.search(r"-\s+AC-001:\s+Given\b", requirement_gathering))

    # then
    assert pipeline_has_ac_id
    assert requirements_has_ac_id
    assert "At least one `AC-*` acceptance criterion per must-have story" in requirement_gathering


def test_pipeline_schema_documents_stage_acceptance_criteria_field():
    """success-case(contract) - stage AC ownership is documented in schema."""
    # given
    schema = json.loads(_read("core/schemas/pipeline.schema.json"))

    # when
    stage_object_schema = schema["properties"]["stages"]["items"]["oneOf"][2]
    acceptance_criteria = stage_object_schema["properties"].get("acceptance_criteria")

    # then
    assert acceptance_criteria is not None
    assert acceptance_criteria["type"] == "array"
    assert acceptance_criteria["items"]["type"] == "string"
    assert "PRD" in acceptance_criteria["description"]


def test_downstream_quality_guidance_requires_assigned_ac_coverage():
    """success-case(contract) - implementation/review gates consume assigned AC IDs."""
    # given
    quality_loop = _read("core/rules/quality-loop.md")
    code_review = _read("core/agents/skills/code-review.md")

    # when / then
    assert "assigned `acceptance_criteria`" in quality_loop
    assert "assigned `AC-*`" in code_review
    assert "acceptance criterion or core feature is missing" in code_review
