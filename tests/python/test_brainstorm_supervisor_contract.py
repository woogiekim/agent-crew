"""Supervisor prompt contracts from the approved Brainstorm design and Task 4."""

from pathlib import Path
import json
import os
import re
import runpy
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "core/agents/supervisor-bootstrap.md"
SUPERVISOR = REPO_ROOT / "core/agents/supervisor.md"


def section(start: str, end: str) -> str:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    return text.split(start, 1)[1].split(end, 1)[0]


def test_success_case_contract_classification_surrounds_requirements_before_planning():
    sut = BOOTSTRAP.read_text(encoding="utf-8")

    assert sut.index("--stage preliminary") < sut.index("#### Phase 1a: Requirement Collection Gate")
    assert sut.index("#### Phase 1a: Requirement Collection Gate") < sut.index("--stage final")
    assert sut.index("--stage final") < sut.index("#### Phase 1c: Analyst")


def test_success_case_contract_cli_uses_raw_positional_task_and_final_evidence():
    sut = BOOTSTRAP.read_text(encoding="utf-8")
    commands = re.findall(r'python3 "\$\{AGENT_CREW_HOME\}/scripts/brainstorm-classification.py".*?(?=\n```)', sut, re.DOTALL)

    assert len(commands) == 2
    for command in commands:
        assert '-- "${TASK}"' in command
        assert '--task ' not in command
        assert '--evidence-file' in command
    assert '--requirements-file "${TASK_DIR}/context/requirements.md"' in commands[1]
    assert '--semantic-file "${TASK_DIR}/context/brainstorm-semantic.json"' in commands[1]


def test_success_case_audit_classification_displays_evidence_and_preserves_both_results():
    sut = BOOTSTRAP.read_text(encoding="utf-8")

    for token in ("BRAINSTORM_CLASSIFICATION:", "REASON:", "PROCESS:", "raw_input_hash",
                  "brainstorm-preliminary-result.json", "brainstorm-final-result.json",
                  "brainstorm-semantic-response.md", "classifier_version"):
        assert token in sut
    assert "preliminary/final" in sut
    assert "원문 그대로" in sut


def test_boundary_case_contract_precollected_requirements_do_not_skip_brainstorm():
    sut = section("##### Case A — `REQUIREMENTS` is present", "##### Case B")

    assert "requirements.md" in sut
    assert "Phase 1b: Brainstorm" in sut
    assert "분류나 설계를 생략하지 않는다" in sut


def test_success_case_contract_preliminary_class_controls_interview_depth():
    sut = section("#### Phase 1a: Requirement Collection Gate", "#### Phase 1b: Brainstorm")

    assert "Architectural" in sut and "MODE: deep_interview" in sut
    assert "질문 한 개" in sut
    assert "Bounded" in sut and "MODE: single_round" in sut
    assert "grouped structured interaction" in sut


def test_failure_case_dependency_classifier_failure_is_visible_and_blocks():
    sut = section("#### Phase 1a preliminary classification", "#### Phase 1c: Analyst")

    assert 'log_progress "DEGRADED"' in sut
    assert "brainstorm_classification_failed" in sut
    assert "자동으로 Bounded" in sut
    assert "readiness: BLOCKED" in sut


def test_success_case_contract_architectural_questions_are_strictly_sequential():
    sut = section("##### Architectural dialogue", "##### Design generation")

    assert "one active question per task" in sut
    assert "active_question_id" in sut
    assert "MODE=next_question" in sut
    assert sut.index("응답을 저장") < sut.index("다음 MODE=next_question")
    assert "MODE=compare" in sut
    assert "고정 질문 수" in sut


def test_success_case_contract_bounded_questions_form_one_grouped_interaction():
    sut = section("##### Bounded dialogue", "##### Architectural dialogue")

    assert "grouped structured interaction" in sut
    assert "active_question_id" in sut
    assert "atomic" in sut
    assert "고영향" in sut


def test_boundary_case_idempotency_persistence_precedes_next_question():
    sut = section("##### Artifact persistence", "##### Spike probe")

    for token in ("idempotency_key", "answered_at", "selected_option_id", "option_id",
                  "section_acknowledgements", "acknowledged_at", "os.replace"):
        assert token in sut
    assert "동일 키" in sut and "재사용" in sut
    assert "최종 설계 승인" in sut
    assert "원문" in sut


