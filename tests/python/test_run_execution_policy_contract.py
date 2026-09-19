"""Durable contract tests for explicit foreground/background run policy."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_MD = (REPO_ROOT / "core" / "commands" / "run.md").read_text(encoding="utf-8")
CAPABILITY_MD = (
    REPO_ROOT / "core" / "rules" / "capabilities" / "agent-background.md"
).read_text(encoding="utf-8")
CODEX_INVOCATION = (
    REPO_ROOT / "adapters" / "codex" / "invocation.md"
).read_text(encoding="utf-8")
CLAUDE_INVOCATION = (
    REPO_ROOT / "adapters" / "claude" / "invocation.md"
).read_text(encoding="utf-8")
TASK_INJECTION = (
    REPO_ROOT / "core" / "rules" / "task-injection.md"
).read_text(encoding="utf-8")


def test_success_case_contract_default_run_is_foreground_even_when_capability_exists():
    assert "default execution policy is foreground" in RUN_MD
    assert "BACKGROUND_REQUESTED=0" in RUN_MD
    assert "RUN_IN_BACKGROUND=1" in RUN_MD
    assert "RUN_IN_BACKGROUND == 0" in RUN_MD
    assert "HAS_AGENT_BACKGROUND == 1" in RUN_MD
    assert "wait for every supervisor to reach a terminal state" in RUN_MD
    assert "fan in every result" in RUN_MD


def test_success_case_contract_explicit_background_is_the_only_p4_entry():
    assert 'crew:run --background "implement order API"' in RUN_MD
    assert "BACKGROUND_REQUESTED == 1" in RUN_MD
    assert "RUN_IN_BACKGROUND == 1" in RUN_MD
    assert "explicit background execution" in RUN_MD
    for phase in ("start", "monitor", "terminal collect", "finalize"):
        assert phase in RUN_MD


def test_failure_case_contract_background_request_fails_closed_without_capability():
    assert "background_execution_unsupported" in RUN_MD
    assert "BACKGROUND_REQUESTED == 1" in RUN_MD
    assert "HAS_AGENT_BACKGROUND == 0" in RUN_MD


def test_regression_case_only_explicit_background_sessions_are_injectable():
    assert "Session Registry Initialization (N > 1 or explicit background)" in RUN_MD
    assert "'execution_policy': 'background' if ${BACKGROUND_REQUESTED} == 1 else 'foreground'" in RUN_MD
    assert "s.get('execution_policy') == 'background'" in RUN_MD
    assert "HAS_AGENT_BACKGROUND" in RUN_MD
    assert "Task injection is not supported on this host" in RUN_MD
    assert "BACKGROUND_REQUESTED=1  # inherit the validated session policy" in RUN_MD


def test_regression_case_collection_preserves_blocked_terminal_status():
    assert "TERMINAL_STATUS" in RUN_MD
    assert "blocked) TERMINAL_STATUS=blocked" in RUN_MD
    assert "t['status'] = '${TERMINAL_STATUS}'" in RUN_MD


def test_failure_case_background_terminal_without_result_is_bounded():
    assert "background_id" in RUN_MD
    assert "BACKGROUND_TERMINAL_WITHOUT_RESULT" in RUN_MD
    assert "BACKGROUND_CRASH_ATTEMPTS" in RUN_MD
    assert "background_result_missing_after_terminal" in RUN_MD
    assert "must not keep polling" in RUN_MD
    assert "BACKGROUND_RESULT_STATUS" in RUN_MD
    assert "cancelled)" in RUN_MD
    assert "invalid_or_missing" in RUN_MD


def test_success_case_contract_has_an_executable_background_finalizer_entry():
    assert 'crew:run --finalize-background' in RUN_MD
    assert "BACKGROUND_FINALIZE_REQUESTED=1" in RUN_MD
    assert "BACKGROUND_FINALIZER_ACTIVE=1" in RUN_MD
    assert "RUN_IN_BACKGROUND=1  # finalizer resumes the P4 lifecycle" in RUN_MD
    assert "BACKGROUND_FINALIZER_COLLECTION" in RUN_MD
    assert "background_finalize_session_not_found" in RUN_MD
    assert "background_finalize_policy_mismatch" in RUN_MD
    assert "skip empty-input task collection" in RUN_MD


def test_regression_case_capability_describes_mechanism_not_policy():
    assert "does not select the user's execution policy" in CAPABILITY_MD
    assert "default `crew:run` remains foreground" in CAPABILITY_MD
    assert "explicit `--background`" in CAPABILITY_MD
    assert "getBackgroundAgent(backgroundId)" in CAPABILITY_MD
    assert "awaitBackgroundAgent(backgroundId, timeoutSeconds?)" in CAPABILITY_MD
    for status in ("running", "completed", "error", "cancelled"):
        assert status in CAPABILITY_MD


def test_regression_case_codex_foreground_wait_is_not_described_as_background():
    assert "foreground wait" in CODEX_INVOCATION
    assert "new user input can interrupt the parent turn" in CODEX_INVOCATION
    assert "does not prove that the supervisor ran in background" in CODEX_INVOCATION
    assert "reconcile" in CODEX_INVOCATION
    assert "no new input can arrive" not in CODEX_INVOCATION


def test_regression_case_benchmark_docs_do_not_route_policy_by_capability():
    benchmark = (
        REPO_ROOT
        / "docs"
        / "superpowers-benchmark"
        / "capability-gated-reexamination.md"
    ).read_text(encoding="utf-8")

    assert "explicit execution policy" in benchmark
    assert "when true, supervisors spawn as background agents" not in benchmark


def test_regression_case_interruptible_input_is_not_described_as_injection_support():
    assert "no new user input is possible" not in TASK_INJECTION
    assert "may accept interrupting user input" in TASK_INJECTION
    assert "does not provide task injection" in TASK_INJECTION
    assert "foreground_session_active" in RUN_MD
    assert "must not overwrite" in RUN_MD


def test_boundary_case_claude_static_capability_is_not_runtime_proof():
    assert "Unverified runtime" in CLAUDE_INVOCATION
    assert "getBackgroundAgent" in CLAUDE_INVOCATION
    assert "awaitBackgroundAgent" in CLAUDE_INVOCATION
    assert "TaskOutput" in CLAUDE_INVOCATION
