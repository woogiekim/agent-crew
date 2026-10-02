"""형식 검사, 작업 리뷰, 적용 가능한 개선안의 경계를 검증한다."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[2] / "core" / "scripts"


def load(name):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_execution_approval_is_not_review_evidence():
    events = load("evolution-learning-events")
    assert events.reviewer_status_for("skill_content_depth", {"approval_status": "approved"}) == "unknown"


def test_format_audit_does_not_claim_content_failure():
    audit = load("skill-content-audit")
    payload = audit.build_payload()
    assert payload["format_findings"]
    assert payload["shallow_findings"] == []
    assert all(row["content_sha256"] for row in payload["inventory"])
    assert all(row["evidence_kind"] == "static_format" for row in payload["format_findings"])


def test_analyzer_retains_static_finding_identity(tmp_path):
    analyzer = load("evolution-analyzer")
    context = tmp_path / "context"
    context.mkdir()
    finding = {"file": "tdd.md", "content_sha256": "abc", "issue_key": "missing_sections", "evidence_kind": "static_format"}
    (context / "skill-content-audit.json").write_text(json.dumps({"format_findings": [finding]}))
    signal = analyzer.skill_content_audit_signal(tmp_path)
    assert signal["format_findings"] == [finding]
    assert signal["shallow_finding_count"] == 0


def test_static_audit_events_deduplicate_across_tasks(tmp_path):
    events = load("evolution-learning-events")
    result = []
    for task_id in ("one", "two"):
        task = tmp_path / "tasks" / task_id
        task.mkdir(parents=True)
        (task / "register.json").write_text(json.dumps({"repository": "example/repo"}))
        report = task / "report.json"
        report.write_text(json.dumps({"generation_mode": "report_only", "meaningful": True,
            "observed_patterns": [{"kind": "skill_format_warning", "findings": [
                {"file": "tdd.md", "content_sha256": "abc", "issue_key": "missing_sections", "evidence_kind": "static_format"}]}]}))
        result.extend(events.build_events(tmp_path, task, report))
    assert len(result) == 2
    assert result[0]["event_id"] == result[1]["event_id"]
    assert result[0]["target_assets"] == ["tdd.md"]
    assert result[0]["content_sha256"] == "abc"

    appended = events.append_unique(tmp_path / "events.jsonl", result)
    assert appended["written"] == 1


def test_legacy_static_reports_are_investigation_not_repeated_failures(tmp_path):
    aggregate = load("evolution-proposal-aggregate")
    for task in ("one", "two"):
        context = tmp_path / "tasks" / task / "context"
        context.mkdir(parents=True)
        (context / "evolution-report.json").write_text(json.dumps({
            "generation_mode": "report_only", "observed_patterns": [{"kind": "skill_content_depth"}]}))
    proposal, = aggregate.build_proposals(tmp_path, 2)
    assert proposal["status"] == "investigation_required"
    assert proposal["occurrence_count"] == 0
    assert proposal["observation_count"] == 2


@pytest.mark.parametrize("field", ["target_skill", "patch_body", "evidence_refs", "expected_impact"])
def test_incomplete_patch_cannot_be_approved(tmp_path, field):
    lifecycle = load("evolution-proposal-lifecycle")
    proposal = {"candidate_id": "patch", "proposal_type": "patch_existing_skill", "status": "approval_required",
        "target_skill": "tdd.md", "patch_body": "Concrete rule", "evidence_refs": ["review.md"], "expected_impact": "Prevent missing red test"}
    del proposal[field]
    path = lifecycle.proposals_path(tmp_path)
    lifecycle.write_json(path, {"proposals": [proposal]})
    before = path.read_bytes()
    args = argparse.Namespace(state_dir=tmp_path, candidate_id="patch", approved_by="tester", reason="reviewed")
    assert lifecycle.cmd_approve(args) == 2
    assert path.read_bytes() == before


def test_ready_patch_can_be_approved(tmp_path):
    lifecycle = load("evolution-proposal-lifecycle")
    proposal = {"candidate_id": "patch", "proposal_type": "patch_existing_skill", "status": "approval_required",
        "target_skill": "tdd.md", "patch_body": "Concrete rule", "evidence_refs": ["review.md"], "expected_impact": "Prevent missing red test"}
    lifecycle.write_json(lifecycle.proposals_path(tmp_path), {"proposals": [proposal]})
    args = argparse.Namespace(state_dir=tmp_path, candidate_id="patch", approved_by="tester", reason="reviewed")
    assert lifecycle.cmd_approve(args) == 0


def test_legacy_incomplete_approval_cannot_apply(tmp_path):
    apply = load("evolution-proposal-apply")
    skill = tmp_path / "tdd.md"
    skill.write_text("Original")
    proposals = tmp_path / "proposals.json"
    proposals.write_text(json.dumps({"proposals": [{"candidate_id": "old", "proposal_type": "patch_existing_skill",
        "status": "approved", "target_skill": "tdd.md", "patch_body": "Unsubstantiated patch"}]}))
    result = apply.apply_proposals(proposals, tmp_path, tmp_path / "requests")
    assert not result["applied"]
    assert skill.read_text() == "Original"


def test_status_does_not_advertise_incomplete_legacy_patch_as_approval(tmp_path):
    lifecycle = load("evolution-proposal-lifecycle")
    path = lifecycle.proposals_path(tmp_path)
    lifecycle.write_json(path, {"proposals": [{"candidate_id": "old", "proposal_type": "patch_existing_skill",
        "status": "approval_required", "target_asset": "skill_content_depth", "occurrence_count": 6}]})
    before = path.read_bytes()
    rendered = lifecycle.render_status(path, 10)
    assert "status: investigation_required" in rendered
    assert "6 observations" in rendered
    assert "6 tasks" not in rendered
    assert path.read_bytes() == before


@pytest.mark.parametrize("changed_field", ["file", "content_sha256", "issue_key"])
def test_static_event_identity_distinguishes_file_version_and_problem(tmp_path, changed_field):
    events = load("evolution-learning-events")
    (tmp_path / "register.json").write_text(json.dumps({"repository": "example/repo"}))
    finding = {"file": "tdd.md", "content_sha256": "abc", "issue_key": "missing_sections"}
    report = {"generation_mode": "report_only", "meaningful": True,
        "observed_patterns": [{"kind": "skill_format_warning", "findings": [finding]}]}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    first, = events.build_events(tmp_path, tmp_path, path)
    finding[changed_field] = "different"
    path.write_text(json.dumps(report))
    second, = events.build_events(tmp_path, tmp_path, path)
    assert first["event_id"] != second["event_id"]


def test_format_only_reports_never_promote_patch(tmp_path):
    analyzer = load("evolution-analyzer")
    aggregate = load("evolution-proposal-aggregate")
    for task_id in ("one", "two"):
        task = tmp_path / "tasks" / task_id
        context = task / "context"
        context.mkdir(parents=True)
        (task / "register.json").write_text(json.dumps({"task_id": task_id}))
        (context / "skill-content-audit.json").write_text(json.dumps({"format_findings": [
            {"file": "tdd.md", "content_sha256": "abc", "issue_key": "missing_sections"}]}))
        report = analyzer.build_report(tmp_path, task)
        assert report["rejected_candidates"] == []
        assert [pattern["kind"] for pattern in report["observed_patterns"]] == ["skill_format_warning"]
        (context / "evolution-report.json").write_text(json.dumps(report))
    assert aggregate.build_proposals(tmp_path, 2) == []


def test_static_audit_does_not_erase_independent_behavior_signal():
    aggregate = load("evolution-proposal-aggregate")
    keys = aggregate.proposal_keys({"observed_patterns": [
        {"kind": "skill_content_depth"}, {"kind": "retry"}]})
    assert keys == ["retry", "skill_content_depth"]


def test_prepared_investigation_becomes_approval_ready_without_auto_approval():
    evidence = load("evolution_evidence")
    proposal = {"proposal_type": "patch_existing_skill", "status": "investigation_required",
        "target_skill": "tdd.md", "patch_body": "Concrete rule", "evidence_refs": ["review.md"],
        "expected_impact": "Prevent missing red test", "readiness_gaps": ["patch_body"]}
    evidence.classify_proposal(proposal)
    assert proposal["status"] == "approval_required"
    assert "readiness_gaps" not in proposal
    proposal["status"] = "approved"
    evidence.classify_proposal(proposal)
    assert proposal["status"] == "approved"
