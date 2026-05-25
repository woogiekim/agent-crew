from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_module(repo_root: Path):
    path = repo_root / "core" / "scripts" / "coverage-changed-surface.py"
    spec = importlib.util.spec_from_file_location("coverage_changed_surface", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def coverage_gate(repo_root: Path):
    return load_module(repo_root)


def write_coverage(path: Path, files: dict) -> Path:
    path.write_text(json.dumps({"files": files}), encoding="utf-8")
    return path


def file_payload(percent: float | str, missing: list[int] | object = ()) -> dict:
    return {
        "summary": {"percent_covered_display": percent},
        "missing_lines": list(missing) if isinstance(missing, tuple) else missing,
    }


def test_path_normalization_and_surface_filtering(coverage_gate):
    assert coverage_gate.normalize_path("./core/scripts/example.py") == "core/scripts/example.py"
    assert coverage_gate.is_python_execution_surface("./core/scripts/example.py")
    assert not coverage_gate.is_python_execution_surface("tests/python/test_example.py")
    assert not coverage_gate.is_python_execution_surface("core/scripts/example.sh")


def test_git_diff_names_returns_non_empty_lines(coverage_gate, monkeypatch):
    monkeypatch.setattr(
        coverage_gate.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="core/scripts/a.py\n\nREADME.md\n",
            stderr="",
        ),
    )

    assert coverage_gate.git_diff_names(["origin/main...HEAD"]) == [
        "core/scripts/a.py",
        "README.md",
    ]


def test_changed_files_merges_committed_staged_and_unstaged_diffs(coverage_gate, monkeypatch):
    outputs = {
        ("git", "diff", "--name-only", "--diff-filter=ACMR", "origin/main...HEAD"): "core/scripts/a.py\n",
        ("git", "diff", "--name-only", "--diff-filter=ACMR", "--cached"): "core/scripts/b.py\n",
        ("git", "diff", "--name-only", "--diff-filter=ACMR"): "core/scripts/a.py\ncore/scripts/c.py\n",
        ("git", "ls-files", "--others", "--exclude-standard"): "core/scripts/d.py\n",
    }

    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout=outputs[tuple(command)], stderr="")

    monkeypatch.setattr(coverage_gate.subprocess, "run", fake_run)

    assert coverage_gate.changed_files("origin/main") == [
        "core/scripts/a.py",
        "core/scripts/b.py",
        "core/scripts/c.py",
        "core/scripts/d.py",
    ]


def test_git_untracked_names_returns_non_empty_lines(coverage_gate, monkeypatch):
    monkeypatch.setattr(
        coverage_gate.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="core/scripts/new.py\n\n.coverage\n",
            stderr="",
        ),
    )

    assert coverage_gate.git_untracked_names() == ["core/scripts/new.py", ".coverage"]


def test_git_untracked_names_raises_error(coverage_gate, monkeypatch):
    monkeypatch.setattr(
        coverage_gate.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="bad ls\n"),
    )

    with pytest.raises(RuntimeError, match="bad ls"):
        coverage_gate.git_untracked_names()


def test_changed_files_raises_git_error(coverage_gate, monkeypatch):
    monkeypatch.setattr(
        coverage_gate.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="bad ref\n"),
    )

    with pytest.raises(RuntimeError, match="bad ref"):
        coverage_gate.git_diff_names(["missing...HEAD"])


def test_changed_files_uses_fallback_error_text(coverage_gate, monkeypatch):
    monkeypatch.setattr(
        coverage_gate.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )

    with pytest.raises(RuntimeError, match="git diff failed"):
        coverage_gate.git_diff_names(["missing...HEAD"])


