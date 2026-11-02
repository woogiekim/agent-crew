"""Regression coverage for Codex current-session fallback execution."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = REPO_ROOT / "core" / "scripts" / "crew-runtime.py"
REPAIR_PATH = REPO_ROOT / "core" / "scripts" / "repair-task-state.py"
SCRIPTS_DIR = REPO_ROOT / "core" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime = _load(RUNTIME_PATH, "crew_runtime_current_session_gate")


def _write_task(
    tmp_path: Path,
    *,
    selected_subagents: list[str],
    inline_evidence: bool = True,
) -> tuple[Path, Path, str]:
    state_dir = tmp_path / "state"
    task_id = "20260923-000000-0"
    task_dir = state_dir / "tasks" / task_id
    context_dir = task_dir / "context"
    context_dir.mkdir(parents=True)

    (task_dir / "register.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "session_id": "20260923-000000",
                "task": "Implement a production fix",
                "project_root": str(tmp_path / "project"),
                "mutation_scope": "workspace_write",
                "current_phase": "handoff_ready",
                "host_bridge_status": "current_session_required",
                "blocked_by": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps({"stages": ["supervisor"], "completed_stages": 0}) + "\n",
        encoding="utf-8",
    )
    (task_dir / "result.md").write_text("STATUS: handoff_ready\n", encoding="utf-8")
    (task_dir / "progress.log").write_text("", encoding="utf-8")
    runtime.write_current_session_execution_contract(
        task_dir,
        task_id,
        "2026-09-23T00:00:00Z",
        "Implement a production fix",
        "workspace_write",
    )
    if inline_evidence:
        (context_dir / "inline-execution.json").write_text(
            json.dumps(
                {
                    "execution_profile": "inline_tdd",
                    "gates": {
                        "requirements_sufficiency": "passed",
                        "focused_red_green_refactor": "passed",
                        "relevant_verification": "passed",
                        "inline_diff_review": "passed",
                        "structured_closeout": "passed",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    (context_dir / "specialist-dispatch.md").write_text(
        "selected_agent: supervisor\n"
        "selection_reason: current session owns the pinned supervisor plan\n"
        "execution_mode: current_session_fallback\n"
        + "".join(f"selected_subagent: {agent}\n" for agent in selected_subagents),
        encoding="utf-8",
    )
    return state_dir, task_dir, task_id


def _repair(state_dir: Path, task_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPAIR_PATH),
            "--state-dir",
            str(state_dir),
            "--status",
            "completed",
            "--quality-bypass-reason",
            "isolate current-session lifecycle gate",
            "--skill-load-bypass-reason",
            "isolate current-session lifecycle gate",
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def _repair_without_quality_bypass(
    state_dir: Path, task_id: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPAIR_PATH),
            "--state-dir",
            str(state_dir),
            "--status",
            "completed",
            "--skill-load-bypass-reason",
            "isolate inline quality integration",
            task_id,
        ],
        text=True,
        capture_output=True,
    )


def test_runtime_contract_forbids_nested_supervisor_and_defaults_inline():
    contract = runtime.current_session_execution_contract(
        "task-1", "2026-09-23T00:00:00Z", "간단한 null 처리 수정"
    )

    assert contract["execution_mode"] == "inline_supervisor"
    assert contract["execution_profile"] == "inline_tdd"
    assert contract["top_level_supervisor_spawn_allowed"] is False
    assert contract["subagent_default"] == "none"
    assert contract["subagent_lifecycle_required"] is True
    assert contract["max_wait_seconds_per_call"] == 60
    assert contract["max_unchanged_waits"] == 2
    assert contract["required_quality_gates"] == [
        "requirements_sufficiency",
        "focused_red_green_refactor",
        "relevant_verification",
        "inline_diff_review",
        "structured_closeout",
    ]


def test_runtime_profile_escalates_explicit_full_crew_and_multi_repo_work():
    explicit = runtime.current_session_execution_contract(
        "task-1", "2026-09-23T00:00:00Z", "full crew로 이 변경을 구현해"
    )
    multi_repo = runtime.current_session_execution_contract(
        "task-2", "2026-09-23T00:00:00Z", "여러 저장소 계약을 함께 변경해"
    )

    assert explicit["execution_profile"] == "full_crew"
    assert "explicit_full_crew" in explicit["profile_signals"]
    assert multi_repo["execution_profile"] == "full_crew"
    assert "multi_repository" in multi_repo["profile_signals"]


def test_runtime_profile_escalates_remote_or_parallel_work():
    remote = runtime.current_session_execution_contract(
        "task-1", "2026-09-23T00:00:00Z", "수정 후 push하고 배포해"
    )
    parallel = runtime.current_session_execution_contract(
        "task-2", "2026-09-23T00:00:00Z", "독립 작업을 병렬로 처리해"
    )

    assert remote["execution_profile"] == "full_crew"
    assert "external_write" in remote["profile_signals"]
    assert parallel["execution_profile"] == "full_crew"
    assert "explicit_parallelism" in parallel["profile_signals"]


def test_runtime_profile_uses_inline_readonly_without_tdd_gate():
    contract = runtime.current_session_execution_contract(
        "task-1",
        "2026-09-23T00:00:00Z",
        "현재 구조를 분석해",
        "read_only",
    )

    assert contract["execution_profile"] == "inline_readonly"
    assert "focused_red_green_refactor" not in contract["required_quality_gates"]


def test_completed_repair_blocks_missing_inline_quality_evidence(tmp_path: Path):
    state_dir, _task_dir, task_id = _write_task(
        tmp_path,
        selected_subagents=[],
        inline_evidence=False,
    )

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "inline_execution_incomplete" in result.stderr
    assert "focused_red_green_refactor" in result.stderr


def test_codex_wrapper_declares_current_session_as_inline_supervisor():
    skill = (REPO_ROOT / "adapters/codex/skill/crew:run/SKILL.md").read_text(
        encoding="utf-8"
    )
    normalized = " ".join(skill.split())

    assert "The current session is the supervisor for the pinned plan" in normalized
    assert "Never spawn or select another top-level" in normalized
    assert "default selected subagent set is empty" in normalized
    assert "max_unchanged_waits" in skill


def test_completed_repair_blocks_selected_subagent_without_lifecycle(tmp_path: Path):
    state_dir, _task_dir, task_id = _write_task(
        tmp_path, selected_subagents=["reviewer"]
    )

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "current_session_lifecycle_incomplete" in result.stderr
    assert "reviewer" in result.stderr


def test_completed_repair_accepts_inline_execution_without_subagents(tmp_path: Path):
    state_dir, task_dir, task_id = _write_task(tmp_path, selected_subagents=[])

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads(
        (task_dir / "context" / "manual-fallback-repair.json").read_text(
            encoding="utf-8"
        )
    )
    assert repair["current_session_execution_gate"]["passed"] is True
    assert repair["current_session_execution_gate"]["selected_subagents"] == []


def test_inline_tdd_quality_evidence_replaces_multi_agent_pipeline_requirement(
    tmp_path: Path,
):
    state_dir, task_dir, task_id = _write_task(tmp_path, selected_subagents=[])

    result = _repair_without_quality_bypass(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads(
        (task_dir / "context" / "manual-fallback-repair.json").read_text(
            encoding="utf-8"
        )
    )
    assert repair["quality_gate"]["passed"] is True
    assert repair["quality_gate"]["execution_profile"] == "inline_tdd"
    assert repair["quality_gate"]["pipeline_gate"]["mode"] == "inline_tdd"


def test_completed_repair_blocks_nested_supervisor_selection(tmp_path: Path):
    state_dir, _task_dir, task_id = _write_task(
        tmp_path, selected_subagents=["supervisor"]
    )

    result = _repair(state_dir, task_id)

    assert result.returncode != 0
    assert "nested_supervisor_forbidden" in result.stderr


def test_completed_repair_accepts_terminal_parent_resumed_subagent(tmp_path: Path):
    state_dir, task_dir, task_id = _write_task(
        tmp_path, selected_subagents=["reviewer"]
    )
    lifecycle_dir = task_dir / "context" / "stage-lifecycle"
    lifecycle_dir.mkdir()
    lifecycle_dir.joinpath("stage-1-unit-review-invocation-r1-attempt-1.json").write_text(
        json.dumps(
            {
                "agent": "reviewer",
                "status": "parent_resumed",
                "timing": {
                    "terminal_at": "2026-09-23T00:01:00Z",
                    "parent_resume_at": "2026-09-23T00:01:01Z",
                },
                "outcome": {"terminal_state": "terminal_completed"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = _repair(state_dir, task_id)

    assert result.returncode == 0, result.stdout + result.stderr
    repair = json.loads(
        (task_dir / "context" / "manual-fallback-repair.json").read_text(
            encoding="utf-8"
        )
    )
    assert repair["current_session_execution_gate"]["passed"] is True


def test_boundary_case_contract_ignores_prohibited_external_writes():
    tasks = [
        "push, 배포는 금지한다. 읽기 전용으로 분석하라.",
        "Do not push or deploy. Inspect the code.",
        "Never publish or rollback; review only.",
        "배포하지 말고 코드를 분석하라.",
        "Do not deploy, read the code and execute unit tests",
        "배포는 금지한다, 코드를 읽고 단위 테스트를 실행해",
    ]

    for task in tasks:
        assert runtime.current_session_execution_profile(task, "read_only") == (
            "inline_readonly", []
        ), task


def test_boundary_case_contract_ignores_document_mentions():
    for task in ["배포 문서만 읽고 문제를 설명하라.", "Read deployment documentation only."]:
        assert runtime.current_session_execution_profile(task, "read_only") == (
            "inline_readonly", []
        ), task


def test_boundary_case_security_preserves_positive_or_ambiguous_external_writes():
    tasks = [
        "Push the branch", "배포해", "배포 문서를 읽고 배포해",
        "Do not deploy, but push the branch", "배포하지 말고 push해",
        "Discuss whether to deploy", "push", "deploy unless tests fail",
        "Publish documentation", "Deploy docs", "Push documentation",
        "Do not deploy unless approved", "배포 문서 읽고 push해",
    ]

    for task in tasks:
        profile, signals = runtime.current_session_execution_profile(task, "read_only")
        assert profile == "full_crew", task
        assert "external_write" in signals, task


def test_boundary_case_contract_retains_explicit_readonly_coordination():
    for task in ["full crew review", "여러 저장소 읽기 전용 분석", "병렬로 분석", "parallel review"]:
        profile, signals = runtime.current_session_execution_profile(task, "read_only")
        assert profile == "full_crew", task
        assert signals, task


@pytest.mark.parametrize("task", [
    "Do not deploy without approval.",
    "Do not deploy\nunless approved.",
])
def test_boundary_case_security_retains_conditional_prohibition(task):
    profile, signals = runtime.current_session_execution_profile(task, "read_only")

    assert profile == "full_crew"
    assert "external_write" in signals


@pytest.mark.parametrize("task", [
    "배포 문서를 읽고 그대로 실행해.",
    "Read the deployment manual and execute it.",
])
def test_boundary_case_security_retains_document_execution(task):
    profile, signals = runtime.current_session_execution_profile(task, "read_only")

    assert profile == "full_crew"
    assert "external_write" in signals


@pytest.mark.parametrize("task", [
    "Read deployment docs and execute unit tests. Do not deploy.",
    "Read deployment docs\nExecute unit tests\nDo not deploy",
    "배포 문서를 읽고 단위 테스트를 실행해. 배포는 금지한다.",
    "Read deployment docs and execute the unit tests.",
])
def test_boundary_case_contract_ignores_document_mentions_with_unit_tests(task):
    assert runtime.current_session_execution_profile(task, "read_only") == (
        "inline_readonly", []
    )
    assert runtime.current_session_execution_profile(task, "workspace_write") == (
        "inline_tdd", []
    )


@pytest.mark.parametrize("task", [
    "Read the deployment manual, execute unit tests and execute it.",
    "배포 문서를 읽고 단위 테스트를 실행하고 그대로 실행해.",
    "Read deployment docs and execute unit tests and deploy.",
])
def test_boundary_case_security_retains_document_execution_alongside_unit_tests(task):
    profile, signals = runtime.current_session_execution_profile(task, "read_only")

    assert profile == "full_crew"
    assert "external_write" in signals


@pytest.mark.parametrize("task", [
    "Read the deployment manual and execute unit tests and the procedure described in it.",
    "Read the deployment manual and execute unit tests, then its steps.",
    "Read the deployment manual and execute its steps and unit tests.",
    "배포 문서를 읽고 문서 절차와 단위 테스트를 실행해.",
    "배포 문서를 읽고 문서 절차 및 단위 테스트를 실행해.",
    "배포 문서를 읽고 단위 테스트와 문서 절차를 실행해.",
])
def test_boundary_case_security_retains_shared_execution_verb(task):
    for scope in ["read_only", "workspace_write"]:
        profile, signals = runtime.current_session_execution_profile(task, scope)

        assert profile == "full_crew"
        assert "external_write" in signals