def test_success_case_contract_spike_stops_with_findings_without_implementation():
    sut = section("##### Spike probe", "##### Bounded dialogue")

    assert "probe contract" in sut
    assert "acknowledgement" in sut
    assert "result.md" in sut
    assert "SPIKE_COMPLETED" in sut
    assert "Phase 1c" in sut and "Phase 2" in sut
    assert "새 분류" in sut


def test_failure_case_validation_design_requires_refinement_before_advancing():
    sut = section("##### Design validation", "#### Phase 1c: Analyst")

    for token in ("unfinished markers", "contradictions", "scope overflow",
                  "blocking unknowns", "MODE=design", "ready_for_approval"):
        assert token in sut
    assert "brainstorm_design_invalid" in sut
    assert "section_acknowledgements" in sut
    assert "Approval Service" in sut
    assert "approval_status" not in sut


def test_success_case_audit_register_phases_and_brainstorm_events_are_published():
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    sut = SUPERVISOR.read_text(encoding="utf-8")

    assert "register_update current_phase phase_1b_brainstorm" in bootstrap
    assert "register_update current_phase phase_1c_plan" in bootstrap
    for field in ("brainstorm_classification_path", "brainstorm_dialogue_path", "brainstorm_design_path"):
        assert field in bootstrap
    for event in ("BRAINSTORM_CLASSIFICATION", "BRAINSTORM_QUESTION", "BRAINSTORM_DESIGN_READY", "SPIKE_COMPLETED", "DEGRADED"):
        assert f"`{event}`" in sut
    assert "Phase 1b: Brainstorm" in sut
    assert "사전 수집" in sut


def semantic_gate_script() -> str:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    match = re.search(r"##### Semantic response gate\n.*?```bash\n(.*?)\n```", text, re.DOTALL)
    assert match, "final classification needs an executable semantic response gate"
    assert match.end() < text.index("--stage final")
    return match.group(1)


def semantic_response() -> dict:
    return {
        "mode": "classify",
        "classification": "Bounded",
        "evidence": [{"source": "context/requirements.md", "finding": "기존 책임 경계 유지"}],
        "unresolved": [],
        "readiness": "READY",
    }


def run_semantic_gate(tmp_path: Path, response: dict) -> subprocess.CompletedProcess:
    context = tmp_path / "context"
    context.mkdir()
    semantic_path = context / "brainstorm-semantic.json"
    original = json.dumps(response, ensure_ascii=False)
    semantic_path.write_text(original, encoding="utf-8")
    script = """
log_progress() { printf '%s %s\\n' "$1" "$2"; }
register_update() { printf '%s %s\\n' "$1" "$2"; }
phase_done() { :; }
""" + semantic_gate_script() + "\nprintf 'CLASSIFIER_REACHED\\n'\n"

    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "TASK_DIR": str(tmp_path), "MUTATION_SCOPE": "read_only",
             "PATH": f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"},
    )

    assert semantic_path.read_text(encoding="utf-8") == original
    return result


