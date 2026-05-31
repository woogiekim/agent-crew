"""Wave C exemplar (#131) — documenter.md dispatcher refactor.

Asserts that `core/agents/documenter.md` opts into the Wave A generalized
dispatcher primitive (`core/rules/agent-tool-dispatch.md`), declares the
**degraded-fallback** flavor of the fallback-policy taxonomy (parallel to
backend's degraded-fallback exemplar; contrasted with issuer's strict /
BLOCKED flavor), and preserves its existing runtime contract:

- Default-output absolute rules (never modify repo-tracked files in auto mode,
  never sync to external wikis without an installed user-layer skill).
- Page-Out Mode (supervisor-internal handoff compaction).
- Three operating modes (auto / to-readme / page-out).

These are the AC1-AC5 enforcement tests from the PRD.
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCUMENTER_MD = REPO_ROOT / "core" / "agents" / "documenter.md"
DISPATCH_RULE = REPO_ROOT / "core" / "rules" / "agent-tool-dispatch.md"


@pytest.fixture(scope="module")
def documenter_md_text() -> str:
    assert DOCUMENTER_MD.is_file(), f"documenter.md missing at {DOCUMENTER_MD}"
    return DOCUMENTER_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dispatch_rule_text() -> str:
    assert DISPATCH_RULE.is_file(), f"agent-tool-dispatch.md missing at {DISPATCH_RULE}"
    return DISPATCH_RULE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC1 — 5-step dispatch protocol (Step 0 + Step 0.5 + rule reference)         #
# --------------------------------------------------------------------------- #


def test_documenter_md_references_agent_tool_dispatch_rule(
    documenter_md_text: str,
) -> None:
    """documenter.md must reference the Wave A primitive by path."""
    assert "core/rules/agent-tool-dispatch.md" in documenter_md_text, (
        "documenter.md must reference core/rules/agent-tool-dispatch.md "
        "to opt into the 5-step dispatch protocol."
    )


def test_documenter_md_declares_step_0_detect_axis(
    documenter_md_text: str,
) -> None:
    """Step 1 of the 5-step protocol: detect output-target axis."""
    assert "Step 0" in documenter_md_text, (
        "documenter.md must include a Step 0 — Detect output-target axis — "
        "block that classifies the documentation backend."
    )
    lowered = documenter_md_text.lower()
    assert "detect" in lowered and "axis" in lowered, (
        "documenter.md Step 0 must describe axis detection."
    )


def test_documenter_md_declares_step_0_5_dispatch(
    documenter_md_text: str,
) -> None:
    """Step 2-5 of the 5-step protocol: resolve <agent>-<tool>, load, branch, dispatch."""
    assert "Step 0.5" in documenter_md_text, (
        "documenter.md must include a Step 0.5 — Resolve <agent>-<tool> "
        "skill and load — block (Steps 2-5 of the dispatch protocol)."
    )


def test_documenter_md_names_skill_per_naming_convention(
    documenter_md_text: str,
) -> None:
    """Per agent-tool-dispatch.md § Naming convention: documenter uses <agent>-<tool>."""
    pattern_present = (
        "documenter-{tool}" in documenter_md_text
        or "documenter-{TOOL}" in documenter_md_text
        or "<agent>-<tool>" in documenter_md_text
    )
    assert pattern_present, (
        "documenter.md must declare the <agent>-<tool> naming convention "
        "(e.g. documenter-{tool})."
    )
    # The Wave C exemplar ships documenter-outline.md as the canonical example.
    assert "documenter-outline" in documenter_md_text, (
        "documenter.md must cite documenter-outline as the canonical example "
        "(matching the shipped Channel B template)."
    )


def test_documenter_md_loads_from_user_skills_layer(
    documenter_md_text: str,
) -> None:
    """Step 3 of the 5-step protocol: load from ~/.agent-crew/user/skills/."""
    assert "~/.agent-crew/user/skills/" in documenter_md_text, (
        "documenter.md must declare that the resolved skill is loaded from "
        "~/.agent-crew/user/skills/<agent>-<tool>.md."
    )


# --------------------------------------------------------------------------- #
# AC2 — Fallback-policy taxonomy: degraded-fallback flavor                    #
# --------------------------------------------------------------------------- #


def test_documenter_md_declares_degraded_fallback_policy(
    documenter_md_text: str,
) -> None:
    """The whole point of this Wave C exemplar: degraded-fallback flavor."""
    lowered = documenter_md_text.lower()
    assert "degraded-fallback" in lowered, (
        "documenter.md must explicitly declare 'degraded-fallback' as its "
        "fallback policy (the deliberate parallel exemplar to backend's "
        "degraded-fallback and contrast to issuer's strict/BLOCKED flavor)."
    )


def test_documenter_md_emits_crew_degraded_warning(
    documenter_md_text: str,
) -> None:
    """The degraded-fallback contract requires a [crew] DEGRADED warning."""
    assert "[crew] DEGRADED" in documenter_md_text, (
        "documenter.md must specify that, when the user-layer skill is missing, "
        "it emits a `[crew] DEGRADED` warning line before continuing."
    )


def test_documenter_md_does_not_block_on_missing_adapter(
    documenter_md_text: str,
) -> None:
    """Degraded-fallback explicitly does NOT halt with STATUS: BLOCKED on missing skill.

    This is the load-bearing contrast to issuer.md (strict/BLOCKED flavor).
    """
    lower = documenter_md_text.lower()
    idx = lower.find("degraded-fallback")
    assert idx != -1, "degraded-fallback block not found"
    window = documenter_md_text[max(0, idx - 200): idx + 1500].lower()
    assert "continue" in window or "default" in window, (
        "The degraded-fallback declaration must explain that the documenter "
        "continues producing default side-car output when the dispatcher's "
        "skill is missing (not halt with STATUS: BLOCKED)."
    )


# --------------------------------------------------------------------------- #
# AC3 — Contrast block with issuer (strict / BLOCKED)                         #
# --------------------------------------------------------------------------- #


def test_documenter_md_contrasts_with_issuer_strict_flavor(
    documenter_md_text: str,
) -> None:
    """The exemplar must explicitly reference the contrast with issuer's strict flavor."""
    lowered = documenter_md_text.lower()
    has_issuer_reference = "issuer" in lowered
    has_strict_or_blocked_reference = ("strict" in lowered) or ("blocked" in lowered)
    assert has_issuer_reference and has_strict_or_blocked_reference, (
        "documenter.md must reference the issuer agent and the strict/BLOCKED "
        "flavor to make the parallel-exemplar relationship explicit "
        "(Wave A taxonomy: strict vs degraded-fallback vs prompt-user)."
    )


