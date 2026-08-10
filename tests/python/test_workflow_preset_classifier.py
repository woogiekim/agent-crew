from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = REPO_ROOT / "core" / "scripts" / "workflow-preset-classifier.py"
RULE = REPO_ROOT / "core" / "rules" / "workflow-presets.md"
RUN_COMMAND = REPO_ROOT / "core" / "commands" / "run.md"


def classify(task: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(CLASSIFIER), "--task", task, "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(result.stdout)


def render_text(task: str) -> str:
    result = subprocess.run(
        [sys.executable, str(CLASSIFIER), "--task", task, "--format", "text"],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ticket_issue_id_auto_selects_ticket_resolve() -> None:
    payload = classify("ENRTC-123 처리")

    assert payload["recommended"] == "ticket-resolve"
    assert payload["confidence"] == "high"
    assert payload["auto_select"] is True
    assert payload["selection_required"] is False
    assert payload["analysis_adequacy_states"] == [
        "READY",
        "NEEDS_ANALYSIS",
        "NEEDS_USER_INPUT",
        "BLOCKED",
    ]


def test_review_fix_conflict_recommends_review_fix_and_requires_selection() -> None:
    payload = classify("ENRTC-123 리뷰에서 나온 finding 반영")

    assert payload["recommended"] == "review-fix"
    assert payload["selection_required"] is True
    assert "ticket-resolve" in payload["conflicts"]
    assert "review-fix" in [option["preset"] for option in payload["options"]]
    assert payload["caution"]


def test_empty_task_renders_workflow_aware_menu_with_plain_numbers() -> None:
    text = render_text("")

    assert "무엇을 실행할까요?" in text
    assert "1. Tracker issue id 입력" in text
    assert "2. 최근 prompt 실행" in text
    assert "3. 현재 작업 브랜치 기준으로 이어서 실행" in text
    assert "4. 직접 작업 내용 입력" in text
    assert "5. 취소" in text
    assert "①" not in text
    assert "APPROVAL_GATE" not in text


def test_ambiguous_task_renders_friendly_workflow_selection_gate() -> None:
    text = render_text("현재 작업 이어서 리뷰 반영까지")

    assert "실행할 workflow를 선택해 주세요." in text
    assert "추천:" in text
    assert "이유:" in text
    assert "주의:" in text
    assert "1." in text
    assert "APPROVAL_GATE" not in text


def test_run_command_documents_thin_workflow_preset_gate() -> None:
    text = read(RUN_COMMAND)

    assert "core/rules/workflow-presets.md" in text
    assert "workflow-preset-classifier.py" in text
    assert "selected_workflow_preset" in text
    assert "must still delegate execution to `supervisor`" in text


def test_provider_native_review_and_tracker_write_boundaries_are_preserved() -> None:
    text = read(RULE)

    assert "provider-native review" in text
    assert "review-lens metadata" in text
    assert "preview + exact approval" in text
    assert "external tracker write" in text
    assert "review-synthesis remains read-only" in text


def test_branch_naming_automation_is_excluded() -> None:
    text = read(RULE)

    assert "does not choose or mutate branch names" in text
    assert "branch naming automation is out of scope" in text
