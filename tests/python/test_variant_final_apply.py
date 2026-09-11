"""최종 결과 적용은 기존 후보 선택과 분리한다."""
import sys
import types

from tests.python.test_variant_review_inputs import collector, v2, git


def final_adapter(monkeypatch, v2):
    _, _, _, _, session = v2
    selected = {**session["tasks"][0], "task_id": "synthesis-final",
                "validation_fingerprint": "validated-final"}
    module = types.ModuleType("variant_synthesis")
    module.final_artifact = lambda state, inputs: selected
    monkeypatch.setitem(sys.modules, "variant_synthesis", module)
    return selected


def test_final_apply_keeps_candidate_selection(monkeypatch, v2):
    base, candidate, state, _, session = v2
    final_adapter(monkeypatch, v2)
    code, output = collector.apply_variant(state, "main", artifact="final")
    assert code == 0, output
    assert "Final synthesis apply plan" in output
    assert "final_task_id: synthesis-final" in output
    assert "artifact: final" in output.splitlines()
    assert "selected_task_id:" not in output
    assert "selected_variant:" not in output
    assert "--artifact final --target BRANCH --confirm PLAN_HASH" in output
    plan_hash = next(line.split(": ", 1)[1] for line in output.splitlines()
                     if line.startswith("plan_hash: "))
    code, output = collector.apply_variant(state, "main", plan_hash, artifact="final")
    assert code == 0, output
    updated = collector.load_json(state / "session.json")
    assert updated["selected_task_id"] is None
    assert updated["selection_status"] == session["selection_status"]
    assert updated["tasks"] == session["tasks"]
    assert updated["applied_task_id"] == "synthesis-final"
    assert git(base, "rev-parse", "HEAD^2") == git(candidate, "rev-parse", "HEAD")


def test_final_plan_binds_validation(monkeypatch, v2):
    _, _, state, _, _ = v2
    selected = final_adapter(monkeypatch, v2)
    _, first = collector.apply_variant(state, "main", artifact="final")
    selected["validation_fingerprint"] = "new-validation"
    _, second = collector.apply_variant(state, "main", artifact="final")
    assert first != second


def test_v2_candidate_apply_cannot_bypass_synthesis(v2):
    _, _, state, _, session = v2
    session.update(selection_status="selected", selected_task_id="v1")
    collector.write_json(state / "session.json", session)
    code, output = collector.apply_variant(state, "main")
    assert code == 2
    assert "--artifact final" in output
