"""Regression tests for completion summary output contracts."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_COMMAND = REPO_ROOT / "core" / "commands" / "run.md"
STATUS_COMMAND = REPO_ROOT / "core" / "commands" / "status.md"
VARIANTS_COMMAND = REPO_ROOT / "core" / "commands" / "variants.md"
VARIANTS_COLLECTOR = REPO_ROOT / "core" / "scripts" / "variant-session-collect.py"
SUPERVISOR_STAGES = REPO_ROOT / "core" / "agents" / "supervisor-stages.md"
SUMMARY_LABELS = ("**📦 Run Summary**", "**🛠️ Implementation Summary**")
LEGACY_HEADING_LABELS = ("## 📦 Run Summary", "## 🛠️ Implementation Summary")


def test_status_is_snapshot_only_without_collect_contract() -> None:
    run_text = RUN_COMMAND.read_text(encoding="utf-8")
    status_text = STATUS_COMMAND.read_text(encoding="utf-8")

    for label in SUMMARY_LABELS:
        assert label in run_text

    for legacy_heading in LEGACY_HEADING_LABELS:
        assert legacy_heading not in run_text
        assert legacy_heading not in status_text

    assert "crew:status --collect" not in status_text
    assert "[Run Summary]" not in status_text
    assert "[Implementation Summary]" not in status_text


def test_current_session_fallback_closeout_requires_summary_relay() -> None:
    run_text = RUN_COMMAND.read_text(encoding="utf-8")
    fallback_section = run_text.split("### Host Bridge Handoff Recovery", 1)[1].split(
        "4. For auto-completion:",
        1,
    )[0]
    normalized_fallback = " ".join(fallback_section.split())

    assert "`HOST_BRIDGE: current_session_required`" in fallback_section
    assert "before `crew repair" in normalized_fallback

    for label in SUMMARY_LABELS:
        assert label in fallback_section

    for legacy_heading in LEGACY_HEADING_LABELS:
        assert legacy_heading not in fallback_section


def test_supervisor_prompt_uses_bold_only_implementation_summary_label() -> None:
    supervisor_text = SUPERVISOR_STAGES.read_text(encoding="utf-8")

    assert "**🛠️ Implementation Summary**" in supervisor_text
    assert "## 🛠️ Implementation Summary" not in supervisor_text


def test_variant_collect_blocks_merge_until_candidate_selection() -> None:
    run_text = RUN_COMMAND.read_text(encoding="utf-8")
    variants_text = VARIANTS_COMMAND.read_text(encoding="utf-8")
    collector_text = VARIANTS_COLLECTOR.read_text(encoding="utf-8")

    assert "--variants N" in run_text
    assert 'session_type: "variants"' in run_text
    assert "candidate collection" in variants_text
    assert "Do not merge all completed branches" in collector_text
    assert "selection_status" in collector_text
