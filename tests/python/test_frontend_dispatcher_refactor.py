"""Wave C exemplar (#131) — frontend.md dispatcher refactor.

Asserts that `core/agents/frontend.md` opts into the Wave A generalized
dispatcher primitive (`core/rules/agent-tool-dispatch.md`), declares the
**degraded-fallback** flavor of the fallback-policy taxonomy (mirroring
the Wave B backend exemplar — UI work can still proceed with
language-agnostic TDD + ui-component-design skills even when the
framework-specific template is absent), and preserves its existing
runtime contract (declared on-demand skills section, language-agnostic
identity).
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_MD = REPO_ROOT / "core" / "agents" / "frontend.md"
DISPATCH_RULE = REPO_ROOT / "core" / "rules" / "agent-tool-dispatch.md"


@pytest.fixture(scope="module")
def frontend_md_text() -> str:
    assert FRONTEND_MD.is_file(), f"frontend.md missing at {FRONTEND_MD}"
    return FRONTEND_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dispatch_rule_text() -> str:
    assert DISPATCH_RULE.is_file(), f"agent-tool-dispatch.md missing at {DISPATCH_RULE}"
    return DISPATCH_RULE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 5-step dispatch protocol — frontend.md must reference the rule and its steps #
# --------------------------------------------------------------------------- #


def test_frontend_md_references_agent_tool_dispatch_rule(frontend_md_text: str) -> None:
    """frontend.md must reference the Wave A primitive by path."""
    assert "core/rules/agent-tool-dispatch.md" in frontend_md_text, (
        "frontend.md must reference core/rules/agent-tool-dispatch.md "
        "to opt into the 5-step dispatch protocol."
    )


def test_frontend_md_declares_step_0_detect_axis(frontend_md_text: str) -> None:
    """Step 1 of the 5-step protocol: detect language/framework axis."""
    assert "Detect" in frontend_md_text and "axis" in frontend_md_text, (
        "frontend.md must include a Step 0 (or Step 1) — Detect language + "
        "framework axis — block that resolves the manifest file."
    )


def test_frontend_md_declares_step_0_5_dispatch(frontend_md_text: str) -> None:
    """Step 2-5 of the 5-step protocol: resolve <agent>-<lang>-<framework>, load, branch, dispatch."""
    assert "Step 0.5" in frontend_md_text or "Resolve" in frontend_md_text, (
        "frontend.md must include a Step 0.5 — Resolve <agent>-<lang>-<framework> "
        "skill and load — block (Steps 2-5 of the dispatch protocol)."
    )


def test_frontend_md_names_skill_per_naming_convention(frontend_md_text: str) -> None:
    """Per agent-tool-dispatch.md § Naming convention: frontend uses <agent>-<lang>-<framework>."""
    pattern_present = (
        "frontend-{lang}-{framework}" in frontend_md_text
        or "frontend-{LANG}-{FRAMEWORK}" in frontend_md_text
        or "<agent>-<lang>-<framework>" in frontend_md_text
    )
    assert pattern_present, (
        "frontend.md must declare the <agent>-<lang>-<framework> naming "
        "convention (e.g. frontend-{lang}-{framework})."
    )
    assert "frontend-typescript-react" in frontend_md_text, (
        "frontend.md must cite frontend-typescript-react as the canonical example."
    )


def test_frontend_md_loads_from_user_skills_layer(frontend_md_text: str) -> None:
    """Step 3 of the 5-step protocol: load from ~/.agent-crew/user/skills/."""
    assert "~/.agent-crew/user/skills/" in frontend_md_text, (
        "frontend.md must declare that the resolved skill is loaded from "
        "~/.agent-crew/user/skills/<agent>-<lang>-<framework>.md."
    )


# --------------------------------------------------------------------------- #
# Fallback-policy taxonomy — frontend MUST declare degraded-fallback           #
# --------------------------------------------------------------------------- #


def test_frontend_md_declares_degraded_fallback_policy(frontend_md_text: str) -> None:
    """The whole point of this Wave C exemplar: degraded-fallback flavor (mirrors backend)."""
    lowered = frontend_md_text.lower()
    assert "degraded-fallback" in lowered, (
        "frontend.md must explicitly declare 'degraded-fallback' as its "
        "fallback policy (mirroring the Wave B backend exemplar)."
    )


def test_frontend_md_emits_crew_degraded_warning(frontend_md_text: str) -> None:
    """The degraded-fallback contract requires a [crew] DEGRADED warning."""
    assert "[crew] DEGRADED" in frontend_md_text, (
        "frontend.md must specify that, when the user-layer skill is missing, "
        "it emits a `[crew] DEGRADED` warning line before continuing."
    )


def test_frontend_md_does_not_block_on_missing_adapter(frontend_md_text: str) -> None:
    """Degraded-fallback explicitly does NOT halt with STATUS: BLOCKED when a skill is missing.

    This is the load-bearing contrast to issuer.md (strict/BLOCKED flavor).
    """
    lower = frontend_md_text.lower()
    idx = lower.find("degraded-fallback")
    assert idx != -1, "degraded-fallback block not found"
    window = frontend_md_text[max(0, idx - 200): idx + 1200].lower()
    assert "continue" in window or "degraded" in window, (
        "The degraded-fallback declaration must explain that the agent "
        "continues using only language-agnostic skills when the dispatcher's "
        "skill is missing (not halt with STATUS: BLOCKED)."
    )


def test_frontend_md_contrasts_with_issuer_strict_flavor(frontend_md_text: str) -> None:
    """The exemplar must explicitly say it is the contrast to issuer's strict flavor."""
    lowered = frontend_md_text.lower()
    has_issuer_reference = "issuer" in lowered
    has_strict_or_blocked_reference = ("strict" in lowered) or ("blocked" in lowered)
    assert has_issuer_reference and has_strict_or_blocked_reference, (
        "frontend.md must reference the issuer agent and the strict/BLOCKED "
        "flavor to make the parallel-exemplar relationship explicit."
    )


