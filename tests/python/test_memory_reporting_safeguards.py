"""Tests for memory evaluation and report quality safeguards."""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_EVAL = REPO_ROOT / "core" / "scripts" / "memory-retrieval-eval.py"
REPORT_CHECK = REPO_ROOT / "core" / "scripts" / "report-quality-check.py"
CANONICAL_CONTEXT = REPO_ROOT / "core" / "scripts" / "canonical-context.py"
MEMORY_TRACE = REPO_ROOT / "core" / "scripts" / "memory-evidence-trace.py"
MEMORY_FIXTURE = REPO_ROOT / "core" / "evaluations" / "memory-retrieval.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


memory_eval = _load_module(MEMORY_EVAL, "memory_retrieval_eval")


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
        "commercialization-e2e-[0-9]+-(review|guardrails|remediation)-[0-9]{8}"
    ]
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


def test_report_quality_gate_passes_with_measurements_evidence_blocker_and_memory(
    tmp_path: Path,
):
    task_dir = tmp_path / "task"
    (task_dir / "context").mkdir(parents=True)
    (task_dir / "context" / "memory.md").write_text(
        "31ec5287-1233-426e-8e1f-241adff08cb3 repeated latency conclusion\n",
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
