"""완료 장벽의 대기, 타임아웃, 실패 후보 수집을 실제 CLI로 검증한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "core/scripts/variant-session-collect.py"


def state_with_tasks(tmp_path):
    tasks = []
    for index in range(3):
        task_dir = tmp_path / f"task-{index}"
        task_dir.mkdir()
        tasks.append({"task_id": str(index), "task_dir": str(task_dir), "status": "running"})
    (tmp_path / "session.json").write_text(json.dumps({"session_type": "variants", "status": "running", "tasks": tasks}))
    return tasks


def test_wait_stays_alive_until_every_candidate_has_terminal_result(tmp_path):
    tasks = state_with_tasks(tmp_path)
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), "collect", "--state-dir", str(tmp_path),
         "--wait", "--timeout", "5", "--interval", "0.05"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        time.sleep(0.2)
        assert process.poll() is None, process.communicate()
        for task in tasks[:2]:
            (Path(task["task_dir"]) / "result.md").write_text("STATUS: completed\nSUMMARY: done\n")
        time.sleep(0.15)
        assert process.poll() is None
        (Path(tasks[2]["task_dir"]) / "result.md").write_text("STATUS: blocked\nBLOCKER: fixture failure\n")
        stdout, stderr = process.communicate(timeout=6)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()

    assert process.returncode == 0, stderr
    session = json.loads((tmp_path / "session.json").read_text())
    assert [task["status"] for task in session["tasks"]] == ["completed", "completed", "blocked"]
    assert session["selected_task_id"] is None
    assert "collection_status: complete" in stdout
    assert session["tasks"][2]["blockers"] == ["fixture failure"]


def test_wait_timeout_keeps_incomplete_session_unselected(tmp_path):
    state_with_tasks(tmp_path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "collect", "--state-dir", str(tmp_path),
         "--wait", "--timeout", "0.1", "--interval", "0.02"],
        capture_output=True, text=True, timeout=5,
    )

    assert result.returncode == 3, result.stdout + result.stderr
    assert "collection_status: timed_out" in result.stdout
    session = json.loads((tmp_path / "session.json").read_text())
    assert session["status"] == "running"
    assert session["selected_task_id"] is None


@pytest.mark.parametrize("options", [["--timeout", "1"], ["--wait", "--timeout", "nan"],
                                    ["--wait", "--interval", "0"], ["--wait", "--timeout", "-1"]])
def test_wait_rejects_unbounded_or_invalid_arguments(tmp_path, options):
    state_with_tasks(tmp_path)
    result = subprocess.run([sys.executable, str(SCRIPT), "collect", "--state-dir", str(tmp_path), *options], capture_output=True)
    assert result.returncode == 2


def test_native_collect_forwards_wait_options(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    state = home / "state/project"
    state.mkdir(parents=True)
    tasks = state_with_tasks(state)
    for task in tasks:
        (Path(task["task_dir"]) / "result.md").write_text("STATUS: completed\n")
    result = subprocess.run(
        ["bash", str(ROOT / "core/bin/crew"), "variants", "collect", "--wait", "--timeout", "1"],
        cwd=project, env={**os.environ, "PROJECT_ROOT": str(project), "AGENT_CREW_HOME": str(home)},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "collection_status: complete" in result.stdout


def test_collect_extracts_markdown_summary_without_following_test_section(tmp_path):
    tasks = state_with_tasks(tmp_path)
    (Path(tasks[0]["task_dir"]) / "result.md").write_text(
        "STATUS: completed\n\n## SUMMARY\n\n범위 파서를 구현했다.\n중복을 제거한다.\n\n## TEST\n\n테스트 출력\n")
    result = subprocess.run([sys.executable, str(SCRIPT), "collect", "--state-dir", str(tmp_path)],
                            capture_output=True, text=True)

    assert result.returncode == 0, result.stdout + result.stderr
    session = json.loads((tmp_path / "session.json").read_text())
    assert session["tasks"][0]["summary"] == "범위 파서를 구현했다. 중복을 제거한다."


@pytest.mark.parametrize("version", [1, 2])
def test_completed_candidate_clears_prior_active_blockers(tmp_path, version):
    tasks = state_with_tasks(tmp_path)
    session_path = tmp_path / "session.json"
    session = json.loads(session_path.read_text())
    session["variants_workflow_version"] = version
    session["tasks"][0].update(status="blocked", blockers=["host_child_tools_unavailable"])
    session_path.write_text(json.dumps(session))
    (Path(tasks[0]["task_dir"]) / "result.md").write_text("STATUS: completed\nSUMMARY: recovered\n")

    result = subprocess.run([sys.executable, str(SCRIPT), "collect", "--state-dir", str(tmp_path)],
                            capture_output=True, text=True)

    assert result.returncode == 0, result.stdout + result.stderr
    candidate = json.loads(session_path.read_text())["tasks"][0]
    assert candidate["status"] == "completed"
    assert candidate["blockers"] == []


@pytest.mark.parametrize("result_text,expected", [
    (None, ["prior failure"]),
    ("STATUS: completed\nBLOCKER: unresolved contract\n", ["unresolved contract"]),
])
def test_collect_preserves_unresolved_or_unavailable_blocker_evidence(tmp_path, result_text, expected):
    tasks = state_with_tasks(tmp_path)
    session_path = tmp_path / "session.json"
    session = json.loads(session_path.read_text())
    session["tasks"][0].update(status="blocked", blockers=["prior failure"])
    session_path.write_text(json.dumps(session))
    if result_text is not None:
        (Path(tasks[0]["task_dir"]) / "result.md").write_text(result_text)

    result = subprocess.run([sys.executable, str(SCRIPT), "collect", "--state-dir", str(tmp_path)],
                            capture_output=True, text=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(session_path.read_text())["tasks"][0]["blockers"] == expected