# --------------------------------------------------------------------------- #
# AC4 — Page-Out Mode preserved verbatim                                      #
# --------------------------------------------------------------------------- #


def test_documenter_md_preserves_page_out_mode_section(
    documenter_md_text: str,
) -> None:
    """Page-Out Mode is supervisor-internal handoff compaction — NOT part of dispatch.

    The dispatcher refactor must NOT delete, move, or rewrite this section.
    """
    assert "Page-Out Mode" in documenter_md_text, (
        "documenter.md must retain its Page-Out Mode section verbatim — "
        "the dispatcher refactor only adds Step 0 / Step 0.5 ahead of the "
        "existing workflow; it does NOT modify Page-Out Mode."
    )
    assert "MODE=page-out" in documenter_md_text, (
        "documenter.md must retain the MODE=page-out trigger for the "
        "supervisor-internal handoff compaction operation."
    )
    # The three structural elements of Page-Out Mode must all still exist.
    assert "ARCHIVE_NUM" in documenter_md_text, (
        "documenter.md must retain the ARCHIVE_NUM input declaration for Page-Out Mode."
    )
    assert "archive/handoff-" in documenter_md_text, (
        "documenter.md must retain the archive/handoff-{N}.md target path "
        "for the paged-out original."
    )


def test_documenter_md_preserves_three_operating_modes(
    documenter_md_text: str,
) -> None:
    """auto / to-readme / page-out — the three modes must survive the refactor."""
    for mode in ("auto", "to-readme", "page-out"):
        assert f"`{mode}`" in documenter_md_text or f"MODE={mode}" in documenter_md_text, (
            f"documenter.md must retain its '{mode}' operating mode."
        )


# --------------------------------------------------------------------------- #
# AC5 — Default-output absolute rules preserved                               #
# --------------------------------------------------------------------------- #


def test_documenter_md_preserves_no_repo_tracked_writes_rule(
    documenter_md_text: str,
) -> None:
    """The 'NEVER modify repo-tracked files in default mode' rule MUST survive."""
    assert "## Absolute Rules" in documenter_md_text, (
        "documenter.md must retain its '## Absolute Rules' section."
    )
    lowered = documenter_md_text.lower()
    assert "never" in lowered and "repo-tracked" in lowered, (
        "documenter.md must retain the 'NEVER modify repo-tracked files in "
        "default mode' rule (side-car-only invariant)."
    )


def test_documenter_md_preserves_no_external_sync_rule(
    documenter_md_text: str,
) -> None:
    """The 'NEVER sync to external wikis without user-layer skill' rule MUST survive.

    Under the dispatcher pattern, external-wiki sync becomes ENABLED ONLY when a
    user installs the matching `documenter-<tool>` skill — never automatic.
    """
    lowered = documenter_md_text.lower()
    # Either the original phrasing ("never sync to external wikis") or the
    # post-refactor wording that ties external sync to an installed user-layer
    # skill is acceptable.
    has_external_sync_rule = (
        ("never" in lowered and ("external wiki" in lowered or "external wikis" in lowered))
        or ("user-layer skill" in lowered and "external" in lowered)
    )
    assert has_external_sync_rule, (
        "documenter.md must retain the 'NEVER sync to external wikis without an "
        "installed user-layer skill' invariant (or its dispatcher-aware "
        "equivalent)."
    )


def test_documenter_md_preserves_result_md_canonical_output(
    documenter_md_text: str,
) -> None:
    """{TASK_DIR}/result.md remains the canonical output regardless of dispatch state."""
    assert "{TASK_DIR}/result.md" in documenter_md_text, (
        "documenter.md must retain {TASK_DIR}/result.md as the canonical "
        "default output — this is the file the degraded-fallback continues "
        "to produce when no user-layer skill is installed."
    )


# --------------------------------------------------------------------------- #
# Cross-check: agent-tool-dispatch.md catalog lists documenter as opted in    #
# --------------------------------------------------------------------------- #


def test_dispatch_rule_lists_documenter_as_dispatcher_candidate(
    dispatch_rule_text: str,
) -> None:
    """Sanity check on the Wave A primitive — documenter is still catalogued."""
    assert "documenter" in dispatch_rule_text.lower()
    # The Wave A rule catalogs documenter under § Agents subject to dispatch
    # as a Wave-C candidate.
    assert "Wave-C" in dispatch_rule_text or "wave-c" in dispatch_rule_text.lower()
