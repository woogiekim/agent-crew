"""Tests for the sufficiency_check() function defined in core/commands/run.md
(Step 5.pre) and mirrored in core/agents/supervisor-bootstrap.md.

Verifies that Python / shell / JS/TS file-creation intents with explicit
function or parameter specs are correctly classified as SUFFICIENT (issue #29),
and that pre-existing AMBIGUOUS classifications are not regressed.

The function body is extracted from the live source file so tests stay in
sync with any future edits — no copy-paste drift.
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_MD = REPO_ROOT / "core" / "commands" / "run.md"
SUPERVISOR_BOOTSTRAP_MD = REPO_ROOT / "core" / "agents" / "supervisor-bootstrap.md"


# ---------------------------------------------------------------------------
# Extract sufficiency_check from a markdown file and compile it into a
# callable.  The function body lives inside a ```python … ``` block.
# ---------------------------------------------------------------------------

def _extract_sufficiency_check(md_path: Path) -> Callable[[str], str]:
    """Parse sufficiency_check() out of a markdown file and return it."""
    src = md_path.read_text(encoding="utf-8")

    # Find the ```python block that contains the function definition.
    # We match from 'def sufficiency_check' up to the closing ``` line.
    m = re.search(
        r"```python\s*\n(.*?def sufficiency_check.*?)```",
        src,
        re.DOTALL,
    )
    if not m:
        raise ValueError(
            f"Could not find sufficiency_check() in {md_path}"
        )

    func_src = textwrap.dedent(m.group(1))
    ns: dict = {}
    exec(  # noqa: S102
        "import re\n" + func_src,
        ns,
    )
    fn = ns.get("sufficiency_check")
    if fn is None:
        raise ValueError(
            f"sufficiency_check not defined after exec of block in {md_path}"
        )
    return fn


# Build both variants at import time so collection errors surface early.
_check_run_md = _extract_sufficiency_check(RUN_MD)
_check_bootstrap_md = _extract_sufficiency_check(SUPERVISOR_BOOTSTRAP_MD)


# ---------------------------------------------------------------------------
# Parametrize over both files to verify they stay in sync (issue: the two
# must stay in sync — any change to one MUST be mirrored to the other).
# ---------------------------------------------------------------------------

@pytest.fixture(params=["run_md", "bootstrap_md"])
def check(request) -> Callable[[str], str]:
    return _check_run_md if request.param == "run_md" else _check_bootstrap_md


# ---------------------------------------------------------------------------
# Issue #29 reproduction cases — must now return SUFFICIENT
# ---------------------------------------------------------------------------

class TestIssue29PythonFileCreation:
    """Tasks from the issue #29 reproduction that previously returned AMBIGUOUS."""

    def test_calculator_py_with_functions(self, check):
        """calculator.py with named arithmetic functions — SUFFICIENT."""
        assert check(
            "Add a calculator.py with add, subtract, multiply, divide functions"
        ) == "SUFFICIENT"

    def test_hello_py_with_parameter(self, check):
        """hello.py with a configurable name parameter — SUFFICIENT."""
        assert check(
            "Add a hello.py that prints Hello, World! with a configurable name parameter"
        ) == "SUFFICIENT"

    def test_fibonacci_py_with_function_signature(self, check):
        """fibonacci.py with a parenthesized function name — SUFFICIENT."""
        assert check(
            "Write a fibonacci.py with a single fibonacci(n) function"
        ) == "SUFFICIENT"


# ---------------------------------------------------------------------------
# Extension-based scope inference — new patterns now SUFFICIENT
# ---------------------------------------------------------------------------

