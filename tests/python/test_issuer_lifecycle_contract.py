"""Regression tests for issuer lifecycle-management responsibilities.

Issue #115 expands issuer from create-only issue publishing to lifecycle
operations: create, transition, and non-state field update.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ISSUER_PATH = REPO_ROOT / "core" / "agents" / "issuer.md"
AGENT_ROUTING_PATH = REPO_ROOT / "core" / "rules" / "agent-routing.md"
CAPABILITIES_PATH = REPO_ROOT / "core" / "policies" / "agent-capabilities.json"


def test_issuer_declares_lifecycle_operation_inputs():
    text = ISSUER_PATH.read_text(encoding="utf-8")

    for marker in (
        "OPERATION_MODE",
        "ISSUE_REFS",
        "TARGET_STATE",
        "FIELD_UPDATES",
    ):
        assert marker in text


def test_issuer_classifies_create_transition_and_update_operations():
    text = ISSUER_PATH.read_text(encoding="utf-8")

    assert "## Operation Classification" in text
    for operation in ("`create`", "`transition`", "`update`"):
        assert operation in text


def test_issuer_contract_requires_lifecycle_adapter_methods():
    text = ISSUER_PATH.read_text(encoding="utf-8")

    for marker in (
        "### Lifecycle Management",
        "Issue resolution",
        "State transition",
        "Field update",
        "Bulk operations",
        "Result reporting",
        "ISSUE_REFS",
    ):
        assert marker in text


def test_agent_routing_defines_issue_lifecycle_pattern():
    routing = AGENT_ROUTING_PATH.read_text(encoding="utf-8")
    issuer = ISSUER_PATH.read_text(encoding="utf-8")

    for marker in ("issue lifecycle", "status transition", "priority update", "assignee update"):
        assert marker in routing
    for marker in ("완료", "진행", "reopen", "priority", "assignee"):
        assert marker in issuer


def test_issuer_capability_manifest_mentions_lifecycle_dispatch():
    text = CAPABILITIES_PATH.read_text(encoding="utf-8")

    assert "issue_lifecycle_dispatch" in text
    assert "transition" in text
    assert "field-update" in text
