"""Tests for provider-neutral fake completion marker scanning."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "fake-completion-scan.py"
QUALITY_CHECK = REPO_ROOT / "core" / "scripts" / "quality-loop-check.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scanner_detects_closed_list_markers(tmp_path: Path) -> None:
    scanner = _load_module(SCRIPT, "fake_completion_scan")
    target = tmp_path / "Wallet.kt"
    target.write_text(
        "class Wallet {\n"
        "  fun debit() = TODO(\"wire balance validation\")\n"
        "}\n",
        encoding="utf-8",
    )

    report = scanner.scan_paths([target])

    assert report["status"] == "failed"
    assert report["findings"][0]["path"].endswith("Wallet.kt")
    assert report["findings"][0]["marker"] == "kotlin_todo_call"


def test_scanner_skips_markdown_prose_quotes_and_fenced_examples(tmp_path: Path) -> None:
    scanner = _load_module(SCRIPT, "fake_completion_scan")
    target = tmp_path / "README.md"
    target.write_text(
        "Plain prose can mention TODO, FIXME, and NotImplementedError without failing.\n\n"
        "> TODO in quoted prior art should not fail\n\n"
        "```kotlin\n"
        "fun example() = TODO(\"documented example\")\n"
        "```\n\n"
        "Implementation complete.\n",
        encoding="utf-8",
    )

    report = scanner.scan_paths([target])

    assert report["status"] == "passed"
    assert report["scanned"] == []
    assert report["findings"] == []


def test_scanner_detects_python_not_implemented_without_parentheses(tmp_path: Path) -> None:
    scanner = _load_module(SCRIPT, "fake_completion_scan")
    target = tmp_path / "wallet.py"
    target.write_text(
        "def debit(balance, amount):\n"
        "    raise NotImplementedError\n",
        encoding="utf-8",
    )

    report = scanner.scan_paths([target])

    assert report["status"] == "failed"
    assert report["findings"][0]["marker"] == "python_not_implemented"


def test_scanner_detects_tc004_marker_in_extensionless_executable(tmp_path: Path) -> None:
    scanner = _load_module(SCRIPT, "fake_completion_scan")
    target = tmp_path / "crew"
    target.write_text(
        "#!/usr/bin/env bash\n"
        "# TODO: finish host bridge dispatch\n",
        encoding="utf-8",
    )
    target.chmod(0o755)

    report = scanner.scan_paths([target])

    assert report["status"] == "failed"
    assert report["scanned"] == [str(target)]
    assert report["findings"][0]["marker"] == "todo_placeholder"


def test_cli_reports_json_findings(tmp_path: Path) -> None:
    target = tmp_path / "sample.test.ts"
    target.write_text("it.only('TC-001 success-case - works', () => {})\n", encoding="utf-8")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--path", str(target), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["findings"][0]["marker"] == "focused_test_only"


def _set_register_paths(task_dir: Path, project_root: Path, modified_files: list[str]) -> None:
    register_path = task_dir / "register.json"
    register = json.loads(register_path.read_text(encoding="utf-8"))
    register["project_root"] = str(project_root)
    register["modified_files"] = modified_files
    register_path.write_text(json.dumps(register), encoding="utf-8")


def test_quality_loop_uses_register_modified_files_with_project_root_resolution(tmp_path: Path) -> None:
    helpers = _load_module(
        REPO_ROOT / "tests" / "python" / "test_quality_loop_pipeline_check.py",
        "quality_loop_pipeline_helpers",
    )

    task_dir = tmp_path / "task"
    project_root = tmp_path / "project"
    changed = project_root / "src" / "wallet.py"
    changed.parent.mkdir(parents=True)
    changed.write_text(
        "def debit(balance, amount):\n"
        "    raise NotImplementedError\n",
        encoding="utf-8",
    )
    helpers.write_task(
        task_dir,
        [
            helpers.row("STAGE_DONE", "test-writer", "TDD RED GREEN REFACTOR, 3 tests passed", stage=1),
            helpers.row("STAGE_DONE", "backend", "backend - completed", stage=1),
            helpers.row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
    )
    _set_register_paths(task_dir, project_root, ["src/wallet.py"])

    result = subprocess.run(
        ["python3", str(QUALITY_CHECK), "--task-dir", str(task_dir), "--format", "json"],
        text=True,
        capture_output=True,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "fake_completion_markers_present" in payload["hard_failures"]
    assert payload["fake_completion"]["findings"][0]["marker"] == "python_not_implemented"
    assert payload["fake_completion"]["scanned"] == [str(changed)]


def test_quality_loop_blocks_test_markers_from_register_modified_files(tmp_path: Path) -> None:
    helpers = _load_module(
        REPO_ROOT / "tests" / "python" / "test_quality_loop_pipeline_check.py",
        "quality_loop_pipeline_helpers_test_markers",
    )

    task_dir = tmp_path / "task"
    project_root = tmp_path / "project"
    changed = project_root / "tests" / "wallet.test.ts"
    changed.parent.mkdir(parents=True)
    changed.write_text(
        "it.only('TC-001 debit rejects overdraft', () => {})\n",
        encoding="utf-8",
    )
    helpers.write_task(
        task_dir,
        [
            helpers.row("STAGE_DONE", "test-writer", "TDD RED GREEN REFACTOR, 3 tests passed", stage=1),
            helpers.row("STAGE_DONE", "backend", "backend - completed", stage=1),
            helpers.row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
    )
    _set_register_paths(task_dir, project_root, ["tests/wallet.test.ts"])

    result = subprocess.run(
        ["python3", str(QUALITY_CHECK), "--task-dir", str(task_dir), "--format", "json"],
        text=True,
        capture_output=True,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "fake_completion_markers_present" in payload["hard_failures"]
    assert payload["fake_completion"]["findings"][0]["marker"] == "focused_test_only"


def test_quality_loop_blocks_extensionless_executable_markers_from_register_modified_files(tmp_path: Path) -> None:
    helpers = _load_module(
        REPO_ROOT / "tests" / "python" / "test_quality_loop_pipeline_check.py",
        "quality_loop_pipeline_helpers_extensionless_executable",
    )

    task_dir = tmp_path / "task"
    project_root = tmp_path / "project"
    changed = project_root / "bin" / "crew"
    changed.parent.mkdir(parents=True)
    changed.write_text(
        "#!/usr/bin/env bash\n"
        "# TODO: finish host bridge dispatch\n",
        encoding="utf-8",
    )
    changed.chmod(0o755)
    helpers.write_task(
        task_dir,
        [
            helpers.row("STAGE_DONE", "test-writer", "TDD RED GREEN REFACTOR, 3 tests passed", stage=1),
            helpers.row("STAGE_DONE", "backend", "backend - completed", stage=1),
            helpers.row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
    )
    _set_register_paths(task_dir, project_root, ["bin/crew"])

    result = subprocess.run(
        ["python3", str(QUALITY_CHECK), "--task-dir", str(task_dir), "--format", "json"],
        text=True,
        capture_output=True,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "fake_completion_markers_present" in payload["hard_failures"]
    assert payload["fake_completion"]["scanned"] == [str(changed)]
    assert payload["fake_completion"]["findings"][0]["marker"] == "todo_placeholder"


def test_quality_loop_ignores_non_authoritative_test_writer_fixture_paths(tmp_path: Path) -> None:
    helpers = _load_module(
        REPO_ROOT / "tests" / "python" / "test_quality_loop_pipeline_check.py",
        "quality_loop_pipeline_helpers_non_implementer",
    )

    task_dir = tmp_path / "task"
    fixture = tmp_path / "tests" / "quality_loop_fixture.py"
    fixture.parent.mkdir()
    fixture.write_text(
        "def fixture():\n"
        "    raise NotImplementedError('fixture documents an expected marker')\n",
        encoding="utf-8",
    )
    helpers.write_task(
        task_dir,
        [
            {
                **helpers.row("STAGE_DONE", "test-writer", "TDD RED GREEN REFACTOR, 3 tests passed", stage=1),
                "files": [str(fixture)],
            },
            helpers.row("STAGE_DONE", "backend", "backend - completed", stage=1),
            helpers.row("STAGE_DONE", "reviewer", "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json", stage=2),
        ],
    )

    result = subprocess.run(
        ["python3", str(QUALITY_CHECK), "--task-dir", str(task_dir), "--format", "json"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "fake_completion_markers_present" not in payload["hard_failures"]
    assert payload["fake_completion"]["findings"] == []