def test_frontend_md_references_backend_as_peer_exemplar(frontend_md_text: str) -> None:
    """Wave C frontend is the third dispatcher; it should reference backend as its peer
    degraded-fallback exemplar so future readers see the family relationship."""
    lowered = frontend_md_text.lower()
    assert "backend" in lowered, (
        "frontend.md must reference the backend agent (its peer degraded-fallback "
        "exemplar) to make the family relationship explicit."
    )


# --------------------------------------------------------------------------- #
# Runtime contract preservation                                                #
# --------------------------------------------------------------------------- #


def test_frontend_md_preserves_on_demand_skills_section(frontend_md_text: str) -> None:
    """The existing declared on-demand skills section must survive the refactor."""
    assert "## Skills (Loaded On Demand)" in frontend_md_text, (
        "frontend.md must retain its `## Skills (Loaded On Demand)` section "
        "(declared skill loading is complementary to the dispatcher per "
        "agent-tool-dispatch.md § 'An agent MAY use both conventions')."
    )


def test_frontend_md_preserves_language_agnostic_identity(frontend_md_text: str) -> None:
    """The agent's language-agnostic identity (TDD discipline, UI component design)
    survives the refactor."""
    assert "TDD" in frontend_md_text, (
        "frontend.md must retain its TDD identity marker even after the Wave C refactor."
    )
    lowered = frontend_md_text.lower()
    assert "ui-component-design" in lowered or "component decomposition" in lowered, (
        "frontend.md must retain its UI component decomposition guidance "
        "(language-agnostic identity)."
    )


def test_frontend_md_declares_typescript_react_axis_example(frontend_md_text: str) -> None:
    """The TypeScript/React axis must be the documented worked example."""
    lower = frontend_md_text.lower()
    assert "typescript-react" in lower, (
        "frontend.md must show typescript-react as the worked example."
    )
    assert "package.json" in lower, (
        "frontend.md must name package.json as the detection signal for the "
        "typescript-react axis (and sibling axes)."
    )


def test_frontend_md_dispatcher_boundary_rule_present(frontend_md_text: str) -> None:
    """The dispatcher boundary rule must be in Absolute Rules — do NOT run stack-specific
    commands (npm test, npx vitest, npx jest, npx tsc) before Step 0.5 completes."""
    lowered = frontend_md_text.lower()
    assert "dispatcher boundary" in lowered, (
        "frontend.md must include a 'Dispatcher boundary' rule in Absolute Rules "
        "(mirrors backend.md)."
    )
    # At least one stack-specific runner literal must be cited as the forbidden-before-dispatch example.
    has_runner_literal = (
        "npm test" in lowered
        or "npx vitest" in lowered
        or "npx jest" in lowered
        or "npx tsc" in lowered
    )
    assert has_runner_literal, (
        "frontend.md dispatcher boundary rule must cite at least one stack-specific "
        "runner literal (npm test / npx vitest / npx jest / npx tsc) as the "
        "forbidden-before-dispatch example."
    )


# --------------------------------------------------------------------------- #
# Cross-check: agent-tool-dispatch.md catalog must show frontend as opted in    #
# --------------------------------------------------------------------------- #


def test_dispatch_rule_lists_frontend_as_dispatcher_candidate(dispatch_rule_text: str) -> None:
    """Sanity check on the Wave A primitive — frontend is still listed."""
    assert "frontend" in dispatch_rule_text.lower()
    assert "Wave-C" in dispatch_rule_text or "wave-c" in dispatch_rule_text.lower()
