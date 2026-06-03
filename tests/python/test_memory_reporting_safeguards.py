"""Tests for memory evaluation and report quality safeguards."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_EVAL = REPO_ROOT / "core" / "scripts" / "memory-retrieval-eval.py"
REPORT_CHECK = REPO_ROOT / "core" / "scripts" / "report-quality-check.py"
CANONICAL_CONTEXT = REPO_ROOT / "core" / "scripts" / "canonical-context.py"
MEMORY_TRACE = REPO_ROOT / "core" / "scripts" / "memory-evidence-trace.py"
MEMORY_FIXTURE = REPO_ROOT / "core" / "evaluations" / "memory-retrieval.json"


def _load_module(path: Path, name: str):
    scripts_dir = str(path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


memory_eval = _load_module(MEMORY_EVAL, "memory_retrieval_eval")
memory_trace = _load_module(MEMORY_TRACE, "memory_evidence_trace")
report_quality = _load_module(REPORT_CHECK, "report_quality_check")


def test_memory_retrieval_fixture_defines_fixed_expected_ids_and_budgets():
    fixture = json.loads(MEMORY_FIXTURE.read_text(encoding="utf-8"))

    assert fixture["expected_memory_ids"] == [
        "f6c6c59e-b4aa-4169-aa27-968de14a1e39",
        "693036fb-febd-4d8a-b8c3-cf3a0d5c73f3",
        "c004a271-d86c-4467-bf54-29927887bbd6",
        "84ce5062-ea82-4552-84eb-6aaa2c4e9638",
        "req-commercialization-eval-6-20260521",
        "a1fc78d0-14fd-45ae-a3e5-1363e328f813",
        "31ec5287-1233-426e-8e1f-241adff08cb3",
        "d2d62df8-33c9-4d03-90b3-e2be9484f88f",
    ]
    assert fixture["accepted_successor_memory_ids"][
        "31ec5287-1233-426e-8e1f-241adff08cb3"
    ] == [
        "9d41b3cc-0cb5-4921-a9e6-30dbf0e269cc",
        "5b5ad81a-4d29-4b4d-a2ce-9e1fcefff04b",
        "06e5f2d0-6cef-4354-a5c9-921f0a543c9d",
    ]
    assert fixture["accepted_successor_memory_ids"][
        "d2d62df8-33c9-4d03-90b3-e2be9484f88f"
    ] == [
        "31ec5287-1233-426e-8e1f-241adff08cb3",
        "cf0a2807-aa93-45ce-9e1c-b2c24c4f7c97",
        "5b5ad81a-4d29-4b4d-a2ce-9e1fcefff04b",
        "06e5f2d0-6cef-4354-a5c9-921f0a543c9d",
        "75684e27-6093-4630-a8df-b8091fb544c9",
    ]
    assert fixture["accepted_context_memory_id_patterns"] == [
        "commercialization-e2e-[0-9]+-(review|guardrails|remediation|risk-remediation)-[0-9]{8}"
    ]
    assert fixture["results_file"] == "memory-retrieval-golden.txt"
    assert fixture["results_file_elapsed_ms"] == 250
    assert fixture["accepted_context_headroom"] == 5
    assert fixture["latency_budget_ms"] > 0
    assert fixture["noise_budget_count"] >= 0


def test_memory_eval_reports_misses_noise_and_latency_separately():
    fixture = {
        "query": "probe",
        "expected_memory_ids": ["expected-a", "expected-b"],
        "latency_budget_ms": 10,
        "noise_budget_count": 0,
    }
    result = memory_eval.evaluate(
        fixture,
        "  [fts] expected-a: useful\n  [fts] noisy-extra: unrelated\n",
        20.0,
    )

    assert result["passed"] is False
    assert result["misses"] == ["expected-b"]
    assert result["failures"]["noise"] == ["noisy-extra"]
    assert result["failures"]["latency_ms"] == 20.0


def test_memory_eval_helpers_cover_fixture_output_and_subprocess_edges(monkeypatch, tmp_path: Path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"query": "probe"}), encoding="utf-8")
    try:
        memory_eval.load_fixture(fixture)
    except ValueError as exc:
        assert "expected_memory_ids" in str(exc)
    else:
        raise AssertionError("expected missing-key fixture to fail")

    assert memory_eval.extract_ids("[mnemos] expected-a\n[memory] expected-b\n  expected-c: ok\n") == ["expected-c"]
    assert memory_eval.extract_scores("[memory] expected-a score=1\n  expected-b score=0.9\n") == {"expected-b": 0.9}

    class BadScoreRe:
        def search(self, _line: str):
            class Match:
                def group(self, _index: int):
                    return "bad"

            return Match()

    monkeypatch.setattr(memory_eval, "SCORE_RE", BadScoreRe())
    assert memory_eval.extract_scores("expected-a score=bad\n") == {}

    class Proc:
        stdout = "out\n"
        stderr = "err\n"
        returncode = 124

    monkeypatch.setattr(memory_eval.subprocess, "run", lambda *_args, **_kwargs: Proc())
    output, rc, elapsed_ms = memory_eval.run_memory(Path("memory"), "probe", 3)
    assert output == "out\nerr\n"
    assert rc == 124
    assert elapsed_ms >= 0

    assert memory_eval.resolve_fixture_path(None, fixture_path=fixture) is None
    assert memory_eval.resolve_fixture_path(tmp_path / "absolute.txt", fixture_path=fixture) == tmp_path / "absolute.txt"
    assert memory_eval.resolve_fixture_path("relative.txt", fixture_path=fixture) == tmp_path / "relative.txt"


def test_memory_eval_enforces_optional_relevance_scores():
    fixture = {
        "query": "probe",
        "expected_memory_ids": ["expected-a", "expected-b"],
        "latency_budget_ms": 10,
        "noise_budget_count": 0,
        "min_expected_score": 0.75,
    }
    result = memory_eval.evaluate(
        fixture,
        "  [fts] expected-a: useful score=0.74\n"
        "  [fts] expected-b: useful\n",
        5.0,
    )

    assert result["passed"] is False
    assert result["failures"]["low_scores"] == {"expected-a": 0.74}
    assert result["failures"]["missing_scores"] == ["expected-b"]


def test_memory_eval_accepts_explicit_successor_memories():
    fixture = {
        "query": "probe",
        "expected_memory_ids": ["older-memory"],
        "accepted_successor_memory_ids": {
            "older-memory": ["newer-memory"],
        },
        "latency_budget_ms": 10,
        "noise_budget_count": 0,
    }
    result = memory_eval.evaluate(fixture, "  [fts] newer-memory: useful\n", 5.0)

    assert result["passed"] is True
    assert result["misses"] == []
    assert result["noise"] == []
    assert result["satisfied_by_successor"] == {"older-memory": ["newer-memory"]}


def test_memory_eval_classifies_round_summaries_as_context_not_noise():
    fixture = {
        "query": "probe",
        "expected_memory_ids": ["expected-memory"],
        "accepted_context_memory_id_patterns": [
            "commercialization-e2e-[0-9]+-(review|guardrails|remediation)-[0-9]{8}"
        ],
        "latency_budget_ms": 10,
        "noise_budget_count": 0,
    }
    result = memory_eval.evaluate(
        fixture,
        "  [fts] expected-memory: useful\n"
        "  [fts] commercialization-e2e-14-review-20260522: useful summary\n",
        5.0,
    )

    assert result["passed"] is True
    assert result["noise"] == []
    assert result["context_memory_ids"] == ["commercialization-e2e-14-review-20260522"]


def test_memory_eval_context_headroom_prevents_summary_crowding():
    fixture = {
        "query": "probe",
        "limit": 1,
        "expected_memory_ids": ["expected-memory"],
        "accepted_context_memory_id_patterns": [
            "commercialization-e2e-[0-9]+-(review|guardrails|remediation|risk-remediation)-[0-9]{8}"
        ],
        "latency_budget_ms": 10,
        "noise_budget_count": 0,
    }
    result = memory_eval.evaluate(
        fixture,
        "  [fts] commercialization-e2e-16-risk-remediation-20260522: useful context\n"
        "  [fts] expected-memory: useful evidence\n",
        5.0,
    )

    assert result["passed"] is True
    assert result["evaluated_memory_ids"] == ["expected-memory"]
    assert result["context_memory_ids"] == [
        "commercialization-e2e-16-risk-remediation-20260522"
    ]


def test_memory_eval_still_fails_unrelated_noise():
    fixture = {
        "query": "probe",
        "expected_memory_ids": ["expected-memory"],
        "accepted_context_memory_id_patterns": [
            "commercialization-e2e-[0-9]+-(review|guardrails|remediation)-[0-9]{8}"
        ],
        "latency_budget_ms": 10,
        "noise_budget_count": 0,
    }
    result = memory_eval.evaluate(
        fixture,
        "  [fts] expected-memory: useful\n  [fts] unrelated-noise: bad\n",
        5.0,
    )

    assert result["passed"] is False
    assert result["failures"]["noise"] == ["unrelated-noise"]


def test_memory_eval_cli_covers_results_file_and_memory_invocation(tmp_path: Path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps({
            "query": "probe",
            "expected_memory_ids": ["expected-a"],
            "latency_budget_ms": 10000,
            "noise_budget_count": 0,
        }),
        encoding="utf-8",
    )
    results = tmp_path / "results.txt"
    results.write_text("expected-a: useful\nnoisy-extra: unrelated\n", encoding="utf-8")

    text_result = subprocess.run(
        [
            "python3",
            str(MEMORY_EVAL),
            "--fixture",
            str(fixture),
            "--results-file",
            str(results),
            "--elapsed-ms",
            "20",
        ],
        text=True,
        capture_output=True,
    )

    assert text_result.returncode == 1
    assert "FAIL: memory retrieval evaluation" in text_result.stdout
    assert "noise: noisy-extra" in text_result.stdout

    missing_results = tmp_path / "missing-results.txt"
    missing_results.write_text("", encoding="utf-8")
    missing_result = subprocess.run(
        [
            "python3",
            str(MEMORY_EVAL),
            "--fixture",
            str(fixture),
            "--results-file",
            str(missing_results),
        ],
        text=True,
        capture_output=True,
    )

    assert missing_result.returncode == 1
    assert "missing: expected-a" in missing_result.stdout

    memory_bin = tmp_path / "memory"
    memory_bin.write_text("#!/bin/sh\necho 'expected-a: useful'\n", encoding="utf-8")
    memory_bin.chmod(0o755)
    json_result = subprocess.run(
        [
            "python3",
            str(MEMORY_EVAL),
            "--fixture",
            str(fixture),
            "--memory-bin",
            str(memory_bin),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert json_result.returncode == 0, json_result.stdout + json_result.stderr
    payload = json.loads(json_result.stdout)
    assert payload["memory_rc"] == 0
    assert payload["passed"] is True


def test_memory_eval_uses_fixture_results_file_by_default(tmp_path: Path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps({
            "query": "probe",
            "results_file": "golden.txt",
            "results_file_elapsed_ms": 12.5,
            "expected_memory_ids": ["expected-a"],
            "latency_budget_ms": 10000,
            "noise_budget_count": 0,
        }),
        encoding="utf-8",
    )
    (tmp_path / "golden.txt").write_text("expected-a score=0.9 useful\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(MEMORY_EVAL),
            "--fixture",
            str(fixture),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["evidence_mode"] == "results_file"
    assert payload["latency_ms"] == 12.5


def test_memory_eval_main_covers_results_file_live_memory_json_and_text(
    monkeypatch,
    capsys,
    tmp_path: Path,
):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps({
            "query": "probe",
            "results_file": "golden.txt",
            "results_file_elapsed_ms": 12.5,
            "expected_memory_ids": ["expected-a"],
            "latency_budget_ms": 10000,
            "noise_budget_count": 0,
        }),
        encoding="utf-8",
    )
    (tmp_path / "golden.txt").write_text("expected-a score=0.9 useful\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["memory-retrieval-eval.py", "--fixture", str(fixture), "--format", "json"],
    )
    assert memory_eval.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["evidence_mode"] == "results_file"

    monkeypatch.setattr(
        memory_eval,
        "run_memory",
        lambda _memory_bin, _query, _limit: ("expected-a score=0.9 useful\n", 124, 7.0),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["memory-retrieval-eval.py", "--fixture", str(fixture), "--live-memory", "--format", "json"],
    )
    assert memory_eval.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["evidence_mode"] == "live_memory"
    assert payload["memory_rc"] == 124

    noisy = tmp_path / "noisy.txt"
    noisy.write_text("noisy-extra unrelated\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "memory-retrieval-eval.py",
            "--fixture",
            str(fixture),
            "--results-file",
            str(noisy),
            "--elapsed-ms",
            "20",
        ],
    )
    assert memory_eval.main() == 1
    output = capsys.readouterr().out
    assert "FAIL: memory retrieval evaluation" in output
    assert "missing: expected-a" in output
    assert "noise: noisy-extra" in output


def test_memory_eval_main_rejects_results_file_live_memory_conflict(
    monkeypatch,
    tmp_path: Path,
):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps({
            "query": "probe",
            "expected_memory_ids": ["expected-a"],
            "latency_budget_ms": 10000,
            "noise_budget_count": 0,
        }),
        encoding="utf-8",
    )
    results = tmp_path / "results.txt"
    results.write_text("expected-a\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "memory-retrieval-eval.py",
            "--fixture",
            str(fixture),
            "--results-file",
            str(results),
            "--live-memory",
        ],
    )

    with pytest.raises(SystemExit):
        memory_eval.main()


def test_report_quality_gate_passes_with_measurements_evidence_blocker_and_memory(
    tmp_path: Path,
):
    task_dir = tmp_path / "task"
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "context" / "memory.md").write_text(
        "31ec5287-1233-426e-8e1f-241adff08cb3 repeated latency conclusion\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "memory-evidence.json").write_text(
        json.dumps({
            "memory_ids": ["31ec5287-1233-426e-8e1f-241adff08cb3"],
            "retrieved_memory_ids": ["31ec5287-1233-426e-8e1f-241adff08cb3"],
            "accepted_context_memory_ids": [],
            "satisfied_by_successor": {},
        }),
        encoding="utf-8",
    )
    evidence = task_dir / "progress.log"
    evidence.write_text("ok\n", encoding="utf-8")
    report = task_dir / "result.md"
    report.write_text(
        "STATUS: blocked\n"
        "BLOCKER: stage_timeout\n"
        "MEASUREMENTS: stage duration 42 seconds, retries 1\n"
        "EVIDENCE: progress.log\n"
        "UNCERTAINTY: Unknown host runtime variance remains.\n"
        "Memory reused: 31ec5287-1233-426e-8e1f-241adff08cb3\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert payload["reused_memory_context_ids"] == [
        "31ec5287-1233-426e-8e1f-241adff08cb3"
    ]


def test_report_quality_gate_blocks_low_value_report(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    report = task_dir / "result.md"
    report.write_text("STATUS: completed\nLooks good.\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_measurements" in payload["failures"]
    assert "missing_evidence" in payload["failures"]
    assert "missing_uncertainty" in payload["failures"]


def test_report_quality_helpers_cover_linked_evidence_and_invalid_trace(tmp_path: Path):
    assert report_quality.evidence_paths("EVIDENCE: [trace](context/evidence.md#L1)\n") == [
        "context/evidence.md"
    ]

    trace = tmp_path / "memory-evidence.json"
    trace.write_text("not json", encoding="utf-8")
    assert report_quality.memory_ids_from_trace(trace) == set()

    telemetry = tmp_path / "telemetry.json"
    telemetry.write_text("not json", encoding="utf-8")
    assert report_quality.stale_blocker_count_from_telemetry(telemetry) == 0

    telemetry.write_text(json.dumps({"summary": {"tasks_stale_blocked": "many"}}), encoding="utf-8")
    assert report_quality.stale_blocker_count_from_telemetry(telemetry) == 0


def test_report_quality_flags_invalid_evidence_blocker_and_missing_memory_reuse(tmp_path: Path):
    task_dir = tmp_path / "task"
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "context" / "memory-evidence.json").write_text(
        json.dumps({"memory_ids": ["trace-memory-999"]}),
        encoding="utf-8",
    )
    report = task_dir / "result.md"
    report.write_text(
        "STATUS: blocked\n"
        "BLOCKER: unexpected_blocker\n"
        "MEASUREMENTS: status latency 42 ms\n"
        "EVIDENCE: missing.log\n"
        "UNCERTAINTY: Unknown runtime variance remains.\n",
        encoding="utf-8",
    )

    payload = report_quality.check_report(
        report,
        task_dir,
        {"allowed_blockers": ["stage_timeout"]},
    )

    assert payload["missing_evidence_paths"] == ["missing.log"]
    assert "invalid_evidence_paths" in payload["failures"]
    assert "invalid_blocker_classification" in payload["failures"]
    assert "missing_memory_context_reuse" in payload["failures"]


def test_report_quality_text_output_lists_failures(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    report = task_dir / "result.md"
    report.write_text("STATUS: completed\nLooks good.\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "FAIL: report quality" in result.stdout
    assert "- missing_measurements" in result.stdout


def test_report_quality_gate_requires_tdd_and_reviewer_for_completed_implementation(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "register.json").write_text(
        json.dumps({"task": "Implement a production update quality gate"}),
        encoding="utf-8",
    )
    evidence = task_dir / "progress.log"
    evidence.write_text("ok\n", encoding="utf-8")
    report = task_dir / "result.md"
    report.write_text(
        "STATUS: completed\n"
        "MEASUREMENTS: 12 tests passed\n"
        "EVIDENCE: progress.log\n"
        "UNCERTAINTY: Unknown reviewer runtime variance remains.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["quality_loop_required"] is True
    assert "missing_tdd_evidence" in payload["failures"]
    assert "missing_reviewer_evidence" in payload["failures"]


def test_report_quality_gate_accepts_tdd_and_reviewer_for_completed_implementation(tmp_path: Path):
    task_dir = tmp_path / "task"
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "register.json").write_text(
        json.dumps({"task": "Implement a production update quality gate"}),
        encoding="utf-8",
    )
    (task_dir / "pipeline.json").write_text(
        json.dumps({
            "schema_version": 1,
            "task": "Implement a production update quality gate",
            "stages": [
                {"agents": ["backend"], "tdd_parallel": True},
                "reviewer",
            ],
            "completed_stages": 2,
        }),
        encoding="utf-8",
    )
    progress_rows = [
        {
            "ts": "2026-05-22T00:00:00Z",
            "trace_id": "20260522-000000.20260522-000000-0.1.1",
            "task_id": "20260522-000000-0",
            "session_id": "20260522-000000",
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "test-writer",
            "attempt": 1,
            "status": "completed",
            "detail": "TDD RED GREEN REFACTOR, 12 tests passed",
            "files": [],
        },
        {
            "ts": "2026-05-22T00:00:01Z",
            "trace_id": "20260522-000000.20260522-000000-0.1.1",
            "task_id": "20260522-000000-0",
            "session_id": "20260522-000000",
            "event": "STAGE_DONE",
            "stage": 1,
            "agent": "backend",
            "attempt": 1,
            "status": "completed",
            "detail": "backend - N/A",
            "files": [],
        },
        {
            "ts": "2026-05-22T00:00:02Z",
            "trace_id": "20260522-000000.20260522-000000-0.2.1",
            "task_id": "20260522-000000-0",
            "session_id": "20260522-000000",
            "event": "STAGE_DONE",
            "stage": 2,
            "agent": "reviewer",
            "attempt": 1,
            "status": "completed",
            "detail": "reviewer - REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json",
            "files": [],
        },
    ]
    with (task_dir / "progress.buffer.jsonl").open("w", encoding="utf-8") as handle:
        for row in progress_rows:
            handle.write(json.dumps(row) + "\n")
    (task_dir / "context" / "tdd_log.md").write_text(
        "TDD: RED -> GREEN -> REFACTOR. tests passed 12.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "review.md").write_text(
        "REVIEW: APPROVED QUALITY_METRICS: context/quality-metrics.json after refactor.\n",
        encoding="utf-8",
    )
    (task_dir / "context" / "quality-metrics.json").write_text(
        json.dumps({
            "schema_version": 1,
            "hallucination_detected": False,
            "rollback_performed": False,
            "human_intervention_required": False,
            "factuality_review": "passed",
            "evidence_paths": ["context/review.md"],
        }),
        encoding="utf-8",
    )
    evidence = task_dir / "progress.log"
    evidence.write_text("ok\n", encoding="utf-8")
    report = task_dir / "result.md"
    report.write_text(
        "STATUS: completed\n"
        "MEASUREMENTS: 12 tests passed\n"
        "EVIDENCE: progress.log\n"
        "UNCERTAINTY: Unknown reviewer runtime variance remains.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["quality_loop_required"] is True
    assert payload["tdd_evidence_paths"] == ["context/tdd_log.md"]
    assert payload["review_evidence_paths"] == ["context/review.md"]


def test_report_quality_gate_requires_memory_evidence_trace_when_context_exists(tmp_path: Path):
    task_dir = tmp_path / "task"
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "context" / "memory.md").write_text(
        "trace-memory-456 useful prior context\n",
        encoding="utf-8",
    )
    evidence = task_dir / "progress.log"
    evidence.write_text("ok\n", encoding="utf-8")
    report = task_dir / "result.md"
    report.write_text(
        "STATUS: completed\n"
        "MEASUREMENTS: status latency 42 ms\n"
        "EVIDENCE: progress.log\n"
        "UNCERTAINTY: Unknown runtime variance remains.\n"
        "Memory reused: trace-memory-456\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "missing_memory_evidence_trace" in payload["failures"]


def test_report_quality_gate_blocks_unclassified_stale_blockers(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    evidence = task_dir / "progress.log"
    evidence.write_text("ok\n", encoding="utf-8")
    telemetry = task_dir / "telemetry.json"
    telemetry.write_text(
        json.dumps({"summary": {"tasks_stale_blocked": 2}}),
        encoding="utf-8",
    )
    report = task_dir / "result.md"
    report.write_text(
        "STATUS: completed\n"
        "MEASUREMENTS: status latency 42 ms\n"
        "EVIDENCE: progress.log\n"
        "UNCERTAINTY: Unknown historical task outcome remains.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--telemetry",
            str(telemetry),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["stale_blocker_count"] == 2
    assert "missing_stale_blocker_classification" in payload["failures"]


def test_report_quality_gate_accepts_classified_stale_blockers(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    evidence = task_dir / "progress.log"
    evidence.write_text("ok\n", encoding="utf-8")
    telemetry = task_dir / "telemetry.json"
    telemetry.write_text(
        json.dumps({"summary": {"tasks_stale_blocked": 2}}),
        encoding="utf-8",
    )
    report = task_dir / "result.md"
    report.write_text(
        "STATUS: completed\n"
        "BLOCKER: stale_host_bridge_not_invoked\n"
        "STALE_BLOCKERS: 2\n"
        "MEASUREMENTS: status latency 42 ms\n"
        "EVIDENCE: progress.log\n"
        "UNCERTAINTY: Unknown historical task outcome remains.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--telemetry",
            str(telemetry),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["stale_blocker_count"] == 2
    assert "missing_stale_blocker_classification" not in payload["failures"]


def test_report_quality_gate_blocks_low_value_blocked_handoff(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    report = task_dir / "result.md"
    report.write_text(
        "STATUS: blocked\n"
        "BLOCKER: supervisor_handoff_not_started\n"
        "DETAIL: Host bridge did not complete the handoff.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["blockers"] == ["supervisor_handoff_not_started"]
    assert "missing_measurements" in payload["failures"]
    assert "missing_evidence" in payload["failures"]
    assert "missing_uncertainty" in payload["failures"]


def test_report_quality_memory_ids_ignore_plain_words(tmp_path: Path):
    task_dir = tmp_path / "task"
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "context" / "memory.md").write_text(
        "commercialization requirements completed bridge\n",
        encoding="utf-8",
    )
    evidence = task_dir / "progress.log"
    evidence.write_text("ok\n", encoding="utf-8")
    report = task_dir / "result.md"
    report.write_text(
        "STATUS: blocked\n"
        "BLOCKER: stage_timeout\n"
        "MEASUREMENTS: stage duration 42 seconds, retries 1\n"
        "EVIDENCE: progress.log\n"
        "UNCERTAINTY: Unknown host runtime variance remains.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["memory_context_ids"] == []
    assert payload["reused_memory_context_ids"] == []


def test_memory_evidence_trace_records_memory_reuse_for_report_quality(tmp_path: Path):
    task_dir = tmp_path / "task"
    (task_dir / "context").mkdir(parents=True)
    evidence = task_dir / "progress.log"
    evidence.write_text("ok\n", encoding="utf-8")

    trace = subprocess.run(
        [
            "python3",
            str(MEMORY_TRACE),
            "--task-dir",
            str(task_dir),
            "--memory-id",
            "trace-memory-123",
            "--evidence",
            "progress.log",
            "--reused",
            "yes",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert trace.returncode == 0, trace.stdout + trace.stderr
    payload = json.loads(trace.stdout)
    assert payload["memory_context_reused"] is True
    assert payload["memory_ids"] == ["trace-memory-123"]
    assert payload["memory_quality"]["reusable_memory_count"] == 1
    assert payload["memory_quality"]["score"] >= 0

    report = task_dir / "result.md"
    report.write_text(
        "STATUS: completed\n"
        "MEASUREMENTS: status latency 123 ms\n"
        "EVIDENCE: progress.log\n"
        "UNCERTAINTY: Unknown host variance remains.\n"
        "Memory reused: trace-memory-123\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    quality = json.loads(result.stdout)
    assert quality["memory_context_ids"] == ["trace-memory-123"]
    assert quality["reused_memory_context_ids"] == ["trace-memory-123"]


def test_memory_evidence_trace_folds_retrieval_eval_context_feedback(tmp_path: Path):
    task_dir = tmp_path / "task"
    (task_dir / "context").mkdir(parents=True)
    evidence = task_dir / "progress.log"
    evidence.write_text("ok\n", encoding="utf-8")
    retrieval = task_dir / "retrieval.json"
    retrieval.write_text(
        json.dumps(
            {
                "passed": True,
                "returned_memory_ids": ["expected-memory", "round-context"],
                "context_memory_ids": ["round-context"],
                "satisfied_by_successor": {"old-memory": ["new-memory"]},
                "latency_ms": 42.5,
                "noise": [],
                "misses": [],
            }
        ),
        encoding="utf-8",
    )

    trace = subprocess.run(
        [
            "python3",
            str(MEMORY_TRACE),
            "--task-dir",
            str(task_dir),
            "--memory-id",
            "explicit-memory",
            "--retrieval-eval-json",
            str(retrieval),
            "--evidence",
            "progress.log",
            "--reused",
            "yes",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert trace.returncode == 0, trace.stdout + trace.stderr
    payload = json.loads(trace.stdout)
    assert payload["memory_ids"] == ["explicit-memory", "round-context", "new-memory"]
    assert payload["retrieved_memory_ids"] == ["expected-memory", "round-context"]
    assert payload["accepted_context_memory_ids"] == ["round-context"]
    assert payload["retrieval_latency_ms"] == 42.5

    report = task_dir / "result.md"
    report.write_text(
        "STATUS: completed\n"
        "MEASUREMENTS: retrieval latency 42.5 ms\n"
        "EVIDENCE: progress.log\n"
        "UNCERTAINTY: Unknown host variance remains.\n"
        "Memory reused: round-context and new-memory\n",
        encoding="utf-8",
    )
    quality = subprocess.run(
        [
            "python3",
            str(REPORT_CHECK),
            "--report",
            str(report),
            "--task-dir",
            str(task_dir),
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
    )

    assert quality.returncode == 0, quality.stdout + quality.stderr
    result = json.loads(quality.stdout)
    assert "round-context" in result["memory_context_ids"]
    assert "new-memory" in result["memory_context_ids"]
    assert result["reused_memory_context_ids"] == ["new-memory", "round-context"]


def test_memory_evidence_trace_helpers_cover_invalid_and_missing_inputs(tmp_path: Path):
    task_dir = tmp_path / "task"
    task_dir.mkdir()

    existing, missing = memory_trace.resolve_evidence(task_dir, ["missing.md"])
    assert existing == []
    assert missing == ["missing.md"]

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert memory_trace.load_retrieval_eval(str(invalid)) == {
        "path": str(invalid),
        "load_error": True,
    }

    non_object = tmp_path / "array.json"
    non_object.write_text("[]", encoding="utf-8")
    assert memory_trace.load_retrieval_eval(str(non_object)) == {
        "path": str(non_object),
        "load_error": True,
    }
    assert memory_trace.successor_ids({"satisfied_by_successor": []}) == []


def test_memory_evidence_trace_text_reports_missing_evidence_and_note(tmp_path: Path):
    task_dir = tmp_path / "task"

    result = subprocess.run(
        [
            "python3",
            str(MEMORY_TRACE),
            "--task-dir",
            str(task_dir),
            "--evidence",
            "missing.md",
            "--reused",
            "no",
            "--note",
            "manual trace note",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "TRACE:" in result.stdout
    assert "MEMORY_CONTEXT_REUSED: no" in result.stdout
    assert "MISSING_EVIDENCE: missing.md" in result.stdout
    markdown = task_dir / "context" / "memory-evidence.md"
    text = markdown.read_text(encoding="utf-8")
    assert "MISSING_EVIDENCE: missing.md" in text
    assert "NOTE: manual trace note" in text


def test_canonical_context_compacts_repeated_prior_outcomes(tmp_path: Path):
    first = tmp_path / "a.md"
    second = tmp_path / "b.md"
    output = tmp_path / "canonical-context.md"
    first.write_text("CONCLUSION: Telemetry must expose retries.\n", encoding="utf-8")
    second.write_text("CONCLUSION: Telemetry must expose retries.\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(CANONICAL_CONTEXT),
            "--output",
            str(output),
            str(first),
            str(second),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    text = output.read_text(encoding="utf-8")
    assert "repeated=2: Telemetry must expose retries." in text


def test_canonical_context_ignores_missing_and_non_matching_inputs(tmp_path: Path):
    source = tmp_path / "notes.md"
    missing = tmp_path / "missing.md"
    output = tmp_path / "canonical-context.md"
    source.write_text("plain note without a canonical marker\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(CANONICAL_CONTEXT),
            "--output",
            str(output),
            str(missing),
            str(source),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "- Unknown: no repeated prior outcomes were available." in output.read_text(encoding="utf-8")
