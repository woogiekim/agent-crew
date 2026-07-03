"""Tests for Claude reasoning-tier model materialization."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLAUDE_SETUP = REPO_ROOT / "adapters" / "claude" / "setup.sh"


def test_claude_setup_uses_upgraded_reasoning_tier_models():
    """success-case - materializer contains the upgraded Claude model map."""
    # given
    text = CLAUDE_SETUP.read_text(encoding="utf-8")

    # when
    block_match = re.search(r"TIER_TO_MODEL = \{(.*?)\n\}", text, re.DOTALL)

    # then
    assert block_match is not None
    block = block_match.group(1)
    assert '"xhigh":' in block and '"claude-fable-5"' in block
    assert '"deep":' in block and '"claude-opus-4-8"' in block
    assert '"balanced":' in block and '"claude-sonnet-5"' in block
    assert '"light":' in block and '"claude-haiku-4-5"' in block
