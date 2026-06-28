"""Regression tests for Python heredocs embedded in the Codex setup script."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CODEX_SETUP = REPO_ROOT / "adapters" / "codex" / "setup.sh"


def _python_heredocs(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    heredocs: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        if "<<'PYEOF'" not in lines[index]:
            index += 1
            continue

        start = index + 1
        body: list[str] = []
        index += 1
        while index < len(lines) and lines[index] != "PYEOF":
            body.append(lines[index])
            index += 1

        heredocs.append((start + 1, "\n".join(body) + "\n"))
        index += 1

    return heredocs


def test_codex_setup_python_heredocs_compile():
    setup_text = CODEX_SETUP.read_text(encoding="utf-8")
    heredocs = _python_heredocs(setup_text)

    assert heredocs, "expected Codex setup.sh to contain Python heredocs"
    for line_number, body in heredocs:
        compile(body, f"{CODEX_SETUP}:{line_number}", "exec")
