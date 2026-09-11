"""native handoff placeholder는 승인된 계획의 재개 상태가 아니다."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("pipeline,expected,code", [
    (None, "fresh", 0),
    ({"planning_required": True, "stages": ["supervisor"], "completed_stages": 0}, "fresh", 0),
    ({"stages": ["backend", "reviewer"], "completed_stages": 1}, "resume", 0),
    ({"stages": ["supervisor"], "completed_stages": 0}, "resume", 0),
    ({"planning_required": True, "stages": ["backend"], "completed_stages": 1}, "", 2),
    ({"planning_required": "true", "stages": ["supervisor"]}, "", 2),
    ([], "", 2),
])
def test_start_mode_is_deterministic_and_read_only(tmp_path, pipeline, expected, code):
    path = tmp_path / "pipeline.json"
    if pipeline is not None:
        path.write_text(json.dumps(pipeline))
    before = path.read_bytes() if path.exists() else None
    result = subprocess.run([sys.executable, str(ROOT / "core/scripts/supervisor-start-mode.py"),
                             "--pipeline", str(path)], text=True, capture_output=True)
    assert result.returncode == code, result.stderr
    assert result.stdout.strip() == expected
    assert (path.read_bytes() if path.exists() else None) == before


def test_supervisor_uses_start_mode_before_resume_skip():
    bootstrap = (ROOT / "core/agents/supervisor-bootstrap.md").read_text()
    index = (ROOT / "core/agents/supervisor.md").read_text()
    assert "supervisor-start-mode.py" in bootstrap
    assert 'if [ "${START_MODE}" = "resume" ]' in bootstrap
    assert "planning_required: true" in index


def test_quality_gate_rejects_unplanned_handoff(tmp_path):
    path = tmp_path / "pipeline.json"
    path.write_text(json.dumps({"planning_required": True, "stages": ["supervisor"],
                                "task": "inspect docs", "completed_stages": 0}))
    result = subprocess.run([sys.executable, str(ROOT / "core/scripts/pipeline-quality-plan-check.py"),
                             "--pipeline", str(path), "--format", "json"],
                            text=True, capture_output=True)
    document = json.loads(result.stdout)
    assert "unplanned_handoff" in document["failures"]
    assert document["passed"] is False


def test_variants_child_bridge_preserves_logical_roles_and_identity():
    command = (ROOT / "core/commands/variants.md").read_text()
    for marker in ("WAITING_FOR_CHILD", "request_id", "definition_path", "project_root",
                   "task_dir", "실제 host ID", "중복 위임", "inline 구현", "create_thread"):
        assert marker in command


def test_supervisor_does_not_advertise_removed_status_collect():
    bootstrap = (ROOT / "core/agents/supervisor-bootstrap.md").read_text()
    assert "crew:status --collect" not in bootstrap


@pytest.mark.parametrize("path,heading,conditional,forbidden,general", [
    ("core/agents/analyst.md", "### Step 7.6", "입력에 `VARIANT_SYNTHESIS: true`가 있으면",
     "`MODE: variant-synthesis`로 대체하지 않는다", "일반 analyst handoff에는 이 플래그를 추가하지 않는다"),
    ("core/agents/skills/pipeline-planning.md", "## Handoff Document Authoring", "해당 경우에만",
     "`MODE: variant-synthesis`로 바꾸지 않는다", "일반 계획에는 추가하지 않는다"),
])
def test_analyst_preserves_synthesis_handoff_mode(path, heading, conditional, forbidden, general):
    instructions = (ROOT / path).read_text().split(heading, 1)[1].split("\n##", 1)[0]
    assert "VARIANT_SYNTHESIS: true" in instructions
    assert "MODE: supervisor" in instructions
    assert conditional in instructions
    assert forbidden in instructions
    assert general in instructions
