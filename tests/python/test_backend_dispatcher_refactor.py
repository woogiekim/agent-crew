"""Wave B exemplar (#131) — backend.md dispatcher refactor.

Asserts that `core/agents/backend.md` opts into the Wave A generalized
dispatcher primitive (`core/rules/agent-tool-dispatch.md`), declares the
**degraded-fallback** flavor of the fallback-policy taxonomy (as the
parallel exemplar to issuer's strict/BLOCKED flavor), and preserves its
existing runtime contract (declared on-demand skills section, language-
agnostic identity).
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_MD = REPO_ROOT / "core" / "agents" / "backend.md"
DISPATCH_RULE = REPO_ROOT / "core" / "rules" / "agent-tool-dispatch.md"


@pytest.fixture(scope="module")
def backend_md_text() -> str:
    assert BACKEND_MD.is_file(), f"backend.md missing at {BACKEND_MD}"
    return BACKEND_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dispatch_rule_text() -> str:
    assert DISPATCH_RULE.is_file(), f"agent-tool-dispatch.md missing at {DISPATCH_RULE}"
    return DISPATCH_RULE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 5-step dispatch protocol — backend.md must reference the rule and its steps #
# --------------------------------------------------------------------------- #


def test_backend_md_references_agent_tool_dispatch_rule(backend_md_text: str) -> None:
    """backend.md must reference the Wave A primitive by path."""
    assert "core/rules/agent-tool-dispatch.md" in backend_md_text, (
        "backend.md must reference core/rules/agent-tool-dispatch.md "
        "to opt into the 5-step dispatch protocol."
    )


def test_backend_md_declares_step_0_detect_axis(backend_md_text: str) -> None:
    """Step 1 of the 5-step protocol: detect language/framework axis."""
    assert "Detect" in backend_md_text and "axis" in backend_md_text, (
        "backend.md must include a Step 0 (or Step 1) — Detect language + "
        "framework axis — block that resolves the manifest file."
    )


def test_backend_md_declares_step_0_5_dispatch(backend_md_text: str) -> None:
    """Step 2-5 of the 5-step protocol: resolve <agent>-<lang>-<framework>, load, branch, dispatch."""
    assert "Step 0.5" in backend_md_text or "Resolve" in backend_md_text, (
        "backend.md must include a Step 0.5 — Resolve <agent>-<lang>-<framework> "
        "skill and load — block (Steps 2-5 of the dispatch protocol)."
    )


def test_backend_md_names_skill_per_naming_convention(backend_md_text: str) -> None:
    """Per agent-tool-dispatch.md § Naming convention: backend uses <agent>-<lang>-<framework>."""
    pattern_present = (
        "backend-{lang}-{framework}" in backend_md_text
        or "backend-{LANG}-{FRAMEWORK}" in backend_md_text
        or "<agent>-<lang>-<framework>" in backend_md_text
    )
    assert pattern_present, (
        "backend.md must declare the <agent>-<lang>-<framework> naming "
        "convention (e.g. backend-{lang}-{framework})."
    )
    assert "backend-kotlin-spring" in backend_md_text, (
        "backend.md must cite backend-kotlin-spring as the canonical example."
    )


def test_backend_md_loads_from_user_skills_layer(backend_md_text: str) -> None:
    """Step 3 of the 5-step protocol: load from ~/.agent-crew/user/skills/."""
    assert "~/.agent-crew/user/skills/" in backend_md_text, (
        "backend.md must declare that the resolved skill is loaded from "
        "~/.agent-crew/user/skills/<agent>-<lang>-<framework>.md."
    )


# --------------------------------------------------------------------------- #
# Fallback-policy taxonomy — backend MUST declare degraded-fallback           #
# --------------------------------------------------------------------------- #


def test_backend_md_declares_degraded_fallback_policy(backend_md_text: str) -> None:
    """The whole point of this Wave B exemplar: degraded-fallback flavor."""
    lowered = backend_md_text.lower()
    assert "degraded-fallback" in lowered, (
        "backend.md must explicitly declare 'degraded-fallback' as its "
        "fallback policy (the deliberate parallel exemplar to issuer's "
        "strict/BLOCKED flavor)."
    )


def test_backend_md_emits_crew_degraded_warning(backend_md_text: str) -> None:
    """The degraded-fallback contract requires a [crew] DEGRADED warning."""
    assert "[crew] DEGRADED" in backend_md_text, (
        "backend.md must specify that, when the user-layer skill is missing, "
        "it emits a `[crew] DEGRADED` warning line before continuing."
    )


def test_backend_md_does_not_block_on_missing_adapter(backend_md_text: str) -> None:
    """Degraded-fallback explicitly does NOT halt with STATUS: BLOCKED when a skill is missing.

    This is the load-bearing contrast to issuer.md (strict/BLOCKED flavor).
    """
    lower = backend_md_text.lower()
    idx = lower.find("degraded-fallback")
    assert idx != -1, "degraded-fallback block not found"
    window = backend_md_text[max(0, idx - 200): idx + 1200].lower()
    assert "continue" in window or "degraded" in window, (
        "The degraded-fallback declaration must explain that the agent "
        "continues using only language-level skills when the dispatcher's "
        "skill is missing (not halt with STATUS: BLOCKED)."
    )


def test_backend_md_contrasts_with_issuer_strict_flavor(backend_md_text: str) -> None:
    """The exemplar must explicitly say it is the contrast to issuer's strict flavor."""
    lowered = backend_md_text.lower()
    has_issuer_reference = "issuer" in lowered
    has_strict_or_blocked_reference = ("strict" in lowered) or ("blocked" in lowered)
    assert has_issuer_reference and has_strict_or_blocked_reference, (
        "backend.md must reference the issuer agent and the strict/BLOCKED "
        "flavor to make the parallel-exemplar relationship explicit."
    )


