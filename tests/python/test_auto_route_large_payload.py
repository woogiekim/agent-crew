"""Regression tests for large UserPromptSubmit payloads in auto-route."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "core" / "hooks" / "auto-route.sh"


def test_auto_route_handles_large_prompt_without_argv_or_timeout_failure():
    prompt = (
        "› 해결되었는지 증명해\n\n"
        "• UserPromptSubmit hook (failed)\n"
        "  error: hook timed out after 5s\n\n"
    ) * 20_000
    payload = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt}, ensure_ascii=False)

    started = time.monotonic()
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        input=payload,
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 5
    assert "Argument list too long" not in result.stderr
    assert result.stderr == ""
    assert result.stdout == ""
