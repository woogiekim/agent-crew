"""문서 계약 검사이며 실제 호스트 AI 실행 증명은 아니다."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def read(relative):
    path = ROOT / relative
    assert path.is_file(), f"missing contract: {relative}"
    return path.read_text()


def section(text, heading, following):
    assert heading in text, f"missing section: {heading}"
    return text.split(heading, 1)[1].split(following, 1)[0]


def test_v2_initial_graph_continues_after_comparison():
    run = read("core/commands/run.md")
    contract = section(run, "#### Variants v2 승인 그래프", "### 5.pre")
    for term in ("implement -> analyze/compare -> synthesize -> independent validate",
                 "variants_workflow_version: 2", "outcome_mode: synthesis", "pre_run_head",
                 "Red -> Green -> Refactor", "ready_for_apply", "초기 승인",
                 "추가 사용자 요청 없이"):
        assert term in contract


def test_nongit_v2_blocks_before_mutating_launch_and_injection():
    run = read("core/commands/run.md")
    contract = section(run, "#### Variants v2 승인 그래프", "### 5.pre")
    for term in ("nonGit", "mutating parallel launch 전에 차단", "공유 디렉터리"):
        assert term in contract
    assert "variants_workflow_version" in section(run, "#### Injection guard", "\n### ")


def test_v2_p4_and_resume_keep_orchestrator_attached():
    run = read("core/commands/run.md")
    assert "ready_for_apply" in section(run, "**P4 — Background fan-out", "**Do NOT proceed")
    variants = read("core/commands/variants.md")
    contract = section(variants, "## v2 자동 연속 실행", "## v1 중단 후 재개")
    for term in ("review_required", "review_in_progress", "synthesis_required",
                 "synthesis_in_progress", "validation_required", "ready_for_apply",
                 "추가 사용자 요청 없이"):
        assert term in contract


@pytest.mark.parametrize("stage,first,bind,last", [
    ("리뷰", "crew variants review --claim INPUT_HASH",
     "crew variants review --bind TOKEN --host-id HOST_AGENT_ID",
     "crew variants review --complete TOKEN --report CANONICAL_JSON"),
    ("종합", "crew variants synthesize --prepare INPUT_HASH",
     "crew variants synthesize --bind TOKEN --host-id HOST_AGENT_ID",
     "crew variants synthesize --complete TOKEN --result RESULT_JSON"),
])
def test_claim_bind_complete_order(stage, first, bind, last):
    contract = section(read("core/commands/variants.md"), f"### v2 {stage} 실행", "\n### ")
    assert contract.index(first) < contract.index(bind) < contract.index(last)
    assert "호스트가 반환한 실제 agent ID" in contract
    assert "실행 종료" in contract


def test_resume_never_fabricates_or_duplicates_execution():
    contract = section(read("core/commands/variants.md"),
                       "## v2 자동 연속 실행", "## v1 중단 후 재개")
    for term in ("crew variants review --release TOKEN",
                 "crew variants synthesize --release TOKEN", "stale", "중복 위임",
                 "host ID", "가짜", "prompt-only", "native CLI는 AI를 실행하지 않는다"):
        assert term in contract


def test_analysis_covers_implementation_not_only_selection():
    skill = read("core/agents/skills/variant-analysis.md")
    for term in ("후보 × 행동 단위", "호출 주체", "호출 조건", "계층", "입력", "출력",
                 "알고리즘", "trade-off", "decision", "작성 AI", "진입점", "호출자", "피호출자"):
        assert term in skill
    for key in ("who", "when", "where", "what", "how", "why"):
        assert chr(96) + key + chr(96) in skill


def test_skill_matches_canonical_contract():
    skill = read("core/agents/skills/variant-analysis.md")
    schema = json.loads(read("core/schemas/variant-review.schema.json"))
    fields = schema["required"] + [
        "statement", "basis", "evidence", "reason", "observed", "inferred", "unknown",
        "not_applicable", "task_id", "commit", "path", "line", "artifact", "sha256",
        "strengths", "weaknesses", "validation", "source_task_id", "source_commit",
    ]
    for key in fields:
        assert chr(96) + key + chr(96) in skill
    for term in ("review-v2.json", "구조 검사", "의미"):
        assert term in skill


def test_variants_reviewer_is_opt_in_and_read_only():
    reviewer = read("core/agents/reviewer.md")
    contract = section(reviewer, "## Variants 전용 모드", "## Test Checklist Review Order")
    for term in ("MODE: variant-analysis", "MODE: variant-comparison", "명시된 경우에만",
                 "variant-analysis.md", "read-only", "기존 일반 reviewer"):
        assert term in contract
    for mode in ("MODE: final", "MODE: streaming", "MODE: test-checklist"):
        assert mode in reviewer
    assert "variant-analysis.md" not in section(
        reviewer, "## Skills (Loaded Upfront)", "## Review-Profile Dispatch"
    )


def test_independent_final_validation_requires_real_results():
    skill = read("core/agents/skills/variant-analysis.md")
    for term in ("실패 후보", "unknown", "정확성", "보안", "동시성",
                 "공통 acceptance", "decision_id", "최종 diff", "실제 실행",
                 "미해결", "needs_changes"):
        assert term in skill
    contract = section(read("core/commands/variants.md"),
                       "### v2 독립 검증", "## v1 중단 후 재개")
    for term in ("reviewer_id != implementer_id", "VARIANT_SYNTHESIS: true",
                 "Red -> Green -> Refactor", "가짜"):
        assert term in contract


def test_v1_selection_and_final_apply_remain_separate():
    variants = read("core/commands/variants.md")
    legacy = section(variants, "## v1 중단 후 재개", "END_OF_FILE_SENTINEL")
    assert "review_complete" in legacy
    assert "선택을 기다린다" in legacy
    contract = section(variants, "## v2 자동 연속 실행", "## v1 중단 후 재개")
    for term in ("apply --artifact final", "별도 승인", "selected_task_id",
                 "자동 merge", "push", "v1"):
        assert term in contract


def test_v2_requires_git_and_executed_strength_and_composition_checks():
    variants = read("core/commands/variants.md")
    for term in ("읽기 전용 v2", "exit 3", "decision_results[].validation",
                 "composition_checks", "passed: true", "command", "log",
                 "SHA-256", "비어 있지 않은", "후보 apply 우회는 금지"):
        assert term in variants


def test_session_completion_is_only_final_readiness():
    variants = read("core/commands/variants.md")
    for term in ("workflow_status=implementing", "session.status=completed",
                 "no_completed_candidates", "session.status를 blocked", "resume", "manage_synthesis"):
        assert term in variants
    contract = section(variants, "## v2 자동 연속 실행", "## v1 중단 후 재개")
    assert "analysis_required" not in contract
    assert "comparing" not in contract


def test_candidate_analysis_can_create_its_own_output_before_freeze():
    for path in ("core/agents/reviewer.md", "core/agents/skills/variant-analysis.md"):
        document = read(path)
        assert "후보 완료 전" in document
        assert "자신의 지정 리뷰 산출물" in document
        assert "완료된 후보" in document


def test_terminal_synthesis_actions_stop_waiting_and_retrying():
    contract = section(read("core/commands/variants.md"),
                       "## v2 자동 연속 실행", "## v1 중단 후 재개")
    failed = section(contract, "- `synthesis_failed`:", "\n- ")
    assert "실패 이유" in failed
    assert "대기하지 않는다" in failed
    blocked = section(contract, "- `blocked`:", "\n- ")
    assert "예산" in blocked
    assert "자동 재시도하지 않는다" in blocked


def test_read_only_variants_rejected_even_in_git():
    contract = section(read("core/commands/variants.md"),
                       "## v2 자동 연속 실행", "## v1 중단 후 재개")
    for term in ("Git 저장소에서도", "--read-only --variants N", "exit 3",
                 "worktree 생성", "Git 변이", "초기에 거부"):
        assert term in contract


def test_session_scoped_artifacts_preserve_legacy_and_candidates():
    variants = read("core/commands/variants.md")
    for term in ("session.variants_dir", "STATE_DIR/variants/<session_id>",
                 "VARIANTS_DIR", "STATE_DIR/session.json", "기존 v1",
                 "없는", "후보 task_dir 밖", "native run", ".variants.lock"):
        assert term in variants
    for path in ("core/agents/reviewer.md", "core/agents/skills/variant-analysis.md",
                 "core/commands/run.md"):
        assert "session.variants_dir" in read(path)


def test_active_session_and_receipt_hash_are_not_overwritten():
    variants = read("core/commands/variants.md")
    for term in ("활성 v2", "덮어쓰기", "resume", "이전 산출물",
                 "input_hash=current", "synthesis_input_hash", "기존 receipt"):
        assert term in variants