class TestExtensionBasedScopeInference:
    def test_deploy_sh_with_function(self, check):
        """Shell file with function spec — SUFFICIENT."""
        assert check(
            "Add a deploy.sh with a function to check environment variables"
        ) == "SUFFICIENT"

    def test_typescript_file_with_function_signature(self, check):
        """TypeScript file with parenthesized function name — SUFFICIENT."""
        assert check(
            "Write a utils.ts with a formatDate(date: Date) function"
        ) == "SUFFICIENT"

    def test_jsx_component_with_method(self, check):
        """JSX file with method spec — SUFFICIENT."""
        assert check(
            "Add a Button.jsx with an onClick method and disabled parameter"
        ) == "SUFFICIENT"

    def test_python_keyword_in_tooling_kw(self, check):
        """'python' keyword is now in tooling_kw — scope hit via keyword."""
        # The word 'python' is now in tooling_kw; this hits scope via keyword.
        # But target still requires a named file — without one it is AMBIGUOUS.
        assert check(
            "Write a Python script to parse CSV files using existing stack"
        ) == "AMBIGUOUS"

    def test_bash_keyword_in_tooling_kw_with_file(self, check):
        """'bash' keyword in tooling_kw, file named — scope + target hit."""
        assert check(
            "Add a bash setup.sh with a function to install dependencies"
        ) == "SUFFICIENT"


# ---------------------------------------------------------------------------
# Question-word veto — must still return AMBIGUOUS
# ---------------------------------------------------------------------------

class TestQuestionVeto:
    def test_question_mark_veto(self, check):
        assert check("what about adding a .py file?") == "AMBIGUOUS"

    def test_which_veto(self, check):
        assert check(
            "which function should I add to calculator.py?"
        ) == "AMBIGUOUS"

    def test_how_should_veto(self, check):
        assert check("how should I implement the algorithm?") == "AMBIGUOUS"

    def test_should_i_veto(self, check):
        assert check(
            "should I add a fibonacci.py with a recursive function?"
        ) == "AMBIGUOUS"


# ---------------------------------------------------------------------------
# Constraint signal only fires for script-file tasks (no false positives)
# ---------------------------------------------------------------------------

class TestFuncSpecConstraintBoundary:
    def test_py_file_without_func_spec_is_ambiguous(self, check):
        """A bare .py filename with no function/parameter description — AMBIGUOUS."""
        assert check("Create a utils.py") == "AMBIGUOUS"

    def test_sh_file_without_func_spec_is_ambiguous(self, check):
        """A bare .sh filename with no function/parameter description — AMBIGUOUS."""
        assert check("Create a cleanup.sh") == "AMBIGUOUS"

    def test_func_spec_without_script_file_does_not_promote(self, check):
        """'function' keyword alone (no .py/.sh/.ts) does not unlock constraint."""
        # No specific file path, no constraint hit via func_spec alone
        # (scope: 'backend'; target: none; constraint: needs file + func_spec OR other signal)
        assert check(
            "Add a backend function to handle authentication"
        ) == "AMBIGUOUS"


# ---------------------------------------------------------------------------
# Regression: pre-existing SUFFICIENT cases must still be SUFFICIENT
# ---------------------------------------------------------------------------

class TestRegressionSufficientCases:
    def test_tooling_path_dep_triple(self, check):
        """tooling keyword + file path + dep constraint — still SUFFICIENT."""
        assert check(
            "Update the pipeline agent hook to use existing stack"
        ) == "SUFFICIENT"

    def test_script_keyword_path_dep(self, check):
        """'script' keyword + quoted name + dep constraint — still SUFFICIENT."""
        assert check(
            'Add a "migration.sh" script with no new dependencies'
        ) == "SUFFICIENT"

    def test_backend_branch_mvp(self, check):
        """Backend keyword + branch ref + MVP constraint — still SUFFICIENT."""
        assert check(
            "Implement MVP auth endpoint on feat/auth-endpoint"
        ) == "SUFFICIENT"

    def test_frontend_component_perf(self, check):
        """Frontend keyword + quoted name + perf constraint — still SUFFICIENT."""
        assert check(
            'Add a "DataTable" component that renders 1000 rows under 100ms'
        ) == "SUFFICIENT"


# ---------------------------------------------------------------------------
# Regression: pre-existing AMBIGUOUS cases must still be AMBIGUOUS
# ---------------------------------------------------------------------------

class TestRegressionAmbiguousCases:
    def test_no_target_is_ambiguous(self, check):
        """Scope + constraint but no specific target — AMBIGUOUS."""
        assert check(
            "Add a backend API endpoint for user authentication"
        ) == "AMBIGUOUS"

    def test_vague_python_task_is_ambiguous(self, check):
        """Python task with no named file and no function spec — AMBIGUOUS."""
        assert check(
            "Write a Python script to parse CSV files using existing stack"
        ) == "AMBIGUOUS"
