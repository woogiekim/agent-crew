"""호스트 결과와 세션 전체 완료 시점을 구분한다."""
import json
import sys
import types

from tests.python.test_variant_review_inputs import collector, v2


def test_only_ready_final_completes_session(v2, monkeypatch):
    _, _, state, _, _ = v2
    module = types.ModuleType("variant_synthesis")
    module.prepare_synthesis = lambda *args: {"status": "running", "next_action": "synthesis_in_progress"}
    module.release_synthesis = lambda *args: {"status": "released", "next_action": "synthesis_required"}
    result = {"status": "needs_changes", "next_action": "validation_required"}
    module.record_synthesis_result = lambda *args: result
    monkeypatch.setitem(sys.modules, "variant_synthesis", module)
    collector.write_json(state / "variant-synthesis-state.json", {"host_id": "implementation"})
    path = state / "result.json"
    collector.write_json(path, {"implementer_id": "implementation"})
    collector.manage_synthesis(state, None, "token", None, str(path))
    assert collector.load_json(state / "session.json")["status"] == "running"
    result.update(status="ready_for_apply", next_action="ready_for_apply")
    collector.manage_synthesis(state, None, "token", None, str(path))
    session = collector.load_json(state / "session.json")
    assert session["status"] == "completed"
    assert session["workflow_status"] == "ready_for_apply"
    assert session["selected_task_id"] is None


def test_host_binding_cannot_be_changed(v2):
    state = v2[2]
    collector.write_json(state / "variant-review-state.json", {"status": "running", "token": "t"})
    assert collector.bind_execution(state, "review", "t", "host-1")[0] == 0
    import pytest
    with pytest.raises(ValueError):
        collector.bind_execution(state, "review", "t", "host-2")


def test_resume_current_hash_is_not_shadowed_by_old_synthesis(v2, monkeypatch):
    _, _, state, _, session = v2
    current = collector.fingerprint(collector.review_inputs(session))
    report = state / "variant-review.md"
    report.write_text("review")
    document = {"checked": True}
    collector.write_json(state / "variant-review.json", document)
    import hashlib
    collector.write_json(state / "variant-review-state.json", {
        "status": "completed", "token": "t", "input_hash": current,
        "document_hash": collector.fingerprint(document),
        "report_hash": hashlib.sha256(report.read_bytes()).hexdigest()})
    module = types.ModuleType("variant_synthesis")
    module.synthesis_readiness = lambda *args: {
        "next_action": "stale", "input_hash": "old-synthesis-input"}
    monkeypatch.setitem(sys.modules, "variant_synthesis", module)
    ready = collector.review_readiness(state, session)
    assert ready["input_hash"] == current
    assert ready["synthesis_input_hash"] == "old-synthesis-input"


def test_new_session_receipts_are_scoped(v2):
    _, _, state, _, session = v2
    artifacts = state / "variants" / session["session_id"]
    artifacts.mkdir(parents=True)
    session["variants_dir"] = str(artifacts)
    collector.write_json(state / "session.json", session)
    ready = json.loads(collector.collect_until_terminal(state, 0, 1, True)[1])
    collector.manage_review(state, ready["input_hash"], None, None, None)
    assert (artifacts / "variant-review-state.json").is_file()
    assert not (state / "variant-review-state.json").exists()
