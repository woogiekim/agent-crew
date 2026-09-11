"""최종 승인, 실제 증거 및 재작업 토큰의 회귀 검사."""
import copy
from pathlib import Path

import pytest

from tests.python.test_variant_synthesis import api, setup, git
from variant_state import read_state, write_json


def result_for(prepared, inputs):
    log = Path(prepared["task_dir"]) / "acceptance.log"
    log.write_text("acceptance passed\n")
    evidence = {"path": "service.py", "line": 1, "commit": inputs["base_commit"]}
    return {"commit": inputs["base_commit"], "implementer_id": "host-implementer",
            "reviewer_id": "host-reviewer", "verdict": "approved", "unresolved_findings": [],
            "acceptance": [{"requirement_id": "r1", "passed": True,
                            "command": "python -m pytest", "log": str(log)}],
            "decision_results": [{"decision_id": "d1", "implemented": True,
                                  "validation": {"passed": True, "command": "python -m pytest strengths",
                                                 "log": str(log)},
                                  "evidence": [evidence]}],
            "composition_checks": [{"name": "combined validation", "passed": True,
                                    "command": "python -m pytest composition", "log": str(log)}],
            "analysis": [{"unit_id": "validation", "five_w_one_h": {
                key: {"statement": "Validation contract", "basis": "observed",
                      "reason": "Pinned source", "evidence": [copy.deepcopy(evidence)]}
                for key in ("who", "when", "where", "what", "how", "why")}}]}


def test_ready_final_does_not_select_candidate_and_log_changes_stale(api, setup):
    state, inputs, _ = setup
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    result = result_for(prepared, inputs)
    before = (state / "session.json").read_bytes()
    assert api.record_synthesis_result(state, prepared["token"], result, inputs)["next_action"] == "ready_for_apply"
    assert api.final_artifact(state, inputs)["status"] == "completed"
    assert (state / "session.json").read_bytes() == before
    Path(result["acceptance"][0]["log"]).write_text("changed")
    with pytest.raises(ValueError):
        api.final_artifact(state, inputs)


def test_final_validation_fingerprint_is_stable_and_binds_evidence(api, setup):
    state, inputs, _ = setup
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    result = result_for(prepared, inputs)
    api.record_synthesis_result(state, prepared["token"], result, inputs)
    first = api.final_artifact(state, inputs)["validation_fingerprint"]
    assert len(first) == 64
    assert api.final_artifact(state, inputs)["validation_fingerprint"] == first
    changed = dict(inputs, policy_version=2)
    assert api.synthesis_readiness(state, changed)["next_action"] == "stale"


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(reviewer_id="host-implementer"),
    lambda r: r.update(verdict="needs_changes"),
    lambda r: r.update(unresolved_findings=["regression"]),
    lambda r: r.update(acceptance=[]),
    lambda r: r["acceptance"][0].update(passed=False),
    lambda r: r["acceptance"][0].update(log="missing"),
    lambda r: r.update(decision_results=[]),
    lambda r: r["decision_results"][0]["evidence"][0].update(line=99),
    lambda r: r.update(analysis=[]),
    lambda r: r["analysis"][0]["five_w_one_h"].pop("why"),
    lambda r: r["decision_results"][0].pop("validation"),
    lambda r: r["decision_results"][0]["validation"].update(passed=False),
    lambda r: r.update(composition_checks=[]),
    lambda r: r["composition_checks"][0].update(passed=False),
    lambda r: r["composition_checks"][0].update(log="missing"),
])
def test_invalid_result_retains_worktree_for_rework(api, setup, mutation):
    state, inputs, _ = setup
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    valid = result_for(prepared, inputs)
    invalid = copy.deepcopy(valid)
    mutation(invalid)
    rejected = api.record_synthesis_result(state, prepared["token"], invalid, inputs)
    assert rejected["status"] == "needs_changes"
    assert rejected["token"] == prepared["token"]
    assert rejected["last_result"] == invalid
    assert api.record_synthesis_result(state, prepared["token"], valid, inputs)["next_action"] == "ready_for_apply"


def test_final_head_or_dirty_tree_blocks_apply(api, setup):
    state, inputs, _ = setup
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    api.record_synthesis_result(state, prepared["token"], result_for(prepared, inputs), inputs)
    (Path(prepared["project_root"]) / "untracked").write_text("dirty")
    assert api.synthesis_readiness(state, inputs)["next_action"] == "stale"


def test_final_preview_validation_does_not_write_stale_receipt(api, setup):
    state, inputs, _ = setup
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    result = result_for(prepared, inputs)
    api.record_synthesis_result(state, prepared["token"], result, inputs)
    before = (state / "variant-synthesis-state.json").read_bytes()
    Path(result["acceptance"][0]["log"]).write_text("changed")
    with pytest.raises(ValueError):
        api.final_artifact(state, inputs)
    assert (state / "variant-synthesis-state.json").read_bytes() == before


def test_release_cannot_reset_validation_budget(api, setup):
    state, inputs, _ = setup
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    result = result_for(prepared, inputs)
    result["verdict"] = "needs_changes"
    for _ in range(3):
        api.record_synthesis_result(state, prepared["token"], result, inputs)
    api.release_synthesis(state, prepared["token"])
    assert api.prepare_synthesis(state, inputs["input_hash"], inputs)["status"] == "blocked"


def test_host_binding_preserved_and_enforced(api, setup):
    state, inputs, _ = setup
    prepared = api.prepare_synthesis(state, inputs["input_hash"], inputs)
    receipt = read_state(state / "variant-synthesis-state.json")
    receipt["host_id"] = "bound-host"
    write_json(state / "variant-synthesis-state.json", receipt)
    result = result_for(prepared, inputs)
    assert api.record_synthesis_result(state, prepared["token"], result, inputs)["status"] == "needs_changes"
    result["implementer_id"] = "bound-host"
    ready = api.record_synthesis_result(state, prepared["token"], result, inputs)
    assert ready["host_id"] == "bound-host"
    assert ready["next_action"] == "ready_for_apply"
