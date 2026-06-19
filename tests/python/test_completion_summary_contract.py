"""Regression tests for completion summary output contracts."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_COMMAND = REPO_ROOT / "core" / "commands" / "run.md"
STATUS_COMMAND = REPO_ROOT / "core" / "commands" / "status.md"
SUMMARY_HEADINGS = ("## 📦 Run Summary", "## 🛠️ Implementation Summary")


def test_status_collect_uses_same_summary_headings_as_run() -> None:
    run_text = RUN_COMMAND.read_text(encoding="utf-8")
    status_text = STATUS_COMMAND.read_text(encoding="utf-8")

    for heading in SUMMARY_HEADINGS:
        assert heading in run_text
        assert heading in status_text

    assert "## Run Summary\n" not in status_text
    assert "## Implementation Summary\n" not in status_text


def test_current_session_fallback_closeout_requires_summary_relay() -> None:
    run_text = RUN_COMMAND.read_text(encoding="utf-8")
    fallback_section = run_text.split("### Host Bridge Handoff Recovery", 1)[1].split(
        "4. For auto-completion:",
        1,
    )[0]
    normalized_fallback = " ".join(fallback_section.split())

    assert "`HOST_BRIDGE: current_session_required`" in fallback_section
    assert "before `crew repair" in normalized_fallback

    for heading in SUMMARY_HEADINGS:
        assert heading in fallback_section
