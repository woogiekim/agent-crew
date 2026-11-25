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


def test_named_tracker_destinations_bypass_remote_detection():
    routing = ISSUER_PATH.read_text(encoding="utf-8").split("### Step 0 —", 1)[1]
    explicit, _ = routing.split("\n2. ", 1)
    explicit = " ".join(explicit.split())

    assert "`플레인이슈로 발행` selects `BACKEND_ADAPTER=plane`" in explicit
    assert "`에이스이슈로 발행` selects `BACKEND_ADAPTER=ace`" in explicit
    assert "bypass the Git remote" in explicit
    assert "`source: explicit`" in explicit
    assert "Preserve the original task text" in explicit


def test_conflicting_tracker_targets_require_a_choice_before_dispatch():
    routing = ISSUER_PATH.read_text(encoding="utf-8").split("### Step 0 —", 1)[1]
    explicit, _ = routing.split("\n2. ", 1)
    explicit = " ".join(explicit.split())

    assert "conflicts with a non-auto `BACKEND_ADAPTER`" in explicit
    assert "more than one tracker is named as the destination" in explicit
    assert "ask which single tracker to use before continuing" in explicit
    assert "issue title, body, migration source, or key prefix does not select it" in explicit


def test_remote_resolution_runs_only_without_an_explicit_target():
    routing = ISSUER_PATH.read_text(encoding="utf-8").split("### Step 0 —", 1)[1]
    _, fallback = routing.split("\n2. ", 1)
    fallback = fallback.split("### Step 0.5", 1)[0]

    assert "If neither the request nor `BACKEND_ADAPTER` specifies a tracker" in fallback
    assert "git remote get-url origin" in fallback
    assert "`BACKEND_ADAPTER=github`" in fallback
    assert "`BACKEND_ADAPTER=gitlab`" in fallback
    assert "No remote — interactive resolution" in fallback
    assert "Unknown remote — explicit consent fallback" in fallback


def test_ace_create_requires_issue_content_before_adapter_dispatch():
    dispatch = ISSUER_PATH.read_text(encoding="utf-8").split("### Step 0.5 —", 1)[1]
    operation, _ = dispatch.split("\n3. ", 1)
    operation = " ".join(operation.split())

    assert "For Ace publication, `이슈 발행해줘` is a `create` request." in operation
    assert "If there is no `ISSUES_FILE` or issue content, ask" in operation
    assert "keep the original request intact" in operation
    assert "Pass that path as `ISSUES_FILE`" in operation
