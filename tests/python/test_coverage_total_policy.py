from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def load_module(repo_root: Path):
    path = repo_root / "core" / "scripts" / "coverage-total-policy.py"
    spec = importlib.util.spec_from_file_location("coverage_total_policy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def policy(repo_root: Path):
    return load_module(repo_root)


def coverage_payload(files: dict, total: float = 100.0) -> dict:
    return {"files": files, "totals": {"percent_covered": total}}


def file_payload(percent: float, missing: list[int] | object = ()) -> dict:
    return {
        "summary": {"percent_covered": percent},
        "missing_lines": list(missing) if isinstance(missing, tuple) else missing,
    }


def exceptions_payload(entries: list[dict], defaults: bool = True) -> dict:
    payload = {"exceptions": entries}
    if defaults:
        payload.update({
            "default_owner": "test-writer",
            "default_reason": "legacy",
            "default_target": "remove after tests",
        })
    return payload


def write_json(path: Path, payload: dict | list) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_normalize_path(policy):
    assert policy.normalize_path("./core/scripts/a.py") == "core/scripts/a.py"


def test_load_json_requires_object(policy, tmp_path: Path):
    with pytest.raises(ValueError, match="JSON object"):
        policy.load_json(write_json(tmp_path / "bad.json", []))


def test_coverage_files_requires_files_object(policy):
    with pytest.raises(ValueError, match="files object"):
        policy.coverage_files({})


def test_exception_entries_require_list_object_path_and_unique_path(policy):
    with pytest.raises(ValueError, match="exceptions list"):
        policy.exception_entries({})
    with pytest.raises(ValueError, match="object with a path"):
        policy.exception_entries({"exceptions": ["bad"]})
    with pytest.raises(ValueError, match="duplicate"):
        policy.exception_entries(exceptions_payload([
            {"path": "core/scripts/a.py"},
            {"path": "./core/scripts/a.py"},
        ]))


def test_exception_entries_merge_defaults(policy):
    result = policy.exception_entries(exceptions_payload([
        {"path": "./core/scripts/a.py", "owner": "custom"},
    ]))

    assert result["core/scripts/a.py"]["owner"] == "custom"
    assert result["core/scripts/a.py"]["reason"] == "legacy"


def test_percent_and_missing_defaults(policy):
    assert policy.percent_covered({"summary": {"percent_covered": "87.5"}}) == 87.5
    assert policy.percent_covered({"summary": "bad"}) == 0.0
    assert policy.missing_count({"missing_lines": [1, 2]}) == 2
    assert policy.missing_count({"missing_lines": "bad"}) == 0


def test_invalid_exception_fields_and_failure(policy):
    assert policy.invalid_exception_fields({"owner": "x"}) == [
        "baseline_percent",
        "max_missing_lines",
        "reason",
        "target",
    ]
    assert policy.failure("p", "code", "detail") == {
        "path": "p",
        "code": "code",
        "detail": "detail",
    }


def test_evaluate_passes_with_covered_and_legacy_files(policy):
    report = policy.evaluate(
        coverage_payload({
            "core/scripts/full.py": file_payload(100.0),
            "core/scripts/legacy.py": file_payload(80.0, (3, 4)),
            "tests/python/ignored.py": file_payload(0.0, (1,)),
        }, total=91.25),
        exceptions_payload([
            {
                "path": "core/scripts/legacy.py",
                "baseline_percent": 80.0,
                "max_missing_lines": 2,
            }
        ]),
        100.0,
        "core/scripts/",
    )

    assert report["status"] == "passed"
    assert report["covered_100_count"] == 1
    assert report["legacy_exception_count"] == 1
    assert report["raw_total_percent"] == 91.25


def test_evaluate_skips_non_python_files_inside_prefix(policy):
    report = policy.evaluate(
        coverage_payload({"core/scripts/helper.sh": file_payload(0.0, (1,))}),
        exceptions_payload([]),
        100.0,
        "core/scripts/",
    )

    assert report["status"] == "passed"


def test_evaluate_reports_all_failure_types(policy):
    report = policy.evaluate(
        coverage_payload({
            "core/scripts/covered_with_exception.py": file_payload(100.0),
            "core/scripts/missing_exception.py": file_payload(99.0, (1,)),
            "core/scripts/invalid_exception.py": file_payload(10.0, (1,)),
            "core/scripts/regressed.py": file_payload(70.0, (1, 2, 3)),
        }),
        exceptions_payload([
            {
                "path": "core/scripts/stale.py",
                "baseline_percent": 0.0,
                "max_missing_lines": 1,
            },
            {
                "path": "core/scripts/covered_with_exception.py",
                "baseline_percent": 0.0,
                "max_missing_lines": 1,
            },
            {"path": "core/scripts/invalid_exception.py"},
            {
                "path": "core/scripts/regressed.py",
                "baseline_percent": 90.0,
                "max_missing_lines": 1,
            },
        ], defaults=False),
        100.0,
        "core/scripts/",
    )

    assert [item["code"] for item in report["failures"]] == [
        "stale_exception",
        "obsolete_exception",
        "invalid_exception",
        "missing_exception",
        "coverage_regressed",
        "missing_lines_regressed",
    ]


def test_render_text_pass_and_fail(policy):
    passed = {
        "status": "passed",
        "covered_100_count": 2,
        "legacy_exception_count": 1,
        "raw_total_percent": 90.0,
    }
    failed = {
        "status": "failed",
        "failures": [
            {"path": "core/scripts/a.py", "code": "missing_exception", "detail": "below"}
        ],
    }

    assert "PASS: full Python coverage policy satisfied" in policy.render_text(passed)
    assert "missing_exception - below" in policy.render_text(failed)


def test_main_json_success(policy, tmp_path: Path, capsys):
    coverage_json = write_json(
        tmp_path / "coverage.json",
        coverage_payload({"core/scripts/a.py": file_payload(100.0)}),
    )
    exceptions_json = write_json(tmp_path / "exceptions.json", exceptions_payload([]))

    rc = policy.main([
        "--coverage-json",
        str(coverage_json),
        "--exceptions",
        str(exceptions_json),
        "--format",
        "json",
    ])

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


def test_main_text_failure(policy, tmp_path: Path, capsys):
    coverage_json = write_json(
        tmp_path / "coverage.json",
        coverage_payload({"core/scripts/a.py": file_payload(50.0, [1])}),
    )
    exceptions_json = write_json(tmp_path / "exceptions.json", exceptions_payload([]))

    rc = policy.main([
        "--coverage-json",
        str(coverage_json),
        "--exceptions",
        str(exceptions_json),
    ])

    assert rc == 1
    assert "FAIL: full Python coverage policy" in capsys.readouterr().out


def test_main_error(policy, tmp_path: Path, capsys):
    coverage_json = tmp_path / "bad.json"
    coverage_json.write_text("{", encoding="utf-8")

    rc = policy.main(["--coverage-json", str(coverage_json)])

    assert rc == 2
    assert "ERROR:" in capsys.readouterr().err
