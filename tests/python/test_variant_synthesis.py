"""실제 Git worktree에서 종합 실행과 중단 복구를 검증한다."""
import importlib
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core/scripts"))
from variant_state import fingerprint, write_json
from tests.python.test_variant_review_contract import make_review


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def api():
    assert (ROOT / "core/scripts/variant_synthesis.py").exists(), "synthesis API missing"
    return importlib.import_module("variant_synthesis")


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "service.py").write_text("def validate(value):\n    return bool(value)\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    commit = git(root, "rev-parse", "HEAD")
    candidate = tmp_path / "candidate"
    git(root, "worktree", "add", "-qb", "candidate", str(candidate), commit)
    state = tmp_path / "state"
    state.mkdir()
    task = tmp_path / "candidate-task"
    task.mkdir()
    document = make_review(commit)
    inputs = {"input_hash": document["input_hash"], "base_commit": commit,
              "base_task": document["base_task"], "candidates": [{
                  "task": {"task_id": "v1", "status": "completed", "task_dir": str(task),
                           "project_root": str(candidate), "base_project_root": str(root),
                           "branch": "candidate"}, "commit": commit,
                  "base_commit": commit, "evidence": {}}]}
    write_json(state / "session.json", {"session_id": "test", "tasks": ["v1"],
                                        "selected_task_id": None})
    write_json(state / "variant-review.json", document)
    write_json(state / "variant-review-state.json", {"status": "completed",
               "input_hash": inputs["input_hash"], "document_hash": fingerprint(document)})
    return state, inputs, root


def test_prepare_independent_pinned_worktree_and_resume(api, setup):
    state, inputs, root = setup
    before = (state / "session.json").read_bytes()
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    assert prepared["status"] == "running"
    assert prepared["artifact_kind"] == "synthesis"
    assert git(Path(prepared["project_root"]), "rev-parse", "HEAD") == inputs["base_commit"]
    assert prepared["branch"] == "codex/variants-test-final-1"
    assert api.prepare_synthesis(state, inputs["input_hash"], inputs)["token"] == prepared["token"]
    assert git(root, "status", "--porcelain") == ""
    assert (state / "session.json").read_bytes() == before
    assert inputs["base_task"] in (Path(prepared["task_dir"]) / "handoff.md").read_text()
    handoff_lines = (Path(prepared["task_dir"]) / "handoff.md").read_text().splitlines()
    assert "MODE: supervisor" in handoff_lines
    assert "VARIANT_SYNTHESIS: true" in handoff_lines
    assert "MODE: variant-synthesis" not in handoff_lines
    assert json.loads((Path(prepared["task_dir"]) / "pipeline.json").read_text())["planning_required"] is True


def test_release_invalidates_token_and_preserves_attempt(api, setup):
    state, inputs, _ = setup
    first = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    api.release_synthesis(state, first["token"])
    second = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    assert second["token"] != first["token"]
    assert Path(first["project_root"]).exists()
    with pytest.raises(ValueError):
        api.release_synthesis(state, first["token"])


def test_changed_review_receipt_blocks_prepare(api, setup):
    state, inputs, _ = setup
    document = json.loads((state / "variant-review.json").read_text())
    document["decisions"][0]["compatibility"] = "changed"
    write_json(state / "variant-review.json", document)
    with pytest.raises(ValueError):
        api.prepare_synthesis(state, inputs["input_hash"], inputs)


def test_source_head_movement_preserves_pinned_synthesis(api, setup):
    state, inputs, root = setup
    api.prepare_synthesis(state, inputs["input_hash"], inputs)
    git(root, "commit", "--allow-empty", "-qm", "moved")
    assert api.synthesis_readiness(state, inputs)["next_action"] == "synthesis_in_progress"


def test_worktree_failure_is_durable_and_never_reexecuted(api, setup, monkeypatch):
    state, inputs, _ = setup
    original = api.git_output

    def fail(root, *args):
        if args[:2] == ("worktree", "add"):
            saved = json.loads((state / "variant-synthesis-state.json").read_text())
            assert saved["status"] == "preparing"
            raise ValueError("injected git failure")
        return original(root, *args)

    monkeypatch.setattr(api, "git_output", fail)
    with pytest.raises(ValueError, match="injected"):
        api.prepare_synthesis(state, inputs["input_hash"], inputs)
    assert api.synthesis_readiness(state, inputs)["status"] == "failed"
    assert api.synthesis_readiness(state, inputs)["next_action"] == "synthesis_failed"
    assert api.prepare_synthesis(state, inputs["input_hash"], inputs)["status"] == "failed"


def test_frozen_task_inputs_cannot_be_rewritten(api, setup):
    state, inputs, _ = setup
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    write_json(Path(prepared["task_dir"]) / "inputs.json", {"changed": True})
    assert api.synthesis_readiness(state, inputs)["next_action"] == "stale"


def test_candidate_dirty_change_stales_running_execution(api, setup):
    state, inputs, _ = setup
    api.prepare_synthesis(state, inputs["input_hash"], inputs)
    candidate = Path(inputs["candidates"][0]["task"]["project_root"])
    (candidate / "service.py").write_text("changed\n")
    assert api.synthesis_readiness(state, inputs)["next_action"] == "stale"


def test_failed_candidate_before_completed_keeps_evidence_without_git(api, setup, monkeypatch):
    state, inputs, root = setup
    failed_task = state / "failed-task"
    failed_task.mkdir()
    log = failed_task / "failure.log"
    log.write_text("candidate failed\n")
    inputs["candidates"].insert(0, {"task": {"task_id": "failed", "status": "failed",
         "task_dir": str(failed_task)}, "evidence": {"failure.log": hashlib.sha256(log.read_bytes()).hexdigest()}})
    # 실패 후보 리뷰 구조는 별도 계약 모듈 소유다. 여기서는 Git/증거 경계만 검사한다.
    monkeypatch.setattr(api, "validate_review", lambda document, inputs: [])
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    assert prepared["base_project_root"] == str(root.resolve())
    assert prepared["status"] == "running"
    log.write_text("changed failure evidence\n")
    assert api.synthesis_readiness(state, inputs)["next_action"] == "stale"


def test_all_failed_cannot_prepare(api, setup, monkeypatch):
    state, inputs, _ = setup
    inputs["candidates"] = [{"task": {"task_id": "failed", "status": "failed",
                             "task_dir": str(state)}, "evidence": {}}]
    monkeypatch.setattr(api, "validate_review", lambda document, inputs: [])
    with pytest.raises(ValueError, match="completed"):
        api.prepare_synthesis(state, inputs["input_hash"], inputs)