def test_load_coverage_rejects_missing_files_object(coverage_gate, tmp_path: Path):
    payload = tmp_path / "coverage.json"
    payload.write_text(json.dumps({"meta": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="files object"):
        coverage_gate.load_coverage(payload)


def test_coverage_index_maps_absolute_core_script_paths(coverage_gate):
    payload = {"summary": {"percent_covered": 100}, "missing_lines": []}
    index = coverage_gate.coverage_index({"/tmp/repo/core/scripts/example.py": payload})

    assert index["/tmp/repo/core/scripts/example.py"] is payload
    assert index["core/scripts/example.py"] is payload


def test_percent_and_missing_line_defaults(coverage_gate):
    assert coverage_gate.percent_covered({"summary": {"percent_covered": 91.25}}) == 91.25
    assert coverage_gate.percent_covered({"summary": "bad"}) == 0.0
    assert coverage_gate.missing_lines({"missing_lines": [1, "x", 3]}) == [1, 3]
    assert coverage_gate.missing_lines({"missing_lines": "bad"}) == []


def test_evaluate_passes_when_no_python_execution_surfaces_changed(coverage_gate):
    report = coverage_gate.evaluate({}, ["README.md", "tests/python/test_x.py"], 100.0)

    assert report["status"] == "passed"
    assert report["target_files"] == []


def test_evaluate_reports_pass_missing_data_and_low_coverage(coverage_gate):
    files = {
        "core/scripts/full.py": file_payload("100"),
        "/tmp/repo/core/scripts/low.py": file_payload("99.50", (7, 9)),
    }

    report = coverage_gate.evaluate(
        files,
        [
            "./core/scripts/full.py",
            "core/scripts/low.py",
            "core/scripts/missing.py",
            "docs/ignored.py",
        ],
        100.0,
    )

    assert report["status"] == "failed"
    assert [item["reason"] for item in report["results"]] == [
        "ok",
        "coverage_below_minimum",
        "missing_coverage_data",
    ]


def test_render_text_outputs_pass_no_target_pass_target_and_fail(coverage_gate):
    no_target = {"target_files": [], "status": "passed", "results": []}
    passed = {"target_files": ["core/scripts/a.py"], "status": "passed", "results": []}
    failed = {
        "target_files": ["core/scripts/a.py"],
        "status": "failed",
        "results": [
            {
                "path": "core/scripts/a.py",
                "status": "failed",
                "coverage": 99.0,
                "reason": "coverage_below_minimum",
                "missing_lines": [12],
            }
        ],
    }

    assert coverage_gate.render_text(no_target).startswith("PASS: no changed")
    assert "1 changed Python" in coverage_gate.render_text(passed)
    assert "missing=[12]" in coverage_gate.render_text(failed)


def test_main_renders_json_for_explicit_changed_file(coverage_gate, tmp_path: Path, capsys):
    coverage_json = write_coverage(
        tmp_path / "coverage.json",
        {"core/scripts/a.py": file_payload("100")},
    )

    rc = coverage_gate.main([
        "--coverage-json",
        str(coverage_json),
        "--changed-file",
        "core/scripts/a.py",
        "--format",
        "json",
    ])

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


def test_main_uses_git_diff_when_changed_file_is_omitted(
    coverage_gate,
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    coverage_json = write_coverage(
        tmp_path / "coverage.json",
        {"core/scripts/a.py": file_payload("100")},
    )
    monkeypatch.setattr(coverage_gate, "changed_files", lambda base_ref: ["core/scripts/a.py"])

    rc = coverage_gate.main(["--coverage-json", str(coverage_json), "--base-ref", "main"])

    assert rc == 0
    assert "meet 100% coverage" in capsys.readouterr().out


def test_main_returns_failure_for_low_coverage(coverage_gate, tmp_path: Path, capsys):
    coverage_json = write_coverage(
        tmp_path / "coverage.json",
        {"core/scripts/a.py": file_payload("80", [4])},
    )

    rc = coverage_gate.main([
        "--coverage-json",
        str(coverage_json),
        "--changed-file",
        "core/scripts/a.py",
    ])

    assert rc == 1
    assert "coverage is below 100%" in capsys.readouterr().out


def test_main_returns_error_for_invalid_coverage_json(coverage_gate, tmp_path: Path, capsys):
    coverage_json = tmp_path / "coverage.json"
    coverage_json.write_text("{", encoding="utf-8")

    rc = coverage_gate.main(["--coverage-json", str(coverage_json)])

    assert rc == 2
    assert "ERROR:" in capsys.readouterr().err
