"""Tests for live telemetry correlation against retry-chaos taxonomy."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "core" / "scripts" / "telemetry-taxonomy-check.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


telemetry_taxonomy = _load_module(SCRIPT, "telemetry_taxonomy_check")


def _write_progress(task_dir: Path, events: list[dict]) -> None:
    task_dir.mkdir(parents=True)
    payload = "\n".join(json.dumps(event) for event in events) + "\n"
    (task_dir / "progress.buffer.jsonl").write_text(payload, encoding="utf-8")


def _write_coverage_files(state_dir: Path, task_id: str) -> None:
    task_dir = state_dir / "tasks" / task_id
    (task_dir / "tool-events.jsonl").write_text('{"tool":"bash"}\n', encoding="utf-8")
    (task_dir / "delegation.jsonl").write_text('{"agent_role":"backend"}\n', encoding="utf-8")
    cost_dir = state_dir / "cost"
    cost_dir.mkdir(parents=True, exist_ok=True)
    (cost_dir / f"{task_id}.jsonl").write_text('{"input_tokens":1,"output_tokens":1}\n', encoding="utf-8")


def _mark_current_contract(task_dir: Path) -> None:
    (task_dir / "register.json").write_text(
        json.dumps({"schema_version": 1, "telemetry_schema_version": 1}) + "\n",
        encoding="utf-8",
    )


def _run(state_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--state-dir",
            str(state_dir),
            "--format",
            "json",
            *args,
        ],
        text=True,
        capture_output=True,
    )


def test_telemetry_taxonomy_check_accepts_known_retry_labels(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(
        task_dir,
        [
            {"event": "RETRY", "detail": "attempt 2 token_truncation resume"},
            {"event": "RETRY", "detail": "reviewer rejected reason=tests_failed"},
            {"event": "BLOCKED", "detail": "quality_loop_exhausted"},
        ],
    )
    _mark_current_contract(task_dir)
    _write_coverage_files(state_dir, "20260523-010203-0")

    result = _run(state_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    labels = set(payload["tasks"][0]["labels"])
    assert {"token_truncation", "tests_failed", "quality_loop_exhausted"}.issubset(labels)
    assert payload["summary"]["classified_events"] == 3


def test_telemetry_taxonomy_helpers_cover_fixture_state_and_progress_edges(monkeypatch, tmp_path: Path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert telemetry_taxonomy.load_json(invalid)[0] is None
    assert telemetry_taxonomy.load_taxonomy(invalid)[1]["error_type"] == "invalid_fixture"

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    assert telemetry_taxonomy.load_json(array) == (None, "fixture root must be an object")

    no_labels = tmp_path / "no-labels.json"
    no_labels.write_text(
        json.dumps({"schema_version": 1, "cases": [{"expected": {}}]}),
        encoding="utf-8",
    )
    assert "did not define" in telemetry_taxonomy.load_taxonomy(no_labels)[1]["failures"][0]

    mixed_expected = tmp_path / "mixed-expected.json"
    mixed_expected.write_text(
        json.dumps({
            "schema_version": 1,
            "cases": [
                {"expected": "bad"},
                {"expected": {"retry_reasons": ["known"]}},
            ],
        }),
        encoding="utf-8",
    )
    assert telemetry_taxonomy.load_taxonomy(mixed_expected) == ({"known"}, None)

    non_object_case = tmp_path / "non-object-case.json"
    non_object_case.write_text(
        json.dumps({"schema_version": 1, "cases": ["bad-case"]}),
        encoding="utf-8",
    )
    assert telemetry_taxonomy.load_taxonomy(non_object_case)[1]["failures"] == [
        "fixture cases must be objects"
    ]

    assert telemetry_taxonomy._string_list("one") == ["one"]
    assert telemetry_taxonomy._string_list(["one", "", 2]) == ["one"]

    explicit = tmp_path / "explicit-task"
    assert telemetry_taxonomy.discover_task_dirs(tmp_path, [str(explicit)]) == [explicit]

    monkeypatch.setenv("AGENT_CREW_STATE_DIR", str(tmp_path / "env-state"))
    assert telemetry_taxonomy.resolve_state_dir(None) == tmp_path / "env-state"
    monkeypatch.delenv("AGENT_CREW_STATE_DIR")
    monkeypatch.setenv("AGENT_CREW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_CREW_PROJECT", "project")
    assert telemetry_taxonomy.resolve_state_dir(None) == tmp_path / "home" / "state" / "project"

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    assert telemetry_taxonomy.read_progress_buffer(task_dir) == []
    (task_dir / "progress.buffer.jsonl").write_text(
        "\nnot json\n" + json.dumps({"event": "RETRY", "retry_reason": "known"}) + "\n",
        encoding="utf-8",
    )
    assert telemetry_taxonomy.read_progress_buffer(task_dir) == [
        {"event": "RETRY", "retry_reason": "known"}
    ]

    (task_dir / "register.json").write_text("not json", encoding="utf-8")
    assert telemetry_taxonomy.is_current_telemetry_contract_task(task_dir) is False


def test_telemetry_taxonomy_label_extraction_coverage_and_text_output(capsys, tmp_path: Path):
    labels, unknown = telemetry_taxonomy.extract_labels(
        {
            "event": "INFO",
            "retry_reason": ["known", "mystery"],
            "detail": "reason=another_mystery taxonomy_label=known",
        },
        {"known"},
    )
    assert labels == {"known"}
    assert unknown == {"another_mystery", "mystery"}

    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(
        task_dir,
        [
            {"event": "INFO", "detail": "not classifiable"},
            {"event": "RETRY", "detail": "token_truncation"},
        ],
    )
    _mark_current_contract(task_dir)
    (task_dir / "tool-events.jsonl").write_text("\nnot json\n{}\n", encoding="utf-8")
    coverage = telemetry_taxonomy.telemetry_coverage(
        task_dir,
        telemetry_taxonomy.read_progress_buffer(task_dir),
    )
    assert coverage["tool_events"] == 1

    result = telemetry_taxonomy.evaluate(
        state_dir,
        REPO_ROOT / "core" / "evaluations" / "retry-chaos.json",
        [],
        ["token_truncation", "not_in_taxonomy"],
    )
    assert {"invalid_required_labels": ["not_in_taxonomy"]} in result["failures"]

    text_payload = {
        "passed": False,
        "summary": {
            "tasks": 1,
            "events": 1,
            "classified_events": 1,
            "unknown_labels": 1,
            "current_schema_failures": 1,
            "historical_compatibility_warnings": 11,
        },
        "tasks": [
            {
                "task_id": "task",
                "labels": ["known"],
                "unknown_labels": ["mystery"],
            }
        ],
        "failures": [{"unknown_labels": ["mystery"]}],
        "historical_compatibility_warnings": [{"code": f"legacy-{index}"} for index in range(11)],
    }
    telemetry_taxonomy.print_text(text_payload)
    output = capsys.readouterr().out
    assert "FAIL: telemetry taxonomy check" in output
    assert "labels=known unknown=mystery" in output
    assert "legacy-compatible warnings truncated: 1 more" in output


def test_telemetry_taxonomy_check_rejects_unknown_explicit_label(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(task_dir, [{"event": "RETRY", "retry_reason": "mystery_retry"}])
    _write_coverage_files(state_dir, "20260523-010203-0")

    result = _run(state_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["tasks"][0]["unknown_labels"] == ["mystery_retry"]


def test_telemetry_taxonomy_check_enforces_required_label(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(task_dir, [{"event": "RETRY", "detail": "token_truncation"}])
    _write_coverage_files(state_dir, "20260523-010203-0")

    result = _run(state_dir, "--require-label", "host_blocked")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["failures"] == [{"missing_required_labels": ["host_blocked"]}]


def test_telemetry_taxonomy_check_rejects_invalid_fixture(tmp_path: Path):
    state_dir = tmp_path / "state"
    fixture = tmp_path / "retry-chaos.json"
    fixture.write_text('{"schema_version": 1, "cases": []}\n', encoding="utf-8")

    result = _run(state_dir, "--fixture", str(fixture))

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error_type"] == "invalid_fixture"


def test_telemetry_taxonomy_check_rejects_empty_event_stream(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    task_dir.mkdir(parents=True)
    _mark_current_contract(task_dir)
    (task_dir / "progress.buffer.jsonl").write_text("", encoding="utf-8")

    result = _run(state_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["failures"][0]["code"] == "insufficient_telemetry_coverage"


def test_telemetry_taxonomy_check_rejects_absent_task_streams(tmp_path: Path):
    state_dir = tmp_path / "state"

    result = _run(state_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["failures"][0]["code"] == "insufficient_telemetry_coverage"
    assert "no task telemetry streams" in payload["failures"][0]["detail"]


def test_telemetry_taxonomy_check_reports_weak_coverage_categories(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(task_dir, [{"event": "RETRY", "detail": "token_truncation"}])
    _mark_current_contract(task_dir)

    result = _run(state_dir)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["failures"][0]["code"] == "weak_telemetry_coverage"
    assert set(payload["failures"][0]["weak_categories"]) == {"tool", "delegation", "token"}


def test_telemetry_taxonomy_check_separates_legacy_warnings(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "legacy-task"
    task_dir.mkdir(parents=True)
    (task_dir / "progress.log").write_text("2026-01-01T00:00:00 | STARTED | legacy\n", encoding="utf-8")

    result = _run(state_dir)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["summary"]["legacy_compatible_tasks"] == 1
    assert payload["historical_compatibility_warnings"][0]["code"] == "insufficient_telemetry_coverage"
    assert payload["current_schema_failures"] == []


def test_telemetry_taxonomy_check_treats_unmarked_weak_stream_as_legacy_warning(
    tmp_path: Path,
):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(task_dir, [{"event": "RETRY", "detail": "token_truncation"}])

    result = _run(state_dir)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["historical_compatibility_warnings"][0]["code"] == "weak_telemetry_coverage"
    assert payload["current_schema_failures"] == []


def test_telemetry_taxonomy_check_text_cli_uses_default_printer(tmp_path: Path):
    state_dir = tmp_path / "state"
    task_dir = state_dir / "tasks" / "20260523-010203-0"
    _write_progress(task_dir, [{"event": "RETRY", "detail": "token_truncation"}])
    _mark_current_contract(task_dir)
    _write_coverage_files(state_dir, "20260523-010203-0")

    result = subprocess.run(
        ["python3", str(SCRIPT), "--state-dir", str(state_dir)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: telemetry taxonomy check" in result.stdout