@pytest.mark.parametrize("field,value", [
    ("classification", None),
    ("classification", "Unknown"),
    ("classification", ["Bounded"]),
    ("evidence", None),
    ("evidence", "repository evidence"),
    ("evidence", [{}]),
    ("evidence", [{"source": "", "finding": "scope"}]),
    ("evidence", [{"source": "file:1", "finding": 42}]),
    ("mode", None),
    ("mode", "design"),
    ("readiness", None),
    ("readiness", "BLOCKED"),
    ("unresolved", None),
    ("unresolved", "Unknown"),
])
def test_failure_case_contract_invalid_semantic_response_blocks_before_classifier(tmp_path, field, value):
    response = semantic_response()
    if value is None:
        del response[field]
    else:
        response[field] = value

    result = run_semantic_gate(tmp_path, response)

    assert result.returncode != 0
    assert "DEGRADED" in result.stdout
    assert "brainstorm_classification_failed" in result.stdout
    assert "CLASSIFIER_REACHED" not in result.stdout
    assert "STATUS: blocked" in (tmp_path / "result.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("classification", ["Spike", "Bounded", "Architectural"])
def test_success_case_contract_valid_semantic_response_reaches_classifier_unchanged(tmp_path, classification):
    response = semantic_response()
    response["classification"] = classification

    result = run_semantic_gate(tmp_path, response)

    assert result.returncode == 0
    assert "CLASSIFIER_REACHED" in result.stdout
    assert "DEGRADED" not in result.stdout
    assert not (tmp_path / "result.md").exists()


def test_success_case_contract_architectural_design_gate_precedes_analyst():
    sut = section("##### Architectural design approval", "#### Phase 1c: Analyst")

    assert "approval_kind: architectural_design" in sut
    assert "approved design_hash" in sut
    assert "Supervisor/orchestrator" in sut
    assert "decision_at" in sut and "idempotency_key" in sut
    assert "PRD/pipeline" in sut


def test_success_case_contract_bounded_gate_binds_hashes_in_one_interaction():
    sut = section("### Phase 1d: Plan Approval Gate", "### Phase 1.5:")

    assert "approval_kind: bounded_combined" in sut
    assert "bound_fields.execution_plan_hash" in sut
    assert "bound_fields.classification_hash" in sut
    assert "한 번의 structured interaction" in sut
    assert "approval.md" in sut and "APPROVED" in sut
    assert "approval_kind: architectural_execution" in sut
    assert "byte-for-byte" in sut
    assert "design_decision_id" in sut


def test_success_case_contract_downgrade_preserves_classification_and_action_gates():
    sut = section("##### Informed downgrade", "##### Architectural design approval")

    for token in ("automatic classification", "evidence", "skipped design steps", "expected risks",
                  "affected boundaries", "override: Bounded", "approval_kind: user_downgrade",
                  "downgrade changes brainstorming ceremony only", "Phase 2.5 remains required"):
        assert token in sut
    assert "final: Architectural" in sut
    assert "external-write" in sut


def test_success_case_contract_hash_gate_is_shared_by_resume_and_phase_boundaries():
    sut = BOOTSTRAP.read_text(encoding="utf-8")

    assert "모든 phase boundary" in sut
    assert "canonical_hash" in sut
    assert "BRAINSTORM_APPROVAL_INVALIDATED" in sut
    assert "BRAINSTORM_RESUME" in SUPERVISOR.read_text(encoding="utf-8")
    assert "skip Phases 1a, 1b, 1c, 1d, and 1.5 entirely" not in sut


def workflow_gate_script() -> str:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    match = re.search(r"#### Brainstorm approval and resume gate\n.*?```bash\n(.*?)\n```", text, re.DOTALL)
    assert match, "resume must execute the approval/hash gate before trusting a pipeline"
    return match.group(1)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def workflow_fixture(tmp_path: Path, classification: str = "Architectural") -> dict:
    context = tmp_path / "context"
    context.mkdir()
    write_json(context / "brainstorm-classification.json", {
        "schema_version": 1, "task_id": "20260920-120000-0", "raw_input_hash": "a" * 64,
        "preliminary": classification, "final": classification, "classifier_version": 1,
        "status": "final", "rule_result": {"classification": classification},
        "semantic_result": {"classification": classification}, "resolution": "semantic_confirmed",
    })
    write_json(context / "brainstorm-dialogue.json", {
        "schema_version": 1, "task_id": "20260920-120000-0", "classification": classification,
        "status": "ready_for_approval", "questions": [], "section_acknowledgements": [],
    })
    fields = {
        "classification": classification, "downgrade": False,
        "goals": ["요청 범위 구현"], "non_goals": ["외부 게시"], "interfaces": ["unchanged"],
        "responsibility_boundaries": ["existing"], "data_model": [], "repositories": ["repo"],
        "modules": ["core"], "security_risks": [], "operational_risks": [],
        "pipeline": ["backend", "reviewer"],
    }
    write_workflow_design(tmp_path, fields)
    return fields


def write_workflow_design(tmp_path: Path, fields: dict, display: str = "설계 설명") -> None:
    (tmp_path / "context/brainstorm-design.md").write_text(
        f"# 설계\n{display}\n<!-- brainstorm-bound-fields -->\n```json\n"
        + json.dumps(fields, ensure_ascii=False) + "\n```\n", encoding="utf-8",
    )


def workflow_pipeline(tmp_path: Path) -> dict:
    pipeline = {"task": "요청 범위 구현", "stages": [["backend"], ["reviewer"]],
                "completed_stages": 0, "stage_agent_status": {}, "needs_creation": []}
    write_json(tmp_path / "pipeline.json", pipeline)
    return pipeline


def run_workflow_gate(tmp_path: Path) -> tuple[dict, str]:
    result = subprocess.run(
        ["bash", "-c", workflow_gate_script()], capture_output=True, text=True,
        env={**os.environ, "TASK_DIR": str(tmp_path), "AGENT_CREW_HOME": str(REPO_ROOT / "core"),
             "PATH": f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout), result.stderr


def workflow_decision(tmp_path: Path, fields: dict, kind: str, status: str = "approved") -> dict:
    gate, _ = run_workflow_gate(tmp_path)
    record = {
        "decision_id": f"{kind}-1", "approval_kind": kind, "status": status,
        "design_hash": gate["design_hash"],
        "bound_fields": {**fields, "classification_hash": gate["classification_hash"]},
        "created_at": "2026-09-20T00:00:00Z",
    }
    if kind == "bounded_combined":
        record["bound_fields"]["execution_plan_hash"] = gate["execution_plan_hash"]
    if status == "approved":
        record.update(decision_at="2026-09-20T00:01:00Z", idempotency_key=f"{kind}-response-1")
    approval_path = tmp_path / "context/brainstorm-approval.json"
    approval = json.loads(approval_path.read_text()) if approval_path.exists() else {
        "schema_version": 1, "task_id": "20260920-120000-0", "decisions": [],
    }
    approval["decisions"].append(record)
    write_json(approval_path, approval)
    return record


def test_success_case_workflow_question_resume_preserves_active_question(tmp_path):
    workflow_fixture(tmp_path)
    dialogue_path = tmp_path / "context/brainstorm-dialogue.json"
    dialogue = json.loads(dialogue_path.read_text())
    dialogue.update(status="waiting_for_input", active_question_id="q-1", questions=[{
        "question_id": "q-1", "status": "pending", "prompt": "경계?",
    }])
    write_json(dialogue_path, dialogue)
    before = dialogue_path.read_bytes()

    gate, _ = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "phase_1b_question"
    assert gate["active_question_id"] == "q-1"
    assert dialogue_path.read_bytes() == before


def test_success_case_workflow_final_design_approval_resume_is_exact(tmp_path):
    fields = workflow_fixture(tmp_path)
    workflow_decision(tmp_path, fields, "architectural_design", "pending")
    approval_path = tmp_path / "context/brainstorm-approval.json"
    before = approval_path.read_bytes()

    pending, _ = run_workflow_gate(tmp_path)

    assert pending["resume_at"] == "phase_1b_design_approval"
    assert approval_path.read_bytes() == before

    approval = json.loads(before)
    approval["decisions"][0].update(status="approved", decision_at="now", idempotency_key="answer-1")
    write_json(approval_path, approval)

    approved, _ = run_workflow_gate(tmp_path)

    assert approved["resume_at"] == "phase_1c_plan"
    assert approved["approved_design_hash"] == approved["design_hash"]
    assert not (tmp_path / "pipeline.json").exists()


def test_success_case_workflow_downgrade_keeps_automatic_classification(tmp_path):
    fields = workflow_fixture(tmp_path)
    fields["downgrade"] = {"override": "Bounded", "automatic_classification": "Architectural",
                           "skipped_steps": ["section_review"], "risks": ["less design review"],
                           "affected_boundaries": ["workflow"], "reason": "user request"}
    write_workflow_design(tmp_path, fields)
    before = (tmp_path / "context/brainstorm-classification.json").read_bytes()
    workflow_decision(tmp_path, fields, "user_downgrade")

    gate, _ = run_workflow_gate(tmp_path)

    assert gate["effective_classification"] == "Bounded"
    assert gate["resume_at"] == "phase_1c_plan"
    assert (tmp_path / "context/brainstorm-classification.json").read_bytes() == before
    assert not (tmp_path / "context/approval.md").exists()


@pytest.mark.parametrize("field", [
    "goals", "non_goals", "interfaces", "responsibility_boundaries", "data_model",
    "repositories", "modules", "security_risks", "operational_risks", "pipeline", "downgrade",
])
def test_failure_case_workflow_changed_bound_field_invalidates_approval(tmp_path, field):
    fields = workflow_fixture(tmp_path)
    original = workflow_decision(tmp_path, fields, "architectural_design")
    original_bytes = json.dumps(original, sort_keys=True).encode()
    fields[field] = True if field == "downgrade" else ["changed"]
    write_workflow_design(tmp_path, fields)

    gate, events = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "phase_1b_design"
    assert "BRAINSTORM_APPROVAL_INVALIDATED" in events
    approval = json.loads((tmp_path / "context/brainstorm-approval.json").read_text())
    assert json.dumps(approval["decisions"][0], sort_keys=True).encode() == original_bytes
    invalidation = approval["decisions"][-1]
    assert invalidation["approval_kind"] == "approval_invalidation"
    assert invalidation["status"] == "invalidated"
    assert invalidation["bound_fields"]["invalidates_decision_id"] == original["decision_id"]
    assert invalidation["bound_fields"]["previous_hashes"]["design_hash"] == original["design_hash"]
    assert invalidation["bound_fields"]["current_hashes"]["design_hash"] == gate["design_hash"]
    saved_bytes = (tmp_path / "context/brainstorm-approval.json").read_bytes()
    repeated, repeated_events = run_workflow_gate(tmp_path)
    assert repeated["resume_at"] == "phase_1b_design"
    assert repeated["approved_design_hash"] is None
    assert "BRAINSTORM_APPROVAL_INVALIDATED" not in repeated_events
    assert (tmp_path / "context/brainstorm-approval.json").read_bytes() == saved_bytes


def test_failure_case_workflow_promotion_invalidates_bounded_approval(tmp_path):
    fields = workflow_fixture(tmp_path, "Bounded")
    workflow_pipeline(tmp_path)
    workflow_decision(tmp_path, fields, "bounded_combined")
    path = tmp_path / "context/brainstorm-classification.json"
    classification = json.loads(path.read_text())
    classification["final"] = "Architectural"
    write_json(path, classification)

    gate, events = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "phase_1b_dialogue"
    assert gate["effective_classification"] == "Architectural"
    assert "BRAINSTORM_APPROVAL_INVALIDATED" in events


def test_success_case_workflow_combined_approval_requires_execution_signal(tmp_path):
    fields = workflow_fixture(tmp_path, "Bounded")
    workflow_pipeline(tmp_path)
    record = workflow_decision(tmp_path, fields, "bounded_combined")

    gate, _ = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "phase_1d_plan_approval"
    assert record["bound_fields"]["classification_hash"] == gate["classification_hash"]
    assert record["bound_fields"]["execution_plan_hash"] == gate["execution_plan_hash"]
    (tmp_path / "context/approval.md").write_text("APPROVED\n", encoding="utf-8")

    approved, _ = run_workflow_gate(tmp_path)

    assert approved["resume_at"] == "phase_1_5"


def test_success_case_workflow_display_and_progress_changes_preserve_approval(tmp_path):
    fields = workflow_fixture(tmp_path, "Bounded")
    pipeline = workflow_pipeline(tmp_path)
    record = workflow_decision(tmp_path, fields, "bounded_combined")
    (tmp_path / "context/approval.md").write_text("APPROVED\n", encoding="utf-8")
    write_workflow_design(tmp_path, fields, display="표시 문구만 변경")
    pipeline.update(completed_stages=1, stage_agent_status={"1": {"backend": "completed"}})
    write_json(tmp_path / "pipeline.json", pipeline)

    gate, events = run_workflow_gate(tmp_path)

    assert gate["design_hash"] == record["design_hash"]
    assert gate["execution_plan_hash"] == record["bound_fields"]["execution_plan_hash"]
    assert gate["resume_at"] == "phase_2"
    assert "BRAINSTORM_APPROVAL_INVALIDATED" not in events


def test_failure_case_workflow_changed_plan_returns_to_plan_approval(tmp_path):
    fields = workflow_fixture(tmp_path, "Bounded")
    pipeline = workflow_pipeline(tmp_path)
    workflow_decision(tmp_path, fields, "bounded_combined")
    (tmp_path / "context/approval.md").write_text("APPROVED\n", encoding="utf-8")
    pipeline["stages"].insert(0, ["qa-owner"])
    write_json(tmp_path / "pipeline.json", pipeline)

    gate, events = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "phase_1d_plan_approval"
    assert "BRAINSTORM_APPROVAL_INVALIDATED" in events
    assert (tmp_path / "context/approval.md").read_text().strip() == "PLAN_READY"


def test_failure_case_workflow_placeholder_does_not_approve_execution(tmp_path):
    workflow_fixture(tmp_path, "Bounded")
    write_json(tmp_path / "pipeline.json", {"planning_required": True})
    (tmp_path / "context/approval.md").write_text("APPROVED\n", encoding="utf-8")

    gate, _ = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "phase_1c_plan"


def test_failure_case_workflow_unreadable_design_blocks_resume(tmp_path):
    fields = workflow_fixture(tmp_path)
    workflow_decision(tmp_path, fields, "architectural_design")
    (tmp_path / "context/brainstorm-design.md").write_text("placeholder", encoding="utf-8")

    result = subprocess.run(
        ["bash", "-c", workflow_gate_script()], capture_output=True, text=True,
        env={**os.environ, "TASK_DIR": str(tmp_path), "AGENT_CREW_HOME": str(REPO_ROOT / "core"),
             "PATH": f"{Path(sys.executable).parent}:{os.environ.get('PATH', '')}"},
    )

    assert result.returncode != 0
    assert "brainstorm_approval_state_invalid" in result.stderr


def workflow_architectural_execution(tmp_path: Path) -> dict:
    fields = workflow_fixture(tmp_path)
    workflow_pipeline(tmp_path)
    workflow_decision(tmp_path, fields, "architectural_design")
    gate, _ = run_workflow_gate(tmp_path)
    approval_path = tmp_path / "context/brainstorm-approval.json"
    approval = json.loads(approval_path.read_text())
    approval["decisions"].append({
        "decision_id": "architectural_execution-1", "approval_kind": "architectural_execution",
        "status": "approved", "design_hash": gate["design_hash"], "created_at": "2026-09-20T00:02:00Z",
        "bound_fields": {**fields, "design_decision_id": approval["decisions"][0]["decision_id"],
                         "classification_hash": gate["classification_hash"],
                         "execution_plan_hash": gate["execution_plan_hash"],
                         "approval_signal_path": "context/approval.md"},
        "decision_at": "2026-09-20T00:02:00Z", "idempotency_key": "execution-response-1",
    })
    write_json(approval_path, approval)
    (tmp_path / "context/approval.md").write_text("APPROVED\n", encoding="utf-8")
    return approval


@pytest.mark.parametrize("binding", ["design_hash", "classification_hash", "execution_plan_hash", "design_decision_id", "approval_signal_path"])
def test_failure_case_workflow_architectural_execution_binding_mismatch_holds_plan(tmp_path, binding):
    approval = workflow_architectural_execution(tmp_path)
    original_design = json.dumps(approval["decisions"][0], sort_keys=True)
    execution = approval["decisions"][1]
    if binding == "design_hash":
        execution[binding] = "b" * 64
    else:
        execution["bound_fields"][binding] = "b" * 64
    approval_path = tmp_path / "context/brainstorm-approval.json"
    write_json(approval_path, approval)

    gate, events = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "phase_1d_plan_approval"
    assert gate["approved_design_hash"] == gate["design_hash"]
    saved = json.loads(approval_path.read_text())["decisions"]
    assert json.dumps(saved[0], sort_keys=True) == original_design
    assert saved[-1]["status"] == "invalidated"
    assert "BRAINSTORM_APPROVAL_INVALIDATED" in events


def test_success_case_workflow_approval_record_validates_against_existing_schema(tmp_path):
    workflow_architectural_execution(tmp_path)
    validator = runpy.run_path(str(REPO_ROOT / "core/scripts/validate-state-schema.py"))
    schema_path = REPO_ROOT / "core/schemas/brainstorm-approval.schema.json"
    findings = validator["Findings"]()
    approval_path = tmp_path / "context/brainstorm-approval.json"

    validator["validate"](json.loads(approval_path.read_text()), json.loads(schema_path.read_text()), findings, schema_path)

    assert findings.errors == []
    gate, _ = run_workflow_gate(tmp_path)
    assert gate["resume_at"] == "phase_1_5"


def test_failure_case_workflow_architectural_execution_cancel_survives_signal_write_interruption(tmp_path):
    approval = workflow_architectural_execution(tmp_path)
    approval["decisions"][1]["status"] = "cancelled"
    write_json(tmp_path / "context/brainstorm-approval.json", approval)

    gate, _ = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "cancelled"


@pytest.mark.parametrize("decision_status,reason,expected", [
    ("pending", None, "phase_1b_downgrade"),
    ("cancelled", "keep_architectural", "phase_1b_design_approval"),
    ("cancelled", "user_cancel", "cancelled"),
])
def test_success_case_workflow_downgrade_decision_resumes_its_own_boundary(tmp_path, decision_status, reason, expected):
    fields = workflow_fixture(tmp_path)
    fields["downgrade"] = {"override": "Bounded", "automatic_classification": "Architectural",
                           "skipped_steps": ["section_review"], "risks": ["less design review"],
                           "affected_boundaries": ["workflow"], "reason": "user request"}
    write_workflow_design(tmp_path, fields)
    decision = workflow_decision(tmp_path, fields, "user_downgrade", "pending")
    approval_path = tmp_path / "context/brainstorm-approval.json"
    approval = json.loads(approval_path.read_text())
    if decision_status == "cancelled":
        approval["decisions"][0].update(status=decision_status, reason=reason,
                                         decision_at="now", idempotency_key="downgrade-response-1")
        write_json(approval_path, approval)
    before = approval_path.read_bytes()

    gate, events = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == expected
    assert gate["effective_classification"] == "Architectural"
    if decision_status == "pending":
        assert gate["pending_decision_id"] == decision["decision_id"]
    assert approval_path.read_bytes() == before
    assert "BRAINSTORM_APPROVAL_INVALIDATED" not in events
    repeated, _ = run_workflow_gate(tmp_path)
    assert repeated["resume_at"] == expected
    assert approval_path.read_bytes() == before


def test_success_case_workflow_architectural_first_dialogue_precedes_design(tmp_path):
    workflow_fixture(tmp_path)
    (tmp_path / "context/brainstorm-design.md").unlink()
    dialogue_path = tmp_path / "context/brainstorm-dialogue.json"
    dialogue = json.loads(dialogue_path.read_text())
    dialogue["status"] = "not_started"
    write_json(dialogue_path, dialogue)

    gate, _ = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "phase_1b_dialogue"
    assert gate["design_hash"] is None
    assert not (tmp_path / "pipeline.json").exists()


def test_failure_case_workflow_append_only_invalidation_prevents_reusing_restored_design(tmp_path):
    fields = workflow_fixture(tmp_path)
    workflow_decision(tmp_path, fields, "architectural_design")
    write_workflow_design(tmp_path, {**fields, "goals": ["changed"]})
    run_workflow_gate(tmp_path)
    write_workflow_design(tmp_path, fields)
    dialogue_path = tmp_path / "context/brainstorm-dialogue.json"
    dialogue = json.loads(dialogue_path.read_text())
    dialogue["status"] = "ready_for_approval"
    write_json(dialogue_path, dialogue)

    gate, _ = run_workflow_gate(tmp_path)

    assert gate["resume_at"] == "phase_1b_design_approval"
    assert gate["approved_design_hash"] is None
    history = json.loads((tmp_path / "context/brainstorm-approval.json").read_text())["decisions"]
    assert history[0]["status"] == "approved"
    assert history[-1]["approval_kind"] == "approval_invalidation"
