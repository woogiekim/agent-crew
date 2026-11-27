"""Regression checks for task-scoped memory recall ownership."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BOOTSTRAP = REPO_ROOT / "core" / "agents" / "supervisor-bootstrap.md"
STAGES = REPO_ROOT / "core" / "agents" / "supervisor-stages.md"
ANALYST = REPO_ROOT / "core" / "agents" / "analyst.md"
STAGE_ROLES = (
    "backend", "frontend", "devops", "reviewer", "designer", "requirements",
    "planner", "test-writer", "documenter", "resolver",
)


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


@pytest.mark.parametrize("role", STAGE_ROLES)
def test_stage_memory_block_reads_task_context_without_replacing_it(tmp_path, role):
    role_doc = _text(REPO_ROOT / "core" / "agents" / f"{role}.md")
    block = re.search(r"## Before Work — Recall from Memory\n\n```bash\n(.*?)\n```", role_doc, re.S)
    assert block
    task = tmp_path / "task"
    context = task / "context"
    context.mkdir(parents=True)
    memory = context / "memory.md"
    memory.write_text("검증된 교훈\n", encoding="utf-8")
    bridge = tmp_path / "agent-crew" / "bin" / "memory"
    bridge.parent.mkdir(parents=True)
    invoked = tmp_path / "memory-called"
    bridge.write_text('#!/bin/sh\ntouch "$INVOKED"\nprintf "원시 후보\\n"\n', encoding="utf-8")
    bridge.chmod(0o755)
    env = {**os.environ, "TASK_DIR": str(task), "PROJECT_ROOT": str(tmp_path),
           "AGENT_CREW_HOME": str(bridge.parents[1]), "TASK": "과제", "BRANCH": "local", "INVOKED": str(invoked)}
    env.pop("MEMORY_CONTEXT_PATH", None)

    result = subprocess.run(["bash", "-u", "-c", block[1]], env=env, capture_output=True, text=True, check=True)

    assert not invoked.exists()
    assert memory.read_text(encoding="utf-8") == result.stdout == "검증된 교훈\n"
    forwarded = context / "forwarded.md"
    forwarded.write_text("전달된 교훈\n", encoding="utf-8")

    result = subprocess.run(["bash", "-u", "-c", block[1]], env={**env, "MEMORY_CONTEXT_PATH": str(forwarded)},
                            capture_output=True, text=True, check=True)

    assert result.stdout == "전달된 교훈\n"
    assert memory.read_text(encoding="utf-8") == "검증된 교훈\n"
    memory.unlink()

    result = subprocess.run(["bash", "-u", "-c", block[1]], env=env, capture_output=True, text=True, check=True)

    assert not invoked.exists() and not memory.exists() and not result.stdout


def test_stage_prompt_links_reviewed_memory_use_to_the_analysis_decision():
    text = _text(STAGES)

    assert "ANALYSIS_CONTEXT_PATH:" in text
    assert "MEMORY_USAGE_PATH:" in text
    assert "MEMORY_RETRIEVAL_PATH:" in text
    assert "source_reviewed_candidate" in text


def test_stage_keeps_origin_available_for_candidate_absent_from_memory_md(tmp_path):
    task = tmp_path / "task"
    context = task / "context"
    context.mkdir(parents=True)
    files = {
        "memory.md": "## Memory Context\n검색 후보가 주입되지 않았다.\n",
        "analysis.md": "# 검증 범위\n근거 로그를 다시 확인한다.\n",
        "memory-usage.json": json.dumps({"decisions": [{"memory_id": "reviewed-candidate",
            "disposition": "applied", "reason_code": "source_reviewed_candidate"}]}),
        "memory-retrieval.json": json.dumps({"results": [], "provider_response": {"results": [{
            "memory_id": "reviewed-candidate", "source_path": "docs/decision.md", "source_section": "검증 근거",
        }]}}),
    }
    for name, body in files.items():
        (context / name).write_text(body, encoding="utf-8")
    block = re.search(r"#### Per-stage memory context reuse.*?```bash\n(.*?)\n```", _text(STAGES), re.S)[1]
    paths = ("MEMORY_CONTEXT_PATH", "ANALYSIS_CONTEXT_PATH", "MEMORY_USAGE_PATH", "MEMORY_RETRIEVAL_PATH")
    command = block + '\n' + 'printf "%s\\n" ' + ' '.join(f'"${{{name}:-}}"' for name in paths)
    env = {**os.environ, "TASK_DIR": str(task)}

    def forwarded():
        result = subprocess.run(["bash", "-u", "-c", command], env=env, capture_output=True, text=True, check=True)
        return result.stdout.splitlines()

    assert forwarded() == [str(context / name) for name in files]
    (context / "memory-retrieval.json").unlink()
    assert forwarded() == [str(context / "memory.md"), "", "", ""]
