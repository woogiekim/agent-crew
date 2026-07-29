"""Regression checks for task-scoped memory recall ownership."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BOOTSTRAP = REPO_ROOT / "core" / "agents" / "supervisor-bootstrap.md"
STAGES = REPO_ROOT / "core" / "agents" / "supervisor-stages.md"
ANALYST = REPO_ROOT / "core" / "agents" / "analyst.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_supervisor_owns_single_task_memory_search_before_analyst_spawn():
    combined = "\n".join(_text(path) for path in (BOOTSTRAP, STAGES, ANALYST))

    assert len(re.findall(r'\$\{MEMORY\}" search', combined)) == 0
    assert 'memory-recall-context.py' in _text(BOOTSTRAP)
    assert 'python3 "${MEMORY_CONTEXT_HELPER}"' in _text(BOOTSTRAP)
    assert 'AGENT_CREW_MEMORY_RECALL_MODE:-v2' in _text(BOOTSTRAP)


def test_supervisor_writes_structured_raw_and_bounded_memory_context():
    text = _text(BOOTSTRAP)

    assert 'MEMORY_RECALL_MODE="${AGENT_CREW_MEMORY_RECALL_MODE:-v2}"' in text
    assert '`{TASK_DIR}/context/memory-retrieval.json`' in text
    assert '`{TASK_DIR}/context/memory.md`' in text
    assert '--agent-role analyst' in text
    assert 'MEMORY_CONTEXT_PATH: {TASK_DIR}/context/memory.md' in text


def test_analyst_reads_supervisor_memory_context_without_search_or_overwrite():
    text = _text(ANALYST)

    assert '"${MEMORY}" search' not in text
    assert '> "${TASK_DIR}/context/memory.md"' not in text
    assert "MEMORY_CONTEXT_PATH" in text
    assert 'if [ -s "${MEMORY_CONTEXT_PATH:-}" ]; then' in text
    assert 'cat "${MEMORY_CONTEXT_PATH}"' in text


def test_stage_agents_reuse_task_memory_context_without_extra_prefetch_search():
    text = _text(STAGES)

    assert 'search "${STAGE_AGENT} ${TASK}"' not in text
    assert 'echo "${MEM_CONTEXT}" > "${TASK_DIR}/context/memory.md"' not in text
    assert 'if [ -s "${TASK_DIR}/context/memory.md" ]; then' in text
    assert "MEMORY_CONTEXT_PATH:" in text