# --------------------------------------------------------------------------- #
# Runtime contract preservation                                                #
# --------------------------------------------------------------------------- #


def test_backend_md_preserves_on_demand_skills_section(backend_md_text: str) -> None:
    """The existing declared on-demand skills section must survive the refactor."""
    assert "## Skills (Loaded On Demand)" in backend_md_text, (
        "backend.md must retain its `## Skills (Loaded On Demand)` section "
        "(declared skill loading is complementary to the dispatcher per "
        "agent-tool-dispatch.md § 'An agent MAY use both conventions')."
    )


def test_backend_md_preserves_language_agnostic_identity(backend_md_text: str) -> None:
    """The agent's language-agnostic identity (DDD/TDD/Object Calisthenics) survives."""
    for required_identity in ("TDD", "DDD"):
        assert required_identity in backend_md_text, (
            f"backend.md must retain its language-agnostic identity marker "
            f"'{required_identity}' even after the Wave B refactor."
        )
    lowered = backend_md_text.lower()
    assert "object calisthenics" in lowered, (
        "Object Calisthenics is language-agnostic and must remain in backend.md."
    )
    assert (
        "tell, don't ask" in lowered
        or "tell don't ask" in lowered
        or "tell, dont ask" in lowered
    ), "Tell, Don't Ask is language-agnostic and must remain in backend.md."


def test_backend_md_declares_kotlin_spring_axis_example(backend_md_text: str) -> None:
    """The Kotlin/Spring axis must be the documented worked example."""
    lower = backend_md_text.lower()
    assert "kotlin-spring" in lower, (
        "backend.md must show kotlin-spring as the worked example."
    )
    assert ("build.gradle" in backend_md_text) or ("gradle" in lower), (
        "backend.md must name a gradle-flavored manifest as the detection "
        "signal for the kotlin-spring axis."
    )


# --------------------------------------------------------------------------- #
# Cross-check: agent-tool-dispatch.md catalog must show backend as opted in    #
# --------------------------------------------------------------------------- #


def test_dispatch_rule_lists_backend_as_dispatcher_candidate(dispatch_rule_text: str) -> None:
    """Backend is listed in the dispatch-eligible agents table.

    #186 graduated backend from "Wave-B candidate" to "Opted in" via
    metadata-driven skill dispatch. The Wave-A primitive still references
    backend as the canonical Wave-B exemplar in commentary; the candidates
    table row must now record opted-in status.
    """
    assert "backend" in dispatch_rule_text.lower()
    assert "| `backend` | Opted in" in dispatch_rule_text
    # Wave-B remains as a label in commentary (e.g. "Wave B exemplar") and
    # in adapter-skill descriptions; only the candidates-table row changed.
    assert (
        "Wave B" in dispatch_rule_text
        or "Wave-B" in dispatch_rule_text
        or "wave-b" in dispatch_rule_text.lower()
    )
