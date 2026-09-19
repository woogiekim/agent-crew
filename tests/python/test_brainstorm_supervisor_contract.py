"""Supervisor prompt contracts from the approved Brainstorm design and Task 4."""

from pathlib import Path
import json
import os
import re
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
