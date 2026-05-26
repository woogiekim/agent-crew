"""Tests for issuer agent registration in core/rules/agent-routing.md.

Verifies acceptance criteria from GitHub issue #35:
  AC1 — issuer row present in Auto-Routing Rules table
  AC2 — issuer row present in Agent Registry table
  AC3 — zero Plane/Jira/GitHub/Linear mentions in the Pattern column
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTING_PATH = REPO_ROOT / "core" / "rules" / "agent-routing.md"


def _load_routing_text() -> str:
    return ROUTING_PATH.read_text(encoding="utf-8")


def _table_rows(text: str, header_fragment: str) -> list[str]:
    """Return all data rows (pipe-delimited) that appear after a *section heading*
    (a line starting with '## ' or '### ') containing *header_fragment*.
    Stops collecting when the next same-or-higher-level heading is encountered."""
    rows: list[str] = []
    in_section = False
    section_level = 0
    for line in text.splitlines():
        # Check if this line is a heading that contains the fragment
        heading_match = re.match(r"^(#{2,})\s+", line)
        if heading_match and re.search(re.escape(header_fragment), line, re.IGNORECASE):
            in_section = True
            section_level = len(heading_match.group(1))
            continue
        if in_section and heading_match:
            current_level = len(heading_match.group(1))
            # Stop on any heading at the same or higher level
            if current_level <= section_level:
                break
        if in_section and line.startswith("|"):
            rows.append(line)
    return rows


# ---------------------------------------------------------------------------
# AC1 — issuer row in Auto-Routing Rules table
# ---------------------------------------------------------------------------

class TestAutoRoutingRulesEntry:
    def test_issuer_row_exists(self):
        """A row with agent=issuer must appear in the Auto-Routing Rules table."""
        text = _load_routing_text()
        rows = _table_rows(text, "Auto-Routing Rules")
        issuer_rows = [r for r in rows if "issuer" in r.lower()]
        assert issuer_rows, (
            "No row containing 'issuer' found in the Auto-Routing Rules table. "
            f"Checked {ROUTING_PATH}"
        )

    def test_issuer_row_priority(self):
        """The issuer row should be at priority 9.5 (between mentorship and no-match)."""
        text = _load_routing_text()
        rows = _table_rows(text, "Auto-Routing Rules")
        issuer_rows = [r for r in rows if "issuer" in r.lower()]
        assert issuer_rows, "issuer row not found"
        assert "9.5" in issuer_rows[0], (
            f"Expected priority 9.5 in issuer row but got: {issuer_rows[0]}"
        )

    def test_issuer_row_confidence_medium(self):
        """The issuer routing row should carry 'medium' confidence."""
        text = _load_routing_text()
        rows = _table_rows(text, "Auto-Routing Rules")
        issuer_rows = [r for r in rows if "issuer" in r.lower()]
        assert issuer_rows, "issuer row not found"
        assert "medium" in issuer_rows[0].lower(), (
            f"Expected 'medium' confidence in issuer row but got: {issuer_rows[0]}"
        )

    def test_issuer_row_covers_lifecycle_updates(self):
        """The issuer row must cover lifecycle transitions and field updates."""
        text = _load_routing_text()
        rows = _table_rows(text, "Auto-Routing Rules")
        issuer_rows = [r for r in rows if "issuer" in r.lower()]
        assert issuer_rows, "issuer row not found"
        row = issuer_rows[0].lower()
        for marker in ("issue lifecycle", "status transition", "field update"):
            assert marker in row, (
                f"Expected lifecycle marker {marker!r} in issuer row: {issuer_rows[0]}"
            )


# ---------------------------------------------------------------------------
# AC2 — issuer row in Agent Registry table
# ---------------------------------------------------------------------------

class TestAgentRegistryEntry:
    def test_issuer_row_exists(self):
        """A row for the issuer agent must appear in the Agent Registry table."""
        text = _load_routing_text()
        rows = _table_rows(text, "Agent Registry")
        issuer_rows = [r for r in rows if r.lstrip("| ").lower().startswith("issuer")]
        assert issuer_rows, (
            "No row for 'issuer' found in the Agent Registry table. "
            f"Checked {ROUTING_PATH}"
        )

    def test_issuer_safe_for_direct_invocation(self):
        """The issuer agent remains directly invokable for read-only tasks."""
        text = _load_routing_text()
        rows = _table_rows(text, "Agent Registry")
        issuer_rows = [r for r in rows if r.lstrip("| ").lower().startswith("issuer")]
        assert issuer_rows, "issuer row not found in Agent Registry"
        assert "yes" in issuer_rows[0].lower(), (
            f"Expected 'yes' for safe direct invocation in issuer registry row: {issuer_rows[0]}"
        )

    def test_issuer_registry_mentions_lifecycle_scope(self):
        text = _load_routing_text()
        rows = _table_rows(text, "Agent Registry")
        issuer_rows = [r for r in rows if r.lstrip("| ").lower().startswith("issuer")]
        assert issuer_rows, "issuer row not found in Agent Registry"
        row = issuer_rows[0].lower()
        assert "state transitions" in row
        assert "field updates" in row


# ---------------------------------------------------------------------------
# AC3 — zero tool-specific keywords in Pattern column
# ---------------------------------------------------------------------------

FORBIDDEN_TOOL_NAMES = re.compile(
    r"\b(Plane|Jira|GitHub|Linear)\b",
    re.IGNORECASE,
)


class TestNoToolSpecificKeywords:
    def test_pattern_column_has_no_plane(self):
        text = _load_routing_text()
        rows = _table_rows(text, "Auto-Routing Rules")
        issuer_rows = [r for r in rows if "issuer" in r.lower()]
        for row in issuer_rows:
            # Extract the Pattern column (second column in the table)
            cols = [c.strip() for c in row.split("|")]
            if len(cols) >= 3:
                pattern_col = cols[2]  # index 2 = third pipe-separated field
                m = FORBIDDEN_TOOL_NAMES.search(pattern_col)
                assert not m, (
                    f"Tool-specific keyword '{m.group()}' found in issuer Pattern "
                    f"column — must be tool-agnostic. Row: {row}"
                )

    def test_no_tool_names_anywhere_in_issuer_rows(self):
        """Belt-and-suspenders: scan every issuer row for any forbidden tool name."""
        text = _load_routing_text()
        for section_header in ("Auto-Routing Rules", "Agent Registry"):
            rows = _table_rows(text, section_header)
            issuer_rows = [r for r in rows if "issuer" in r.lower()]
            for row in issuer_rows:
                m = FORBIDDEN_TOOL_NAMES.search(row)
                assert not m, (
                    f"Tool-specific keyword '{m.group()}' found in issuer row "
                    f"(section: {section_header}). Row: {row}"
                )
