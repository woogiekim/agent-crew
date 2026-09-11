"""고정 Git 증거를 사용하는 v2 리뷰 계약 테스트."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def make_review(commit, *, base_commit=None, input_hash=None, base_task=None):
    """통합 테스트용 최소 완전한 정본. service.py:1이 있는 실제 SHA를 전달한다."""
    document = json.loads((ROOT / "tests/fixtures/variants/review-v2.json").read_text()
                          .replace("1" * 40, commit))
    document["base_commit"] = base_commit or commit
    if input_hash is not None:
        document["input_hash"] = input_hash
    if base_task is not None:
        document["base_task"] = base_task
        document["requirements"][0]["text"] = base_task
    return document


@pytest.fixture
def api():
    path = ROOT / "core/scripts/variant_review.py"
    assert path.exists(), "variant_review contract module is not implemented"
    spec = importlib.util.spec_from_file_location("variant_review", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def review(tmp_path):
    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(tmp_path), *args], text=True
        ).strip()

    git("init", "-q")
    (tmp_path / "service.py").write_text("def validate(value):\n    return bool(value)\n")
    git("add", "service.py")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", "fixture")
    commit = git("rev-parse", "HEAD")
    document = make_review(commit)
    log = tmp_path / "result.md"
    log.write_text("acceptance passed\n")
    digest = hashlib.sha256(log.read_bytes()).hexdigest()
    inputs = {
        "input_hash": document["input_hash"], "base_task": document["base_task"],
        "base_commit": commit,
        "candidates": [{"task": {"task_id": "v1", "status": "completed",
                                "task_dir": str(tmp_path), "project_root": str(tmp_path)},
                        "commit": commit, "base_commit": commit,
                        "evidence": {"result.md": digest}}],
    }
    return document, inputs, tmp_path


def test_canonical_review_and_renderer(api, review):
    document, inputs, _ = review
    assert api.validate_review(document, inputs) == []
    rendered = api.render_review(document)
    for value in ("validation", "d1", "service.py", "who", "why",
                  "Run empty-input acceptance test.", "구조"):
        assert value in rendered


@pytest.mark.parametrize("field", ["schema_version", "input_hash", "base_task",
                                  "base_commit", "requirements", "units",
                                  "candidate_analyses", "comparison", "decisions",
                                  "semantic_review"])
def test_required_root_fields(api, review, field):
    document, inputs, _ = review
    del document[field]
    assert any(field in error for error in api.validate_review(document, inputs))


@pytest.mark.parametrize("field", ["who", "when", "where", "what", "how", "why"])
def test_missing_five_w_one_h_rejected(api, review, field):
    document, inputs, _ = review
    del document["candidate_analyses"][0]["units"][0]["five_w_one_h"][field]
    assert any(field in error for error in api.validate_review(document, inputs))


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(input_hash="b" * 64),
    lambda d: d.update(base_task="Rewritten request"),
    lambda d: d.update(base_commit="2" * 40),
    lambda d: d["units"][0].update(requirement_ids=["missing"]),
    lambda d: d["requirements"].append({"requirement_id": "r2", "text": "Uncovered"}),
    lambda d: d["candidate_analyses"][0].update(units=[]),
    lambda d: d.update(comparison=[]),
    lambda d: d["comparison"][0].update(candidate_ids=[]),
    lambda d: d.update(decisions=[]),
    lambda d: d["decisions"][0].update(source_commit="2" * 40),
    lambda d: d["decisions"][0].update(validation=" "),
    lambda d: d["semantic_review"].update(verdict="needs_changes"),
    lambda d: d["semantic_review"].update(unresolved_findings=["open"]),
    lambda d: d["candidate_analyses"].append(copy.deepcopy(d["candidate_analyses"][0])),
])
def test_invalid_contract_rejected(api, review, mutation):
    document, inputs, _ = review
    mutation(document)
    assert api.validate_review(document, inputs)


@pytest.mark.parametrize("basis", ["unknown", "not_applicable", "inferred"])
def test_nonobserved_requires_reason(api, review, basis):
    document, inputs, _ = review
    field = document["candidate_analyses"][0]["units"][0]["five_w_one_h"]["why"]
    field.update(basis=basis, reason="")
    assert api.validate_review(document, inputs)


def test_unknown_critical_rejected(api, review):
    document, inputs, _ = review
    document["candidate_analyses"][0]["units"][0]["five_w_one_h"]["how"].update(
        basis="unknown", evidence=[], reason="Algorithm unverified")
    assert api.validate_review(document, inputs)


@pytest.mark.parametrize("change", [
    {"path": "../service.py"}, {"path": "/service.py"}, {"path": "missing.py"},
    {"line": 3}, {"line": 0}, {"line": True}, {"commit": "2" * 40},
    {"task_id": "missing"},
])
def test_invalid_pinned_code_evidence(api, review, change):
    document, inputs, _ = review
    document["candidate_analyses"][0]["units"][0]["five_w_one_h"]["who"]["evidence"][0].update(change)
    assert api.validate_review(document, inputs)


def test_working_tree_does_not_replace_pinned_code(api, review):
    document, inputs, root = review
    (root / "service.py").write_text("")
    assert api.validate_review(document, inputs) == []


def test_artifact_manifest_and_bytes_must_match(api, review):
    document, inputs, root = review
    field = document["candidate_analyses"][0]["units"][0]["five_w_one_h"]["who"]
    field["evidence"] = [{"task_id": "v1", "artifact": "result.md",
                          "sha256": inputs["candidates"][0]["evidence"]["result.md"]}]
    assert api.validate_review(document, inputs) == []
    (root / "result.md").write_text("changed")
    assert api.validate_review(document, inputs)


@pytest.mark.parametrize("status", ["failed", "blocked", "cancelled", "running"])
def test_failed_candidate_cannot_be_adopted(api, review, status):
    document, inputs, _ = review
    inputs["candidates"][0]["task"]["status"] = status
    assert api.validate_review(document, inputs)


@pytest.mark.parametrize("document", ["review", None, [], {"schema_version": True}])
def test_malformed_document_returns_errors(api, review, document):
    assert api.validate_review(document, review[1])


def add_failed_candidate(document, inputs, root, *, commit=None):
    """SHA를 얻지 못한 실패 후보도 공통 단위의 진단 대상으로 유지한다."""
    candidate = {"task": {"task_id": "v2", "status": "blocked",
                          "task_dir": str(root / "failed"),
                          "project_root": str(root / "unavailable")}, "evidence": {}}
    analysis = copy.deepcopy(document["candidate_analyses"][0])
    analysis["task_id"] = "v2"
    analysis.pop("commit")
    if commit:
        candidate.update(commit=commit, base_commit=inputs["base_commit"])
        candidate["task"]["project_root"] = str(root)
        analysis["commit"] = commit
    for unit in analysis["units"]:
        unit["strengths"] = []
        unit["weaknesses"] = ["Candidate failed before implementation was verified."]
        for field in unit["five_w_one_h"].values():
            field.update(statement="Implementation unavailable", basis="unknown",
                         evidence=[], reason="Candidate execution failed.")
    inputs["candidates"].append(candidate)
    document["candidate_analyses"].append(analysis)
    document["comparison"][0]["candidate_ids"].append("v2")


@pytest.mark.parametrize("with_commit", [False, True])
def test_one_valid_and_one_failed_candidate_has_diagnostic_coverage(api, review, with_commit):
    document, inputs, root = review
    add_failed_candidate(document, inputs, root,
                         commit=inputs["base_commit"] if with_commit else None)
    assert api.validate_review(document, inputs) == []
    assert "v2" in api.render_review(document)


def test_failed_candidate_reject_decision_without_invented_sha(api, review):
    document, inputs, root = review
    add_failed_candidate(document, inputs, root)
    decision = copy.deepcopy(document["decisions"][0])
    decision.update(decision_id="d2", action="reject", source_task_id="v2",
                    five_w_one_h=document["candidate_analyses"][1]["units"][0]["five_w_one_h"])
    decision.pop("source_commit")
    document["decisions"].append(decision)
    assert api.validate_review(document, inputs) == []
    assert "d2" in api.render_review(document)


@pytest.mark.parametrize("action", ["adopt", "adapt", "retain"])
def test_failed_diagnostic_cannot_be_used_as_adoption(api, review, action):
    document, inputs, root = review
    add_failed_candidate(document, inputs, root)
    document["decisions"][0].update(action=action, source_task_id="v2")
    document["decisions"][0].pop("source_commit")
    assert api.validate_review(document, inputs)


def test_all_failed_candidates_cannot_approve_synthesis(api, review):
    document, inputs, root = review
    add_failed_candidate(document, inputs, root)
    document["candidate_analyses"] = document["candidate_analyses"][1:]
    inputs["candidates"] = inputs["candidates"][1:]
    document["comparison"][0]["candidate_ids"] = ["v2"]
    decision = document["decisions"][0]
    decision.update(action="reject", source_task_id="v2",
                    five_w_one_h=document["candidate_analyses"][0]["units"][0]["five_w_one_h"])
    decision.pop("source_commit")
    assert any("completed" in error for error in api.validate_review(document, inputs))


def test_failed_diagnostics_still_require_reason(api, review):
    document, inputs, root = review
    add_failed_candidate(document, inputs, root)
    document["candidate_analyses"][1]["units"][0]["five_w_one_h"]["how"]["reason"] = ""
    assert api.validate_review(document, inputs)


@pytest.mark.parametrize("field", ["commit", "base_commit"])
def test_completed_candidate_still_requires_pinned_sha(api, review, field):
    document, inputs, _ = review
    inputs["candidates"][0].pop(field)
    assert api.validate_review(document, inputs)


def test_completed_analysis_still_requires_commit(api, review):
    document, inputs, _ = review
    document["candidate_analyses"][0].pop("commit")
    assert api.validate_review(document, inputs)
