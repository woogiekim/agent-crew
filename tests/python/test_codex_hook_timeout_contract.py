"""Regression coverage for Codex hook timeout contracts."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP = REPO_ROOT / "adapters" / "codex" / "setup.sh"


def _setup_text() -> str:
    return SETUP.read_text(encoding="utf-8")


def _hook_entry(script_name: str) -> str:
    text = _setup_text()
    match = re.search(
        rf"\{{\s*\"type\": \"command\",\s*\"command\": f\"bash '\{{home\}}/hooks/{re.escape(script_name)}'\",(?P<body>.*?)\}}",
        text,
        flags=re.DOTALL,
    )
    assert match, f"missing Codex hook entry for {script_name}"
    return match.group(0)


def test_codex_pretooluse_bash_guard_has_explicit_timeout() -> None:
    assert '"timeout": 5' in _hook_entry("guard-dangerous-commands.sh")


def test_codex_pretooluse_tracker_guard_has_explicit_timeout() -> None:
    assert '"timeout": 5' in _hook_entry("tracker-mutation-guard.sh")


def test_codex_pretooluse_direct_edit_guard_has_explicit_timeout() -> None:
    assert '"timeout": 5' in _hook_entry("direct-edit-guard.sh")
