"""리뷰 표현 지침의 원본과 업데이트 후 사용자 자산 보존을 검증한다."""

from pathlib import Path
import os
import subprocess


ROOT = Path(__file__).resolve().parents[2]
COMMANDS = (
    "review", "generic-review", "post-audit", "mr-review-rate", "mr-review-note",
    "review-followup", "review-retrospective", "review-synthesis", "parity-check",
)


def test_review_commands_and_codex_entrypoints_have_durable_sources():
    for name in COMMANDS:
        command = ROOT / "core/user/commands" / f"{name}.md"
        wrapper = ROOT / "adapters/codex/skill" / name / "SKILL.md"

        assert command.is_file(), name
        assert "core/rules/review-method-comparison.md" in command.read_text(), name
        assert wrapper.is_file(), name
        assert f"~/.agent-crew/commands/{name}.md" in wrapper.read_text(), name


def test_note_source_keeps_required_verification_and_mr_state():
    text = (ROOT / "core/user/commands/mr-review-note.md").read_text()

    for required in (
        "#### 방법별 비교", "#### 검증 및 MR 상태", "이번에 직접 재실행",
        "- 로컬 반영:", "- 원격 MR 코드 반영:", "- MR 설명 갱신:", "- 운영 검증:",
    ):
        # 방법별 비교의 전체 형식은 공통 지침에서 로드한다.
        effective = text + (ROOT / "core/rules/review-method-comparison.md").read_text()
        assert required in effective


def test_retrospective_output_requires_summary_and_contextual_comparisons():
    command = (ROOT / "core/user/commands/review-retrospective.md").read_text()
    output = command.split("## Output\n", 1)[1].split("## Compatibility", 1)[0]

    for required in (
        "상태 요약만으로 전체 결과를 대신하지 않는다",
        "### 구현 선택의 회고",
        "### 재발 방지 교훈의 적용 범위",
        "실제 채택과 회고 권장을 구분",
        "session_lesson_only",
        "원 리뷰 항목별 의도와 disposition",
        "확인 근거와 한계",
        "과거 실행 기록과 이번 실행 여부",
        "후보 수를 고정하지 않는다",
    ):
        assert required in output


def test_synthesis_loads_budget_guidance_before_composing_output():
    command = (ROOT / "core/user/commands/review-synthesis.md").read_text()

    assert "core/rules/review-synthesis-report-budget.md" in command
    assert "빈 줄·제목·목록·코드 fence·앞뒤 안내 문장" in command
    assert "출력 전 줄 수 확인" in command


def test_synthesis_budget_preserves_explanations_and_counts_entire_response():
    rule = (ROOT / "core/rules/review-synthesis-report-budget.md").read_text()

    for required in (
        "len(report.splitlines())",
        "72줄",
        "선택 이유·얻는 점·감수할 점",
        "후보별 설명·장점·단점",
        "필수 개행",
        "반복 설명",
        "아티팩트",
        "분할",
        "각 응답도 80줄",
        "모든 렌즈",
        "최종 출력과 동일한 문자열",
        "반드시 실행",
        "측정 후 수정하면 다시",
    ):
        assert required in rule


def test_seed_refreshes_pristine_commands_but_keeps_user_edits(tmp_path):
    source = tmp_path / "source"
    installed = tmp_path / "installed"
    manifest = tmp_path / "manifest.json"
    source.mkdir()
    seeder = ROOT / "core/setup/seed-user-commands.sh"
    env = dict(os.environ, AGENT_CREW_HOME=str(tmp_path / "crew"))

    for name in COMMANDS:
        (source / f"{name}.md").write_text(f"# {name}\n\nold seed\n")

    def seed():
        return subprocess.run(
            ["bash", str(seeder), str(source), str(installed), str(manifest)],
            env=env, check=True, capture_output=True, text=True,
        )

    seed()
    custom = installed / "mr-review-note.md"
    custom.write_text(custom.read_text() + "\n사용자 고유 문구\n")
    custom_before = custom.read_bytes()

    for name in COMMANDS:
        (source / f"{name}.md").write_bytes(
            (ROOT / "core/user/commands" / f"{name}.md").read_bytes()
        )

    result = seed()

    assert custom.read_bytes() == custom_before
    assert "diverged" in result.stdout
    for name in COMMANDS:
        if name != "mr-review-note":
            assert (installed / f"{name}.md").read_bytes() == (source / f"{name}.md").read_bytes()

    before = {p.name: p.read_bytes() for p in installed.glob("*.md")}
    manifest_before = manifest.read_bytes()
    seed()

    assert {p.name: p.read_bytes() for p in installed.glob("*.md")} == before
    assert manifest.read_bytes() == manifest_before


def test_user_rule_survives_upstream_replacement_or_removal(tmp_path):
    system = tmp_path / "system"
    user = tmp_path / "user"
    merged = tmp_path / "merged"
    system.mkdir()
    user.mkdir()
    name = "review-method-comparison.md"
    (system / name).write_text("# 기존 upstream 규칙\n")
    custom = (ROOT / "core/rules" / name).read_text() + "\n사용자 규칙\n"
    (user / name).write_text(custom)

    def merge():
        subprocess.run(
            ["bash", "-c", '. "$1"; merge_rules_to_discovery "$2" "$3" "$4"',
             "review-rule-test", str(ROOT / "core/setup/common.sh"), str(system),
             str(user), str(merged)],
            check=True, capture_output=True, text=True,
        )

    merge()
    assert (merged / name).read_text() == custom

    (system / name).write_text("# 변경된 upstream 규칙\n")
    merge()
    assert (merged / name).read_text() == custom

    (system / name).unlink()
    merge()
    assert (merged / name).read_text() == custom


def test_personal_command_edit_survives_update_from_older_source(tmp_path):
    source = tmp_path / "source"
    installed = tmp_path / "installed"
    source.mkdir()
    manifest = tmp_path / "manifest.json"
    seeder = ROOT / "core/setup/seed-user-commands.sh"
    current = (ROOT / "core/user/commands/review-followup.md").read_text()
    (source / "review-followup.md").write_text(current)

    def seed():
        subprocess.run(
            ["bash", str(seeder), str(source), str(installed), str(manifest)],
            check=True, capture_output=True, text=True,
        )

    seed()
    target = installed / "review-followup.md"
    personal = current + "\n<!-- user-owned-review-format: 개인 출력 형식 유지 -->\n"
    target.write_text(personal)
    manifest_before = manifest.read_bytes()
    (source / "review-followup.md").write_text("# 이전 버전 명령\n")
    seed()

    assert target.read_text() == personal
    assert manifest.read_bytes() == manifest_before
