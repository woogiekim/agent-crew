"""RED tests for core/scripts/check-verification-evidence.py.

Spec: PRD § F1 (VERIFIED line shape) and § F5 (TDD test surface) from
{TASK_DIR}/context/prd.md, with the validator contract refined as:

    VERIFIED: tests=<RESULT> cmd=<CMD> exit=<CODE>

  - RESULT is `<passed>/<total>` (both non-negative integers, passed <= total)
    OR `skipped:<reason>` with a non-empty reason.
  - CMD is a non-empty string.
  - CODE is a parseable integer.

Validator behavior:
  - exit 0 + "PASS: <reason>" on stdout when the report contains a valid VERIFIED line.
  - exit 1 + "FAIL: <reason>" on stdout when the line is missing, malformed,
    fails value validation, or violates the strict --require-passed mode.
  - exit 2 + "ERROR: <reason>" on stdout when the --report argument points at
    an unreadable / non-existent path.

The script under test does NOT yet exist when these tests are first run; the
RED phase is expected to fail with FileNotFoundError / nonzero exit because
core/scripts/check-verification-evidence.py is missing.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_NAME = "check-verification-evidence.py"


def _completion_block(verified_line: str) -> str:
    """Build a realistic completion report containing the VERIFIED line."""
    return (
        "ARTIFACTS: src/foo.py tests/python/test_foo.py\n"
        f"{verified_line}\n"
        "STATUS: completed\n"
    )


class TestValidVerifiedLine:
    """Happy paths — valid VERIFIED line returns exit 0 + PASS."""

    def test_pass_form_all_passed_returns_pass(self, script_runner):
        report = _completion_block("VERIFIED: tests=12/12 cmd=pytest exit=0")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 0, (
            f"valid pass form must exit 0; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "PASS" in r.stdout, (
            f"stdout must contain 'PASS'; got: {r.stdout!r}"
        )

    def test_pass_form_partial_in_default_mode_returns_pass(self, script_runner):
        """Default mode tolerates passed/total mismatches; only --require-passed rejects."""
        report = _completion_block("VERIFIED: tests=11/12 cmd=pytest exit=0")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 0, (
            f"partial pass must exit 0 in default mode; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "PASS" in r.stdout

    def test_skipped_form_with_reason_returns_pass(self, script_runner):
        report = _completion_block(
            "VERIFIED: tests=skipped:no-runnable-harness cmd=n/a exit=0"
        )
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 0, (
            f"skipped:<reason> must exit 0; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "PASS" in r.stdout

    def test_canonical_agent_prescribed_skip_line_returns_pass(self, script_runner):
        """F-001 regression lock-in.

        The agent prompts (backend.md, frontend.md, test-writer.md) and the
        rule narrative (self-verification.md, quality-loop.md) all prescribe
        the exact canonical skip-form literal:

            VERIFIED: tests=skipped:no_runnable_harness cmd=none exit=0

        This test asserts that the validator accepts that exact line shape,
        preventing any future drift back to `exit=n/a` (which the script's
        `_validate_exit` would reject because `int('n/a')` raises ValueError).
        """
        report = _completion_block(
            "VERIFIED: tests=skipped:no_runnable_harness cmd=none exit=0"
        )
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 0, (
            f"canonical agent-prescribed skip line must exit 0; "
            f"got {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "PASS" in r.stdout

    def test_passed_equals_total_zero_returns_pass(self, script_runner):
        """tests=0/0 (no tests run, none failed) is a valid degenerate pass."""
        report = _completion_block("VERIFIED: tests=0/0 cmd=pytest exit=0")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 0, (
            f"0/0 must exit 0; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )


class TestMissingVerifiedLine:
    """The completion report has no VERIFIED line — must FAIL."""

    def test_no_verified_line_at_all_returns_fail(self, script_runner):
        report = (
            "ARTIFACTS: src/foo.py\n"
            "STATUS: completed\n"
        )
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 1, (
            f"missing VERIFIED must exit 1; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout


class TestMalformedVerifiedLine:
    """The VERIFIED line is present but malformed — must FAIL."""

    def test_missing_tests_field_returns_fail(self, script_runner):
        report = _completion_block("VERIFIED: cmd=pytest exit=0")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 1, (
            f"missing tests= must exit 1; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout

    def test_missing_cmd_field_returns_fail(self, script_runner):
        report = _completion_block("VERIFIED: tests=12/12 exit=0")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 1, (
            f"missing cmd= must exit 1; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout

    def test_missing_exit_field_returns_fail(self, script_runner):
        report = _completion_block("VERIFIED: tests=12/12 cmd=pytest")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 1, (
            f"missing exit= must exit 1; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout

    def test_invalid_tests_value_non_numeric_returns_fail(self, script_runner):
        report = _completion_block("VERIFIED: tests=abc/def cmd=pytest exit=0")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 1, (
            f"non-numeric tests must exit 1; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout

    def test_invalid_tests_value_empty_skip_reason_returns_fail(self, script_runner):
        report = _completion_block("VERIFIED: tests=skipped: cmd=pytest exit=0")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 1, (
            f"skipped with empty reason must exit 1; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout

    def test_empty_cmd_value_returns_fail(self, script_runner):
        report = _completion_block("VERIFIED: tests=12/12 cmd= exit=0")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 1, (
            f"empty cmd must exit 1; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout

    def test_invalid_exit_value_non_integer_returns_fail(self, script_runner):
        report = _completion_block("VERIFIED: tests=12/12 cmd=pytest exit=notanint")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 1, (
            f"non-integer exit must exit 1; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout

    def test_passed_greater_than_total_returns_fail(self, script_runner):
        """tests=15/12 — passed exceeds total, impossible by construction."""
        report = _completion_block("VERIFIED: tests=15/12 cmd=pytest exit=0")
        r = script_runner(SCRIPT_NAME, input_text=report)
        assert r.returncode == 1, (
            f"passed > total must exit 1; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout


class TestStrictRequirePassedMode:
    """--require-passed enforces N == M; default mode tolerates N < M."""

    def test_strict_mode_rejects_partial_pass(self, script_runner):
        report = _completion_block("VERIFIED: tests=11/12 cmd=pytest exit=0")
        r = script_runner(SCRIPT_NAME, "--require-passed", input_text=report)
        assert r.returncode == 1, (
            f"--require-passed must reject N < M; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "FAIL" in r.stdout
        assert "not all tests passed" in r.stdout.lower(), (
            f"strict-mode rejection must explain 'not all tests passed'; "
            f"got stdout: {r.stdout!r}"
        )

    def test_strict_mode_accepts_full_pass(self, script_runner):
        report = _completion_block("VERIFIED: tests=12/12 cmd=pytest exit=0")
        r = script_runner(SCRIPT_NAME, "--require-passed", input_text=report)
        assert r.returncode == 0, (
            f"--require-passed must accept N == M; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "PASS" in r.stdout


class TestReportFileInput:
    """--report <path> reads the report from the given file."""

    def test_report_path_valid_file_returns_pass(self, script_runner, tmp_path):
        report_path = tmp_path / "report.txt"
        report_path.write_text(
            _completion_block("VERIFIED: tests=5/5 cmd=pytest exit=0")
        )
        r = script_runner(SCRIPT_NAME, "--report", str(report_path))
        assert r.returncode == 0, (
            f"valid --report file must exit 0; got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "PASS" in r.stdout

    def test_report_path_missing_file_returns_error(self, script_runner, tmp_path):
        missing = tmp_path / "does-not-exist.txt"
        r = script_runner(SCRIPT_NAME, "--report", str(missing))
        assert r.returncode == 2, (
            f"missing --report file must exit 2 (ERROR); got {r.returncode}\n"
            f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "ERROR" in r.stdout
