"""Regression tests for measured reviewer and retry latency causes."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWER = (REPO_ROOT / "core" / "agents" / "reviewer.md").read_text(
    encoding="utf-8"
)
SKILL_LOADING = (
    REPO_ROOT / "core" / "rules" / "agent-skill-loading.md"
).read_text(encoding="utf-8")
BOOTSTRAP = (REPO_ROOT / "core" / "agents" / "supervisor-bootstrap.md").read_text(
    encoding="utf-8"
)
RETRY = (REPO_ROOT / "core" / "agents" / "supervisor-retry.md").read_text(
    encoding="utf-8"
)
STAGES = (REPO_ROOT / "core" / "agents" / "supervisor-stages.md").read_text(
    encoding="utf-8"
)


def _section(text: str, heading: str) -> str:
    tail = text.split(heading, 1)[1]
    return tail.split("\n## ", 1)[0]


def test_regression_case_reviewer_does_not_load_every_language_upfront():
    upfront = _section(REVIEWER, "## Skills (Loaded Upfront)")

    assert "effective-kotlin.md" not in upfront
    assert "effective-java.md" not in upfront
    assert "effective-typescript.md" not in upfront
    assert "effective-python.md" not in upfront
    assert "effective-go.md" not in upfront
    assert "effective-rust.md" not in upfront
    assert "effective-scala.md" not in upfront
    assert "effective-swift.md" not in upfront
    assert "## Language Skills (Loaded by Changed-Code Evidence)" in REVIEWER


def test_regression_case_skill_loading_allows_evidence_based_language_subset():
    assert "cross-cutting skills" in SKILL_LOADING
    assert "language-specific skills" in SKILL_LOADING
    assert "changed-code evidence" in SKILL_LOADING
    assert "must not load unrelated language skills" in SKILL_LOADING
    assert "must not select a subset" not in SKILL_LOADING


def test_regression_case_reviewer_selects_one_gradle_verification_mode_before_run():
    assert "Choose the verification mode before executing Gradle" in REVIEWER
    assert "MUST NOT automatically follow" in REVIEWER
    assert "--rerun-tasks" in REVIEWER
    assert "UP-TO-DATE" in REVIEWER
    assert "stale verification evidence" in REVIEWER
    assert "exactly one fresh verification run" in REVIEWER


def test_regression_case_reviewer_resolves_installed_jdk_before_gradle():
    assert "/usr/libexec/java_home -v 17" in REVIEWER
    assert "JAVA_HOME" in REVIEWER
    assert "before the first Gradle invocation" in REVIEWER
    assert "jdk17_unavailable" in REVIEWER


def test_success_case_docs_only_reviewer_skips_test_execution():
    assert "REQUIRES_TEST_EXECUTION: false" in REVIEWER
    assert "docs-only" in REVIEWER


def test_failure_case_capacity_retries_are_bounded_and_observable():
    assert "ANALYST_CAPACITY_ATTEMPTS" in BOOTSTRAP
    assert "capacity_unavailable" in BOOTSTRAP
    assert "fallback=unavailable" in BOOTSTRAP
    assert "capacity_attempts" in RETRY
    assert "reason=capacity" in RETRY


def test_boundary_case_stage_timeouts_use_bounded_kind_specific_defaults():
    assert "stage-specific defaults" in BOOTSTRAP
    assert "requirements, Brainstorm" in BOOTSTRAP
    assert "planning, test-writer, implementation, QA, reviewer" in BOOTSTRAP
    assert "explicit `0`" in BOOTSTRAP
    assert "stage_timeout_unenforceable" in BOOTSTRAP
    assert "AGENT_CREW_STAGE_TIMEOUT_SECONDS" in BOOTSTRAP


def test_boundary_case_configured_timeout_is_enforced_during_invocation():
    assert "remaining timeout" in RETRY
    assert "cancel or interrupt the host invocation" in RETRY
    assert "stage_timeout_unenforceable" in RETRY


def test_success_case_stage_completion_reports_elapsed_time():
    assert "STAGE_DONE" in RETRY
    assert "elapsed=" in RETRY
    assert "STAGE_START_EPOCH" in STAGES
    assert "STAGE_END_EPOCH" in STAGES
    assert 'log_progress "STAGE_DONE"' in STAGES
    assert "elapsed=${STAGE_ELAPSED}s" in STAGES
    assert "reason=capacity" in RETRY


def test_success_case_phase_completion_reports_start_end_and_elapsed_time():
    assert "phase_start" in BOOTSTRAP
    assert "phase_done" in BOOTSTRAP
    assert 'log_progress "PHASE_START"' in BOOTSTRAP
    assert 'log_progress "PHASE_DONE"' in BOOTSTRAP
    assert "elapsed=${PHASE_ELAPSED}s" in BOOTSTRAP
    assert "Every numbered supervisor phase" in BOOTSTRAP
