"""Tests for the deterministic requirements sufficiency helper."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "requirements-sufficiency.py"
RUN_MD = REPO_ROOT / "core" / "commands" / "run.md"
SUPERVISOR_BOOTSTRAP_MD = REPO_ROOT / "core" / "agents" / "supervisor-bootstrap.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("requirements_sufficiency", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_module = _load_module()


def check() -> Callable[[str], str]:
    return _module.sufficiency_check


class TestIssue29PythonFileCreation:
    def test_calculator_py_with_functions(self):
        assert check()(
            "Add a calculator.py with add, subtract, multiply, divide functions"
        ) == "SUFFICIENT"

    def test_hello_py_with_parameter(self):
        assert check()(
            "Add a hello.py that prints Hello, World! with a configurable name parameter"
        ) == "SUFFICIENT"

    def test_fibonacci_py_with_function_signature(self):
        assert check()(
            "Write a fibonacci.py with a single fibonacci(n) function"
        ) == "SUFFICIENT"


class TestExtensionBasedScopeInference:
    def test_deploy_sh_with_function(self):
        assert check()(
            "Add a deploy.sh with a function to check environment variables"
        ) == "SUFFICIENT"

    def test_typescript_file_with_function_signature(self):
        assert check()(
            "Write a utils.ts with a formatDate(date: Date) function"
        ) == "SUFFICIENT"

    def test_jsx_component_with_method(self):
        assert check()(
            "Add a Button.jsx with an onClick method and disabled parameter"
        ) == "SUFFICIENT"

    def test_python_keyword_in_tooling_kw(self):
        assert check()(
            "Write a Python script to parse CSV files using existing stack"
        ) == "AMBIGUOUS"

    def test_bash_keyword_in_tooling_kw_with_file(self):
        assert check()(
            "Add a bash setup.sh with a function to install dependencies"
        ) == "SUFFICIENT"


class TestCommercializationPrompt:
    def test_latency_quality_blocker_prompt_is_sufficient(self):
        task = (
            "Find and implement concrete fixes for the commercialization blockers "
            "identified in the previous agent-crew E2E validation. Prioritize "
            "performance and answer quality as product-critical: poor latency "
            "blocks adoption and poor output quality makes the product unusable. "
            "Inspect the current branch, previous validation report, "
            "run/update/status/agent flows, prompt/instruction surface, "
            "telemetry/status reporting, and benchmark/test coverage. Implement "
            "narrow safe fixes. Do not push or merge without approval."
        )
        assert check()(task) == "SUFFICIENT"
        requirements = _module.synthesize_requirements(task)
        assert "Performance / scalability" in requirements
        assert "Answer quality / failure guidance" in requirements
        assert "No remote publish without approval" in requirements

    def test_cli_json_exposes_signals(self):
        task = (
            "Improve status reporting for latency and quality blockers in the "
            "current branch and previous validation report"
        )
        result = subprocess.run(
            ["python3", str(SCRIPT), "--json", task],
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(result.stdout)
        assert payload["status"] == "SUFFICIENT"
        assert payload["signals"]["has_perf"] is True
        assert payload["signals"]["has_quality"] is True

    def test_cli_write_is_silent_and_creates_requirements(self, tmp_path):
        out = tmp_path / "requirements.md"
        result = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--write", str(out),
                "Improve status reporting for latency and quality blockers in "
                "the current branch and previous validation report",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        assert result.stdout == ""
        assert "REQUIREMENTS: |" in out.read_text()

    def test_second_commercialization_e2e_prompt_is_sufficient(self):
        task = (
            "Run a second commercialization-focused end-to-end validation of "
            "agent-crew, prioritizing performance and answer quality. Evaluate "
            "agent-crew strictly as a prompt-internal orchestration/control "
            "layer on top of a host AI execution plane, not as an autonomous "
            "commercial harness. Measure current behavior after the latest "
            "fixes across crew setup, crew run, crew status, crew update, "
            "crew agent, fake-host E2E, host handoff quality, stale or "
            "incomplete pipeline handling, status and telemetry guidance, and "
            "prompt-runtime overhead. Decide whether latency is acceptable for "
            "adoption and whether user-visible answer and failure quality is "
            "actionable enough for commercial use. If narrow safe issues are "
            "found, implement fixes, run relevant and full tests, and commit "
            "locally. Do not push or merge without approval."
        )
        assert check()(task) == "SUFFICIENT"
        signals = _module.sufficiency_signals(task)
        assert signals["workflow_targets"] >= 2
        assert signals["has_perf"] is True
        assert signals["has_quality"] is True


class TestQuestionVeto:
    def test_question_mark_veto(self):
        assert check()("what about adding a .py file?") == "AMBIGUOUS"

    def test_which_veto(self):
        assert check()("which function should I add to calculator.py?") == "AMBIGUOUS"

    def test_how_should_veto(self):
        assert check()("how should I implement the algorithm?") == "AMBIGUOUS"

    def test_should_i_veto(self):
        assert check()(
            "should I add a fibonacci.py with a recursive function?"
        ) == "AMBIGUOUS"


class TestFuncSpecConstraintBoundary:
    def test_py_file_without_func_spec_is_ambiguous(self):
        assert check()("Create a utils.py") == "AMBIGUOUS"

    def test_sh_file_without_func_spec_is_ambiguous(self):
        assert check()("Create a cleanup.sh") == "AMBIGUOUS"

    def test_func_spec_without_script_file_does_not_promote(self):
        assert check()("Add a backend function to handle authentication") == "AMBIGUOUS"


class TestRegressionSufficientCases:
    def test_tooling_path_dep_triple(self):
        assert check()("Update the pipeline agent hook to use existing stack") == "SUFFICIENT"

    def test_script_keyword_path_dep(self):
        assert check()('Add a "migration.sh" script with no new dependencies') == "SUFFICIENT"

    def test_backend_branch_mvp(self):
        assert check()("Implement MVP auth endpoint on feat/auth-endpoint") == "SUFFICIENT"

    def test_frontend_component_perf(self):
        assert check()(
            'Add a "DataTable" component that renders 1000 rows under 100ms'
        ) == "SUFFICIENT"


class TestRegressionAmbiguousCases:
    def test_no_target_is_ambiguous(self):
        assert check()("Add a backend API endpoint for user authentication") == "AMBIGUOUS"

    def test_vague_python_task_is_ambiguous(self):
        assert check()(
            "Write a Python script to parse CSV files using existing stack"
        ) == "AMBIGUOUS"


class TestPromptSurface:
    def test_large_scoring_function_not_duplicated_in_prompt_docs(self):
        run_text = RUN_MD.read_text(encoding="utf-8")
        bootstrap_text = SUPERVISOR_BOOTSTRAP_MD.read_text(encoding="utf-8")
        assert "def sufficiency_check" not in run_text
        assert "def sufficiency_check" not in bootstrap_text
        assert "requirements-sufficiency.py" in run_text
        assert "requirements-sufficiency.py" in bootstrap_text
